"""
True zero-copy Bronze registration via Iceberg's add_files() procedure.

Creates Bronze Iceberg tables by registering existing Parquet files
without rewriting any data.  Only Iceberg metadata (manifests, snapshots)
is created.  Works with:

  - FUSE-mounted zip archives (Option 1 — data stays on NFS)
  - S3/MinIO paths (Option 2 — after byte-stream upload)

Since clip_id is now derived at query time by Silver views (via
input_file_name()), Bronze tables no longer need it.  This means ALL
tables — including sensor data — can use add_files() for true zero-copy
registration.

Runs INSIDE the Spark container (via docker exec).

Usage:
    python -m nvidia_ingestion.register_bronze fuse
    python -m nvidia_ingestion.register_bronze s3
    python -m nvidia_ingestion.register_bronze fuse --max-chunks 2
"""

import argparse
import glob
import os
from typing import Dict, List, Optional

from .benchmark import BenchmarkTracker
from .config import NvidiaPipelineConfig, build_spark_session, create_namespaces


# ---------------------------------------------------------------------------
# Table registry
# ---------------------------------------------------------------------------

# Bare parquet files (not in zips) — on NFS directly
BARE_PARQUET_TABLES = {
    "clip_index": "clip_index.parquet",
    "data_collection": "metadata/data_collection.parquet",
    "sensor_presence": "metadata/sensor_presence.parquet",
}

CALIBRATION_TABLES = {
    "camera_intrinsics": "calibration/camera_intrinsics",
    "sensor_extrinsics": "calibration/sensor_extrinsics",
    "vehicle_dimensions": "calibration/vehicle_dimensions",
}


# ---------------------------------------------------------------------------
# Registration engine
# ---------------------------------------------------------------------------

class BronzeRegistrar:
    """Registers Parquet files into Bronze Iceberg tables via add_files().

    True zero-copy: no data is read, deserialized, or rewritten.  Only
    Iceberg manifests and snapshots are created, pointing at the existing
    Parquet files on FUSE or S3.
    """

    def __init__(self, spark, config: NvidiaPipelineConfig,
                 tracker: Optional[BenchmarkTracker] = None):
        self.spark = spark
        self.config = config
        self.cat = config.spark_catalog_name
        self.ns = config.nvidia.namespace_bronze
        self.src = config.nvidia.source_path
        self.tracker = tracker
        self._limit_chunks = config.nvidia.max_zip_chunks or None

    def _full(self, table: str) -> str:
        return f"{self.cat}.{self.ns}.{table}"

    def _register(self, table: str, parquet_uri: str) -> int:
        """Create a table from schema and register files via add_files().

        parquet_uri: a file:// or s3a:// path to a Parquet file or directory.
        """
        full = self._full(table)
        # Create empty table with matching schema
        df = self.spark.read.parquet(parquet_uri)
        df.limit(0).writeTo(full).using("iceberg").tableProperty(
            "format-version", "2"
        ).createOrReplace()
        # Register the actual data files (zero-copy — metadata only)
        self.spark.sql(
            f"CALL {self.cat}.system.add_files("
            f"  table => '{full}',"
            f"  source_table => '`parquet`.`{parquet_uri}`'"
            f")"
        )
        return self.spark.table(full).count()

    def _append_files(self, table: str, parquet_uri: str) -> int:
        """Append additional files to an existing table via add_files()."""
        full = self._full(table)
        self.spark.sql(
            f"CALL {self.cat}.system.add_files("
            f"  table => '{full}',"
            f"  source_table => '`parquet`.`{parquet_uri}`'"
            f")"
        )
        return self.spark.table(full).count()

    # -- Bare Parquet registration ---------------------------------------------

    def register_bare_parquets(self, mode: str = "fuse") -> Dict[str, int]:
        """Register bare Parquet files (not inside zips)."""
        results = {}
        for table, rel_path in BARE_PARQUET_TABLES.items():
            print(f"[REGISTER] {table}")
            if self.tracker:
                self.tracker.begin("bronze", table)

            if mode == "fuse":
                src_path = os.path.join(self.src, rel_path)
                if not os.path.exists(src_path):
                    print(f"  [SKIP] {src_path} not found")
                    results[table] = 0
                    if self.tracker:
                        self.tracker.end()
                    continue
                uri = f"file://{src_path}"
                bytes_in = os.path.getsize(src_path)
            else:
                uri = f"s3a://spark1/nvidia_bronze/{table}/"
                bytes_in = 0

            rows = self._register(table, uri)
            if self.tracker:
                self.tracker.end(rows_out=rows, bytes_in=bytes_in)
            print(f"  [DONE] {self._full(table)}: {rows} rows")
            results[table] = rows
        return results

    # -- Calibration registration ----------------------------------------------

    def register_calibration(self, mode: str = "fuse") -> Dict[str, int]:
        results = {}
        for table, rel_dir in CALIBRATION_TABLES.items():
            print(f"[REGISTER] {table}")
            if self.tracker:
                self.tracker.begin("bronze", table)

            if mode == "fuse":
                src_dir = os.path.join(self.src, rel_dir)
                if not os.path.isdir(src_dir):
                    print(f"  [SKIP] {src_dir} not found")
                    results[table] = 0
                    if self.tracker:
                        self.tracker.end()
                    continue
                uri = f"file://{src_dir}"
                parquets = sorted(glob.glob(os.path.join(src_dir, "*.parquet")))
                bytes_in = sum(os.path.getsize(p) for p in parquets)
            else:
                uri = f"s3a://spark1/nvidia_bronze/{table}/"
                bytes_in = 0

            rows = self._register(table, uri)
            if self.tracker:
                self.tracker.end(rows_out=rows, bytes_in=bytes_in)
            print(f"  [DONE] {self._full(table)}: {rows} rows")
            results[table] = rows
        return results

    # -- FUSE-based sensor registration ----------------------------------------

    def _find_fuse_dirs(self, sensor_subdir: str,
                        fuse_root: str) -> List[str]:
        """Find FUSE-mounted chunk directories for a sensor.

        With ratarmount, the zip contents are exposed under the sensor
        directory directly — e.g. /mnt/nvidia-fuse/radar/sensor_name/
        contains all Parquet files from all zips.
        """
        base = os.path.join(fuse_root, sensor_subdir)
        if not os.path.isdir(base):
            return []
        # ratarmount exposes zip contents flat or in chunk subdirs
        # Check for chunk dirs first
        chunk_dirs = sorted(glob.glob(os.path.join(base, "chunk_*")))
        if chunk_dirs:
            if self._limit_chunks:
                chunk_dirs = chunk_dirs[:self._limit_chunks]
            return chunk_dirs
        # If no chunk dirs, the directory itself may contain Parquets
        if glob.glob(os.path.join(base, "*.parquet")):
            return [base]
        # ratarmount with --recursive may nest by zip filename
        subdirs = sorted(glob.glob(os.path.join(base, "*")))
        actual_dirs = [d for d in subdirs if os.path.isdir(d)]
        if self._limit_chunks and actual_dirs:
            actual_dirs = actual_dirs[:self._limit_chunks]
        return actual_dirs

    def register_fuse_sensor(
        self,
        table: str,
        sensor_subdir: str,
        suffix_filter: str = ".parquet",
        fuse_root: str = "/mnt/nvidia-fuse",
    ) -> int:
        """Register FUSE-mounted sensor Parquets via add_files()."""
        print(f"[REGISTER] {table} (add_files)")
        if self.tracker:
            self.tracker.begin("bronze", table)

        dirs = self._find_fuse_dirs(sensor_subdir, fuse_root)
        if not dirs:
            print(f"  [SKIP] no FUSE data for {sensor_subdir}")
            if self.tracker:
                self.tracker.end()
            return 0

        # Collect all matching Parquet files
        all_files = []
        for d in dirs:
            all_files.extend(sorted(glob.glob(os.path.join(d, f"*{suffix_filter}"))))

        if not all_files:
            print(f"  [SKIP] no {suffix_filter} files found")
            if self.tracker:
                self.tracker.end()
            return 0

        total_bytes = sum(os.path.getsize(f) for f in all_files)

        # Register first directory to create the table
        first_dir = dirs[0]
        first_uri = f"file://{first_dir}"
        rows = self._register(table, first_uri)

        # Append remaining directories
        for d in dirs[1:]:
            uri = f"file://{d}"
            rows = self._append_files(table, uri)

        if self.tracker:
            self.tracker.end(rows_out=rows, bytes_in=total_bytes)
        print(f"  [DONE] {self._full(table)}: {rows} rows ({len(dirs)} dirs)")
        return rows

    # -- S3-based sensor registration ------------------------------------------

    def register_s3_sensor(self, table: str, s3_prefix: str) -> int:
        """Register sensor Parquets from S3 via add_files()."""
        print(f"[REGISTER] {table} (add_files, S3)")
        if self.tracker:
            self.tracker.begin("bronze", table)

        s3_uri = f"s3a://spark1/{s3_prefix}"
        rows = self._register(table, s3_uri)

        if self.tracker:
            self.tracker.end(rows_out=rows)
        print(f"  [DONE] {self._full(table)}: {rows} rows")
        return rows

    # -- Full registration orchestrators ----------------------------------------

    def register_all_fuse(self, fuse_root: str = "/mnt/nvidia-fuse") -> Dict[str, int]:
        """Register all Bronze tables from FUSE-mounted sources."""
        results = {}

        # Bare Parquets (directly on NFS)
        results.update(self.register_bare_parquets(mode="fuse"))

        # Calibration directories
        results.update(self.register_calibration(mode="fuse"))

        # Egomotion
        results["egomotion"] = self.register_fuse_sensor(
            "egomotion", "labels/egomotion", fuse_root=fuse_root,
        )

        # Lidar
        results["lidar"] = self.register_fuse_sensor(
            "lidar", "lidar/lidar_top_360fov", fuse_root=fuse_root,
        )

        # Radar (discover sensors dynamically)
        radar_root = os.path.join(fuse_root, "radar")
        if os.path.isdir(radar_root):
            for sensor in sorted(os.listdir(radar_root)):
                sensor_path = os.path.join(radar_root, sensor)
                if os.path.isdir(sensor_path):
                    safe = sensor.replace("-", "_")
                    results[f"radar_{safe}"] = self.register_fuse_sensor(
                        f"radar_{safe}", f"radar/{sensor}",
                        fuse_root=fuse_root,
                    )

        # Camera metadata (timestamps + blur boxes)
        cam_root = os.path.join(fuse_root, "camera")
        if os.path.isdir(cam_root):
            for sensor in sorted(os.listdir(cam_root)):
                sensor_path = os.path.join(cam_root, sensor)
                if os.path.isdir(sensor_path):
                    safe = sensor.replace("-", "_")
                    results[f"cam_{safe}_ts"] = self.register_fuse_sensor(
                        f"cam_{safe}_ts", f"camera/{sensor}",
                        suffix_filter=".timestamps.parquet",
                        fuse_root=fuse_root,
                    )
                    results[f"cam_{safe}_blur"] = self.register_fuse_sensor(
                        f"cam_{safe}_blur", f"camera/{sensor}",
                        suffix_filter=".blurred_boxes.parquet",
                        fuse_root=fuse_root,
                    )

        return results

    def register_all_s3(self, s3_prefix: str = "nvidia_bronze") -> Dict[str, int]:
        """Register all Bronze tables from S3 paths (after upload)."""
        results = {}

        results.update(self.register_bare_parquets(mode="s3"))
        results.update(self.register_calibration(mode="s3"))

        # Discover uploaded sensor tables from S3
        s3_base = f"s3a://spark1/{s3_prefix}"
        try:
            hadoop_conf = self.spark._jsc.hadoopConfiguration()
            fs_class = self.spark._jvm.org.apache.hadoop.fs.FileSystem
            uri_class = self.spark._jvm.java.net.URI
            fs = fs_class.get(uri_class(s3_base), hadoop_conf)
            path_class = self.spark._jvm.org.apache.hadoop.fs.Path
            statuses = fs.listStatus(path_class(s3_base))
            subdirs = [s.getPath().getName() for s in statuses if s.isDirectory()]
        except Exception:
            subdirs = []

        skip = set(BARE_PARQUET_TABLES) | set(CALIBRATION_TABLES)
        for table_dir in sorted(subdirs):
            if table_dir in skip:
                continue
            results[table_dir] = self.register_s3_sensor(
                table_dir, f"{s3_prefix}/{table_dir}/",
            )

        return results


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def run_fuse_registration(
    config: Optional[NvidiaPipelineConfig] = None,
    tracker: Optional[BenchmarkTracker] = None,
    fuse_root: str = "/mnt/nvidia-fuse",
) -> Dict[str, int]:
    if config is None:
        config = NvidiaPipelineConfig()
    spark = build_spark_session(config, app_name="nvidia-register-fuse")
    try:
        create_namespaces(spark, config)
        reg = BronzeRegistrar(spark, config, tracker=tracker)
        return reg.register_all_fuse(fuse_root=fuse_root)
    finally:
        spark.stop()


def run_s3_registration(
    config: Optional[NvidiaPipelineConfig] = None,
    tracker: Optional[BenchmarkTracker] = None,
    s3_prefix: str = "nvidia_bronze",
) -> Dict[str, int]:
    if config is None:
        config = NvidiaPipelineConfig()
    spark = build_spark_session(config, app_name="nvidia-register-s3")
    try:
        create_namespaces(spark, config)
        reg = BronzeRegistrar(spark, config, tracker=tracker)
        return reg.register_all_s3(s3_prefix=s3_prefix)
    finally:
        spark.stop()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Zero-copy Bronze registration via Iceberg add_files()"
    )
    parser.add_argument(
        "mode", choices=["fuse", "s3"],
        help="Registration source: fuse (FUSE-mounted zips) or s3 (MinIO)"
    )
    parser.add_argument("--max-chunks", type=int, default=0)
    parser.add_argument("--fuse-root", default="/mnt/nvidia-fuse")
    parser.add_argument("--s3-prefix", default="nvidia_bronze")
    args = parser.parse_args()

    cfg = NvidiaPipelineConfig()
    if args.max_chunks:
        cfg.nvidia.max_zip_chunks = args.max_chunks

    tracker = BenchmarkTracker(f"nvidia-register-{args.mode}")

    if args.mode == "fuse":
        results = run_fuse_registration(cfg, tracker, fuse_root=args.fuse_root)
    else:
        results = run_s3_registration(cfg, tracker, s3_prefix=args.s3_prefix)

    tracker.print_summary()
    tracker.flush()

    print(f"\n{'=' * 60}")
    print(f"BRONZE REGISTRATION SUMMARY ({args.mode.upper()})")
    print(f"{'=' * 60}")
    for table, count in results.items():
        status = "+" if count > 0 else "-"
        print(f"  {status} {table}: {count} rows")


if __name__ == "__main__":
    main()
