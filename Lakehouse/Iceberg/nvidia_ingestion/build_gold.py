"""
Gold Layer Construction for Nvidia PhysicalAI dataset.

Produces pre-joined, ML-ready feature tables:

  lidar_with_ego
      LiDAR point-cloud data joined with ego-motion and calibration.
      Suitable for SLAM, localisation, and 3D object detection training.
      (Works with both Draco-blob and decoded lidar modes.)

  sensor_fusion_clip
      Per-clip denormalisation that brings together all sensor timestamps,
      ego-motion, calibration, and metadata in a single queryable table.
      One row per clip.

  radar_ego_fusion
      All radar returns for a clip joined with ego-motion and extrinsics,
      useful for radar-centric perception / tracking research.

Supports two modes:
  - "materialized": Writes physical Iceberg tables (default, faster queries)
  - "view": Creates SQL views only (zero storage overhead)
"""

from typing import Dict, List, Optional

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    col,
    collect_list,
    count,
    first,
    lit,
    monotonically_increasing_id,
    struct,
)

from kaist_ingestion.config import KAISTConfig, apply_ad_table_optimizations

from .benchmark import BenchmarkTracker
from .config import NvidiaPipelineConfig, build_spark_session, create_namespaces


class NvidiaGoldBuilder:

    GOLD_SORT_CONFIG = {
        "lidar_with_ego": ["clip_id", "reference_timestamp"],
        "sensor_fusion_clip": ["split"],
        "radar_ego_fusion": ["clip_id", "timestamp"],
    }

    GOLD_METRICS_CONFIG = {
        "lidar_with_ego": ["clip_id", "reference_timestamp"],
        "sensor_fusion_clip": ["split"],
        "radar_ego_fusion": ["clip_id", "timestamp", "sensor_name"],
    }

    def __init__(self, spark: SparkSession, config: NvidiaPipelineConfig,
                 tracker: Optional[BenchmarkTracker] = None):
        self.spark = spark
        self.config = config
        self.cat = config.spark_catalog_name
        self.silver_ns = config.nvidia.namespace_silver
        self.gold_ns = config.nvidia.namespace_gold
        self.tracker = tracker
        self.view_mode = config.nvidia.gold_mode == "view"
        self._opt_cfg = KAISTConfig(
            write_distribution_mode=config.nvidia.write_distribution_mode,
            snapshot_min_to_keep=config.nvidia.snapshot_min_to_keep,
            snapshot_max_age_hours=config.nvidia.snapshot_max_age_hours,
        )

    def _silver(self, t: str) -> str:
        return f"{self.cat}.{self.silver_ns}.{t}"

    def _gold(self, t: str) -> str:
        return f"{self.cat}.{self.gold_ns}.{t}"

    def _read_silver(self, t: str) -> DataFrame:
        return self.spark.table(self._silver(t))

    def _write_gold(self, df: DataFrame, table: str,
                    partition_by: Optional[List[str]] = None) -> int:
        full = self._gold(table)
        sort_by = self.GOLD_SORT_CONFIG.get(table)
        if sort_by:
            df = df.sortWithinPartitions(*sort_by)

        writer = (
            df.writeTo(full).using("iceberg")
            .tableProperty("format-version", "2")
            .tableProperty("write.target-file-size-bytes",
                           str(self.config.nvidia.target_file_size_bytes))
        )
        if partition_by:
            writer = writer.partitionedBy(*partition_by)
        writer.createOrReplace()

        metrics = self.GOLD_METRICS_CONFIG.get(table, [])
        apply_ad_table_optimizations(
            self.spark, full,
            sort_columns=sort_by,
            partition_columns=partition_by,
            metrics_columns=metrics or None,
            config=self._opt_cfg,
        )
        return self.spark.table(full).count()

    def _create_gold_view(self, table: str, sql: str) -> int:
        """Create a Gold view (zero storage mode)."""
        full = self._gold(table)
        self.spark.sql(f"CREATE OR REPLACE VIEW {full} AS {sql}")
        return self.spark.table(full).count()

    # -- gold table builders -------------------------------------------------

    def build_lidar_with_ego(self) -> int:
        """Join lidar with ego-motion by clip_id."""
        print(f"[GOLD] lidar_with_ego ({'view' if self.view_mode else 'materialized'})")
        if self.tracker:
            self.tracker.begin("gold", "lidar_with_ego")

        lidar_tbl = ("lidar_decoded"
                      if self.config.nvidia.lidar_mode == "decoded"
                      else "lidar")

        if self.view_mode:
            sql = (
                f"SELECT l.*, e.ego_sample_count, e.ego_trajectory "
                f"FROM {self._silver(lidar_tbl)} l "
                f"LEFT JOIN ("
                f"  SELECT clip_id, "
                f"    count(*) AS ego_sample_count, "
                f"    collect_list(struct(timestamp, x, y, z, qw, qx, qy, qz)) AS ego_trajectory "
                f"  FROM {self._silver('egomotion')} "
                f"  GROUP BY clip_id"
                f") e ON l.clip_id = e.clip_id"
            )
            rows_out = self._create_gold_view("lidar_with_ego", sql)
        else:
            lidar = self._read_silver(lidar_tbl)
            egomotion = self._read_silver("egomotion")
            ego_agg = egomotion.groupBy("clip_id").agg(
                count("*").alias("ego_sample_count"),
                collect_list(
                    struct("timestamp", "x", "y", "z", "qw", "qx", "qy", "qz")
                ).alias("ego_trajectory"),
            )
            df = lidar.join(ego_agg, on="clip_id", how="left")
            rows_out = self._write_gold(df, "lidar_with_ego", partition_by=["clip_id"])

        if self.tracker:
            self.tracker.end(rows_out=rows_out)
        print(f"  [DONE] {self._gold('lidar_with_ego')}: {rows_out} rows")
        return rows_out

    def build_sensor_fusion_clip(self) -> int:
        """Positionally merge per-clip metadata tables.

        Note: This table always materializes because it uses
        monotonically_increasing_id() for positional joins, which is
        non-deterministic and cannot be expressed as a stable view.
        """
        print("[GOLD] sensor_fusion_clip (always materialized)")
        if self.tracker:
            self.tracker.begin("gold", "sensor_fusion_clip")

        clip_index = self._read_silver("clip_index").withColumn("_row", monotonically_increasing_id())
        data_coll = self._read_silver("data_collection").withColumn("_row", monotonically_increasing_id())
        sensor_pres = self._read_silver("sensor_presence").withColumn("_row", monotonically_increasing_id())
        veh_dim = self._read_silver("vehicle_dimensions").withColumn("_row", monotonically_increasing_id())

        df = clip_index
        df = df.join(data_coll, on="_row", how="left")
        df = df.join(sensor_pres, on="_row", how="left")
        df = df.join(veh_dim, on="_row", how="left")
        df = df.drop("_row")

        rows_out = self._write_gold(df, "sensor_fusion_clip", partition_by=["split"])
        if self.tracker:
            self.tracker.end(rows_out=rows_out)
        print(f"  [DONE] {self._gold('sensor_fusion_clip')}: {rows_out} rows")
        return rows_out

    def build_radar_ego_fusion(self) -> int:
        """Combine all radar sensor tables with ego-motion by clip_id."""
        print(f"[GOLD] radar_ego_fusion ({'view' if self.view_mode else 'materialized'})")
        if self.tracker:
            self.tracker.begin("gold", "radar_ego_fusion")

        # Discover radar tables in silver
        try:
            silver_tables = [
                r[1] for r in
                self.spark.sql(
                    f"SHOW TABLES IN {self.cat}.{self.silver_ns}"
                ).collect()
            ]
        except Exception:
            silver_tables = []

        radar_tables = sorted(t for t in silver_tables if t.startswith("radar_"))
        if not radar_tables:
            print("  [SKIP] no radar tables found in silver")
            if self.tracker:
                self.tracker.end(rows_out=0)
            return 0

        if self.view_mode:
            # Build a SQL UNION ALL view
            unions = []
            for rt in radar_tables:
                sensor_name = rt.replace("radar_", "", 1)
                unions.append(
                    f"SELECT *, '{sensor_name}' AS sensor_name "
                    f"FROM {self._silver(rt)}"
                )
            union_sql = " UNION ALL ".join(unions)

            sql = (
                f"SELECT r.*, e.ego_sample_count "
                f"FROM ({union_sql}) r "
                f"LEFT JOIN ("
                f"  SELECT clip_id, count(*) AS ego_sample_count "
                f"  FROM {self._silver('egomotion')} "
                f"  GROUP BY clip_id"
                f") e ON r.clip_id = e.clip_id"
            )
            rows_out = self._create_gold_view("radar_ego_fusion", sql)
        else:
            # Materialized path (original logic)
            frames = []
            for rt in radar_tables:
                rdf = self._read_silver(rt)
                if "sensor_name" not in rdf.columns:
                    sensor_name = rt.replace("radar_", "", 1)
                    rdf = rdf.withColumn("sensor_name", lit(sensor_name))
                frames.append(rdf)

            combined = frames[0]
            for f in frames[1:]:
                combined = combined.unionByName(f, allowMissingColumns=True)

            if "clip_id" in combined.columns:
                egomotion = self._read_silver("egomotion")
                ego_agg = egomotion.groupBy("clip_id").agg(
                    count("*").alias("ego_sample_count"),
                )
                combined = combined.join(ego_agg, on="clip_id", how="left")

            rows_out = self._write_gold(combined, "radar_ego_fusion",
                                         partition_by=["sensor_name"])

        if self.tracker:
            self.tracker.end(rows_out=rows_out)
        print(f"  [DONE] {self._gold('radar_ego_fusion')}: {rows_out} rows")
        return rows_out

    # -- orchestrator --------------------------------------------------------

    def build_all(self) -> Dict[str, int]:
        results: Dict[str, int] = {}
        for name, fn in [
            ("lidar_with_ego", self.build_lidar_with_ego),
            ("sensor_fusion_clip", self.build_sensor_fusion_clip),
            ("radar_ego_fusion", self.build_radar_ego_fusion),
        ]:
            try:
                results[name] = fn()
            except Exception as e:
                print(f"  [ERROR] {name}: {e}")
                results[name] = -1
        return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_gold_build(
    config: Optional[NvidiaPipelineConfig] = None,
    tracker: Optional[BenchmarkTracker] = None,
) -> Dict[str, int]:
    if config is None:
        config = NvidiaPipelineConfig()
    spark = build_spark_session(config, app_name="nvidia-gold")
    try:
        create_namespaces(spark, config)
        builder = NvidiaGoldBuilder(spark, config, tracker=tracker)
        return builder.build_all()
    finally:
        spark.stop()


if __name__ == "__main__":
    tracker = BenchmarkTracker("nvidia-gold")
    results = run_gold_build(tracker=tracker)
    tracker.print_summary()
    tracker.flush()

    print("\n" + "=" * 60)
    print("NVIDIA GOLD BUILD SUMMARY")
    print("=" * 60)
    for table, count in results.items():
        status = "+" if count >= 0 else "-"
        print(f"  {status} {table}: {count} rows")
