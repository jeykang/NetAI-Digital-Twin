"""
Gold Layer Construction for KAIST E2E Dataset.

The Gold layer provides pre-joined, ML-ready feature tables optimized for
specific access patterns. These tables eliminate runtime joins and enable
partition pruning for fast data loading.
"""

from typing import Dict, Optional

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    array,
    col,
    collect_list,
    first,
    lit,
    struct,
)

from .config import PipelineConfig, build_spark_session, create_namespaces


class GoldTableBuilder:
    """
    Builds denormalized Gold tables from Silver layer data.
    
    Gold tables are designed for specific ML workloads:
    - camera_annotations: Object detection training
    - lidar_with_ego: SLAM/Localization
    - sensor_fusion_frame: Multi-modal perception
    """
    
    def __init__(self, spark: SparkSession, config: PipelineConfig):
        self.spark = spark
        self.config = config
        self.catalog = config.spark_catalog_name
        self.silver_ns = config.kaist.namespace_silver
        self.gold_ns = config.kaist.namespace_gold
        
    def _silver_table(self, table: str) -> str:
        return f"{self.catalog}.{self.silver_ns}.{table}"
    
    def _gold_table(self, table: str) -> str:
        return f"{self.catalog}.{self.gold_ns}.{table}"
    
    def _read_silver(self, table: str) -> DataFrame:
        return self.spark.table(self._silver_table(table))
    
    def _write_gold(
        self,
        df: DataFrame,
        table: str,
        partition_by: Optional[list] = None,
    ) -> int:
        """Write a DataFrame to the Gold layer."""
        full_table = self._gold_table(table)
        
        writer = (
            df.writeTo(full_table)
            .using("iceberg")
            .tableProperty("format-version", "2")
            .tableProperty("write.target-file-size-bytes",
                          str(self.config.kaist.target_file_size_bytes))
        )
        
        if partition_by:
            writer = writer.partitionedBy(*partition_by)
            
        writer.createOrReplace()
        
        return self.spark.table(full_table).count()
    
    def build_camera_annotations(self) -> int:
        """
        Build camera_annotations Gold table.
        
        Pre-joins:
        - Camera sensor data
        - Frame metadata
        - Clip/Session hierarchy
        - Calibration data
        - Dynamic object annotations
        - HD map metadata
        
        Partition by: camera_name (enables sensor-specific queries)
        """
        print("[BUILD] camera_annotations")
        
        # Read Silver tables
        camera = self._read_silver("camera")
        frame = self._read_silver("frame")
        clip = self._read_silver("clip")
        calibration = self._read_silver("calibration")
        dynamic_obj = self._read_silver("dynamic_object")
        hdmap = self._read_silver("hdmap")
        
        # Build the denormalized table
        # Step 1: Join camera with frame metadata
        df = camera.join(
            frame.select("frame_id", "frame_idx"),
            on="frame_id",
            how="left"
        )
        
        # Step 2: Add clip/session hierarchy
        df = df.join(
            clip.select("clip_id", "session_id", "date"),
            on="clip_id",
            how="left"
        )
        
        # Step 3: Add calibration data (sensor-specific)
        df = df.join(
            calibration.select(
                col("clip_id").alias("cal_clip_id"),
                col("sensor_name"),
                col("extrinsics"),
                col("camera_intrinsics"),
            ),
            (df.clip_id == col("cal_clip_id")) & (df.camera_name == col("sensor_name")),
            how="left"
        ).drop("cal_clip_id", "sensor_name")
        
        # Step 4: Add annotations (aggregated per frame)
        annotations_agg = dynamic_obj.groupBy("frame_id").agg(
            collect_list(
                struct(
                    col("boxes_3d"),
                    col("category"),
                )
            ).alias("annotations")
        )
        
        df = df.join(annotations_agg, on="frame_id", how="left")
        
        # Step 5: Add HD map metadata
        df = df.join(
            hdmap.select(
                col("clip_id").alias("map_clip_id"),
                col("city"),
                col("site"),
            ),
            df.clip_id == col("map_clip_id"),
            how="left"
        ).drop("map_clip_id")
        
        # Select final columns in order
        df = df.select(
            "frame_id",
            "clip_id",
            "session_id",
            "frame_idx",
            "sensor_timestamp",
            "camera_name",
            "filename",
            "extrinsics",
            "camera_intrinsics",
            "annotations",
            "city",
            "site",
            "date",
        )
        
        return self._write_gold(df, "camera_annotations", partition_by=["camera_name"])
    
    def build_lidar_with_ego(self) -> int:
        """
        Build lidar_with_ego Gold table.
        
        Pre-joins:
        - LiDAR sensor data
        - Ego motion (translation + rotation)
        - Calibration (extrinsics)
        
        Partition by: clip_id (bucketed for temporal queries within a clip)
        """
        print("[BUILD] lidar_with_ego")
        
        lidar = self._read_silver("lidar")
        ego_motion = self._read_silver("ego_motion")
        calibration = self._read_silver("calibration")
        
        # Join LiDAR with ego motion
        df = lidar.join(
            ego_motion.select(
                col("frame_id").alias("ego_frame_id"),
                col("translation").alias("ego_translation"),
                col("rotation").alias("ego_rotation"),
            ),
            lidar.frame_id == col("ego_frame_id"),
            how="left"
        ).drop("ego_frame_id")
        
        # Join with calibration (assuming single LiDAR per clip, sensor_name = 'lidar')
        df = df.join(
            calibration.filter(col("sensor_name") == "lidar").select(
                col("clip_id").alias("cal_clip_id"),
                col("extrinsics"),
            ),
            df.clip_id == col("cal_clip_id"),
            how="left"
        ).drop("cal_clip_id")
        
        df = df.select(
            "frame_id",
            "clip_id",
            "filename",
            "sensor_timestamp",
            "ego_translation",
            "ego_rotation",
            "extrinsics",
        )
        
        return self._write_gold(df, "lidar_with_ego", partition_by=["clip_id"])
    
    def build_sensor_fusion_frame(self) -> int:
        """
        Build sensor_fusion_frame Gold table.
        
        This is the most comprehensive Gold table, providing all sensor
        modalities for a single frame in a single row.
        
        Structure:
        - One row per frame
        - Camera data as a map (camera_name -> struct)
        - Radar data as a map (radar_name -> struct)
        - Single LiDAR filename
        - Aggregated annotations
        
        Partition by: clip_id
        """
        print("[BUILD] sensor_fusion_frame")
        
        frame = self._read_silver("frame")
        camera = self._read_silver("camera")
        lidar = self._read_silver("lidar")
        radar = self._read_silver("radar")
        dynamic_obj = self._read_silver("dynamic_object")
        
        # Aggregate cameras per frame
        camera_agg = camera.groupBy("frame_id").agg(
            collect_list(
                struct(
                    col("camera_name"),
                    col("filename"),
                    col("sensor_timestamp"),
                )
            ).alias("cameras")
        )
        
        # Aggregate radars per frame
        radar_agg = radar.groupBy("frame_id").agg(
            collect_list(
                struct(
                    col("radar_name"),
                    col("filename"),
                    col("sensor_timestamp"),
                )
            ).alias("radars")
        )
        
        # Get LiDAR per frame (assuming single LiDAR)
        lidar_df = lidar.select(
            col("frame_id").alias("lidar_frame_id"),
            col("filename").alias("lidar_filename"),
            col("sensor_timestamp").alias("lidar_timestamp"),
        )
        
        # Aggregate annotations
        annot_agg = dynamic_obj.groupBy("frame_id").agg(
            collect_list(
                struct(
                    col("boxes_3d"),
                    col("category"),
                )
            ).alias("annotations")
        )
        
        # Build the fusion frame
        df = frame.select("frame_id", "clip_id", "frame_idx")
        
        df = df.join(camera_agg, on="frame_id", how="left")
        df = df.join(radar_agg, on="frame_id", how="left")
        df = df.join(lidar_df, df.frame_id == col("lidar_frame_id"), how="left").drop("lidar_frame_id")
        df = df.join(annot_agg, on="frame_id", how="left")
        
        df = df.select(
            "frame_id",
            "clip_id",
            "frame_idx",
            "cameras",
            "lidar_filename",
            "lidar_timestamp",
            "radars",
            "annotations",
        )
        
        return self._write_gold(df, "sensor_fusion_frame", partition_by=["clip_id"])
    
    def build_all(self) -> Dict[str, int]:
        """
        Build all Gold tables.
        
        Returns:
            Dictionary mapping table names to row counts
        """
        builds = [
            ("camera_annotations", self.build_camera_annotations),
            ("lidar_with_ego", self.build_lidar_with_ego),
            ("sensor_fusion_frame", self.build_sensor_fusion_frame),
        ]
        
        results = {}
        for table_name, build_fn in builds:
            try:
                count = build_fn()
                results[table_name] = count
                print(f"[DONE] {self._gold_table(table_name)}: {count} rows")
            except Exception as e:
                print(f"[ERROR] Failed to build {table_name}: {e}")
                results[table_name] = -1
                
        return results


def run_gold_build(config: Optional[PipelineConfig] = None) -> Dict[str, int]:
    """
    Main entry point for Gold layer construction.
    
    Args:
        config: Pipeline configuration (uses defaults if None)
        
    Returns:
        Dictionary mapping table names to row counts
    """
    if config is None:
        config = PipelineConfig()
        
    spark = build_spark_session(config, app_name="kaist-gold-build")
    
    try:
        create_namespaces(spark, config)
        builder = GoldTableBuilder(spark, config)
        return builder.build_all()
    finally:
        spark.stop()


if __name__ == "__main__":
    results = run_gold_build()
    
    print("\n" + "=" * 60)
    print("GOLD BUILD SUMMARY")
    print("=" * 60)
    for table, count in results.items():
        status = "✓" if count >= 0 else "✗"
        print(f"  {status} {table}: {count} rows")
