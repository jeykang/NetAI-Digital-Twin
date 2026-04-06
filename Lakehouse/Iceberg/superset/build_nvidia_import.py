#!/usr/bin/env python3
"""
Build a Superset import ZIP bundle for the Nvidia PhysicalAI dashboard,
then import it via the /api/v1/dashboard/import/ endpoint.

This is the reliable way to create dashboards with properly linked charts.
"""

import io
import json
import uuid
import zipfile

import requests
import yaml

SUPERSET_URL = "http://localhost:8088"
USERNAME = "admin"
PASSWORD = "admin"

# Fixed UUIDs so re-imports overwrite rather than duplicate (uuid5-derived)
DB_UUID = "ee777ec4-517c-4386-92af-21cc43684489"  # existing Trino connection
DASH_UUID = "f7b2c747-dca1-5cfb-8b75-c68c141dbeec"

PREFIX = "dashboard_export"


def make_uuid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Dataset definitions (virtual SQL)
# ---------------------------------------------------------------------------

DATASETS = {
    "clip_overview": {
        "uuid": "3487d6cb-5dd6-5319-a488-73d02408d5f7",
        "table_name": "Clip Overview (Gold)",
        "schema": "nvidia_gold_blob",
        "catalog": "iceberg",
        "sql": r"""
SELECT
    split,
    country,
    month,
    hour_of_day,
    platform_class,
    clip_is_valid,
    radar_config,
    length  AS vehicle_length,
    width   AS vehicle_width,
    height  AS vehicle_height,
    wheelbase,
    CAST(camera_cross_left_120fov   AS INTEGER)
  + CAST(camera_cross_right_120fov  AS INTEGER)
  + CAST(camera_front_tele_30fov    AS INTEGER)
  + CAST(camera_front_wide_120fov   AS INTEGER)
  + CAST(camera_rear_left_70fov     AS INTEGER)
  + CAST(camera_rear_right_70fov    AS INTEGER)
  + CAST(camera_rear_tele_30fov     AS INTEGER) AS num_cameras,
    CAST(lidar_top_360fov AS INTEGER)           AS has_lidar,
    CAST(radar_corner_front_left_srr_0  AS INTEGER)
  + CAST(radar_corner_front_left_srr_3  AS INTEGER)
  + CAST(radar_corner_front_right_srr_0 AS INTEGER)
  + CAST(radar_corner_front_right_srr_3 AS INTEGER)
  + CAST(radar_corner_rear_left_srr_0   AS INTEGER)
  + CAST(radar_corner_rear_left_srr_3   AS INTEGER)
  + CAST(radar_corner_rear_right_srr_0  AS INTEGER)
  + CAST(radar_corner_rear_right_srr_3  AS INTEGER)
  + CAST(radar_front_center_imaging_lrr_1 AS INTEGER)
  + CAST(radar_front_center_mrr_2       AS INTEGER)
  + CAST(radar_front_center_srr_0       AS INTEGER)
  + CAST(radar_rear_left_mrr_2          AS INTEGER)
  + CAST(radar_rear_left_srr_0          AS INTEGER)
  + CAST(radar_rear_right_mrr_2         AS INTEGER)
  + CAST(radar_rear_right_srr_0         AS INTEGER)
  + CAST(radar_side_left_srr_0          AS INTEGER)
  + CAST(radar_side_left_srr_3          AS INTEGER)
  + CAST(radar_side_right_srr_0         AS INTEGER)
  + CAST(radar_side_right_srr_3         AS INTEGER) AS num_radars
FROM iceberg.nvidia_gold_blob.sensor_fusion_clip
""",
    },
    "radar_detections": {
        "uuid": "c1fe829b-7f37-565e-9b4d-766459500ca1",
        "table_name": "Radar Detections (Gold)",
        "schema": "nvidia_gold_blob",
        "catalog": "iceberg",
        "sql": r"""
SELECT
    clip_id, sensor_name, timestamp,
    azimuth, elevation, distance, radial_velocity, rcs, snr,
    num_returns, detection_index, ego_sample_count,
    CASE
        WHEN distance < 25  THEN '0-25 m'
        WHEN distance < 50  THEN '25-50 m'
        WHEN distance < 100 THEN '50-100 m'
        WHEN distance < 200 THEN '100-200 m'
        ELSE '200+ m'
    END AS range_bucket,
    CASE
        WHEN sensor_name LIKE '%lrr%' THEN 'LRR (Long Range)'
        WHEN sensor_name LIKE '%mrr%' THEN 'MRR (Mid Range)'
        WHEN sensor_name LIKE '%srr_0%' THEN 'SRR Mode-0'
        WHEN sensor_name LIKE '%srr_3%' THEN 'SRR Mode-3'
        ELSE 'Other'
    END AS radar_type,
    CASE
        WHEN sensor_name LIKE '%front_center%' THEN 'Front Center'
        WHEN sensor_name LIKE '%front_left%'   THEN 'Front Left'
        WHEN sensor_name LIKE '%front_right%'  THEN 'Front Right'
        WHEN sensor_name LIKE '%rear_left%'    THEN 'Rear Left'
        WHEN sensor_name LIKE '%rear_right%'   THEN 'Rear Right'
        WHEN sensor_name LIKE '%side_left%'    THEN 'Side Left'
        WHEN sensor_name LIKE '%side_right%'   THEN 'Side Right'
        ELSE 'Unknown'
    END AS radar_position
FROM iceberg.nvidia_gold_blob.radar_ego_fusion
""",
    },
    "ego_motion": {
        "uuid": "36bd5027-73ad-5f33-a3b1-aa15f9f97997",
        "table_name": "Ego-Motion Dynamics (Silver)",
        "schema": "nvidia_silver_blob",
        "catalog": "iceberg",
        "sql": r"""
SELECT
    clip_id, timestamp,
    x, y, z, qw, qx, qy, qz,
    vx, vy, vz, ax, ay, az, curvature,
    SQRT(vx*vx + vy*vy + vz*vz)       AS speed,
    SQRT(ax*ax + ay*ay + az*az)        AS total_accel,
    SQRT(vx*vx + vy*vy + vz*vz) * 3.6 AS speed_kmh,
    ABS(curvature)                      AS abs_curvature
FROM iceberg.nvidia_silver_blob.egomotion
""",
    },
    "layer_counts": {
        "uuid": "ae2f025a-b372-532a-8bbd-5a203dad1d1b",
        "table_name": "Lakehouse Layer Row Counts",
        "schema": "nvidia_bronze_blob",
        "catalog": "iceberg",
        "sql": r"""
SELECT 'Bronze' AS layer, 'clip_index' AS tbl, COUNT(*) AS row_count FROM iceberg.nvidia_bronze_blob.clip_index
UNION ALL SELECT 'Bronze', 'egomotion', COUNT(*) FROM iceberg.nvidia_bronze_blob.egomotion
UNION ALL SELECT 'Bronze', 'camera_intrinsics', COUNT(*) FROM iceberg.nvidia_bronze_blob.camera_intrinsics
UNION ALL SELECT 'Bronze', 'sensor_extrinsics', COUNT(*) FROM iceberg.nvidia_bronze_blob.sensor_extrinsics
UNION ALL SELECT 'Bronze', 'sensor_presence', COUNT(*) FROM iceberg.nvidia_bronze_blob.sensor_presence
UNION ALL SELECT 'Bronze', 'data_collection', COUNT(*) FROM iceberg.nvidia_bronze_blob.data_collection
UNION ALL SELECT 'Bronze', 'vehicle_dimensions', COUNT(*) FROM iceberg.nvidia_bronze_blob.vehicle_dimensions
UNION ALL SELECT 'Bronze', 'lidar', COUNT(*) FROM iceberg.nvidia_bronze_blob.lidar
UNION ALL SELECT 'Silver', 'clip_index', COUNT(*) FROM iceberg.nvidia_silver_blob.clip_index
UNION ALL SELECT 'Silver', 'egomotion', COUNT(*) FROM iceberg.nvidia_silver_blob.egomotion
UNION ALL SELECT 'Silver', 'camera_intrinsics', COUNT(*) FROM iceberg.nvidia_silver_blob.camera_intrinsics
UNION ALL SELECT 'Silver', 'sensor_extrinsics', COUNT(*) FROM iceberg.nvidia_silver_blob.sensor_extrinsics
UNION ALL SELECT 'Silver', 'sensor_presence', COUNT(*) FROM iceberg.nvidia_silver_blob.sensor_presence
UNION ALL SELECT 'Silver', 'data_collection', COUNT(*) FROM iceberg.nvidia_silver_blob.data_collection
UNION ALL SELECT 'Silver', 'vehicle_dimensions', COUNT(*) FROM iceberg.nvidia_silver_blob.vehicle_dimensions
UNION ALL SELECT 'Silver', 'lidar', COUNT(*) FROM iceberg.nvidia_silver_blob.lidar
UNION ALL SELECT 'Gold', 'sensor_fusion_clip', COUNT(*) FROM iceberg.nvidia_gold_blob.sensor_fusion_clip
UNION ALL SELECT 'Gold', 'lidar_with_ego', COUNT(*) FROM iceberg.nvidia_gold_blob.lidar_with_ego
UNION ALL SELECT 'Gold', 'radar_ego_fusion', COUNT(*) FROM iceberg.nvidia_gold_blob.radar_ego_fusion
""",
    },
    "radar_stats": {
        "uuid": "3b452575-ffec-50d8-bcd7-fac172cf14fa",
        "table_name": "Radar Sensor Statistics",
        "schema": "nvidia_gold_blob",
        "catalog": "iceberg",
        "sql": r"""
SELECT
    sensor_name,
    COUNT(*)                  AS detection_count,
    ROUND(AVG(distance), 2)   AS avg_distance_m,
    ROUND(AVG(radial_velocity), 2) AS avg_radial_vel,
    ROUND(AVG(rcs), 2)        AS avg_rcs_dbsm,
    ROUND(AVG(snr), 2)        AS avg_snr_db,
    ROUND(STDDEV(distance), 2) AS std_distance,
    ROUND(MIN(distance), 2)   AS min_distance,
    ROUND(MAX(distance), 2)   AS max_distance,
    CASE
        WHEN sensor_name LIKE '%lrr%' THEN 'LRR'
        WHEN sensor_name LIKE '%mrr%' THEN 'MRR'
        ELSE 'SRR'
    END AS radar_type,
    CASE
        WHEN sensor_name LIKE '%front_center%' THEN 'Front Center'
        WHEN sensor_name LIKE '%front_left%'   THEN 'Front Left'
        WHEN sensor_name LIKE '%front_right%'  THEN 'Front Right'
        WHEN sensor_name LIKE '%rear_left%'    THEN 'Rear Left'
        WHEN sensor_name LIKE '%rear_right%'   THEN 'Rear Right'
        WHEN sensor_name LIKE '%side_left%'    THEN 'Side Left'
        WHEN sensor_name LIKE '%side_right%'   THEN 'Side Right'
        ELSE 'Unknown'
    END AS radar_position
FROM iceberg.nvidia_gold_blob.radar_ego_fusion
GROUP BY sensor_name
""",
    },
}


# ---------------------------------------------------------------------------
# Chart definitions  (key -> yaml dict)
# ---------------------------------------------------------------------------

def _metric(col, agg, label):
    return {"expressionType": "SIMPLE",
            "column": {"column_name": col}, "aggregate": agg, "label": label}


CHARTS = [
    # -- KPI row --
    {"key": "total_clips", "uuid": "2830ed10-bb68-5aa5-b29c-fe947a1bccc7",
     "slice_name": "Total Clips", "viz_type": "big_number_total",
     "dataset_key": "clip_overview",
     "params": {"viz_type": "big_number_total",
                "metric": _metric("split", "COUNT", "Total Clips"),
                "header_font_size": 0.3, "subheader_font_size": 0.15}},

    {"key": "total_countries", "uuid": "907a2b07-7a11-55e8-a7cf-284b9cbea5f9",
     "slice_name": "Total Countries", "viz_type": "big_number_total",
     "dataset_key": "clip_overview",
     "params": {"viz_type": "big_number_total",
                "metric": _metric("country", "COUNT_DISTINCT", "Countries"),
                "header_font_size": 0.3, "subheader_font_size": 0.15}},

    {"key": "total_radar", "uuid": "39ae9236-9746-5a00-b6c3-7e50c8dffddb",
     "slice_name": "Total Radar Detections", "viz_type": "big_number_total",
     "dataset_key": "radar_stats",
     "params": {"viz_type": "big_number_total",
                "metric": _metric("detection_count", "SUM", "Radar Detections"),
                "header_font_size": 0.3, "subheader_font_size": 0.15}},

    {"key": "radar_sensors", "uuid": "51f1796a-990a-52e2-82d8-e5cd3c59f472",
     "slice_name": "Radar Sensors", "viz_type": "big_number_total",
     "dataset_key": "radar_stats",
     "params": {"viz_type": "big_number_total",
                "metric": _metric("sensor_name", "COUNT", "Radar Sensors"),
                "header_font_size": 0.3, "subheader_font_size": 0.15}},

    # -- Geographic & temporal --
    {"key": "clips_country", "uuid": "63c9cdcd-182e-5840-9459-ac7ea89c3be7",
     "slice_name": "Clips by Country", "viz_type": "echarts_timeseries_bar",
     "dataset_key": "clip_overview",
     "params": {"viz_type": "echarts_timeseries_bar", "x_axis": "country",
                "metrics": [_metric("country", "COUNT", "Clip Count")],
                "groupby": [], "order_desc": True, "row_limit": 25,
                "truncate_metric": True, "show_legend": False,
                "rich_tooltip": True, "color_scheme": "supersetColors"}},

    {"key": "heatmap_time", "uuid": "33f15689-3d3f-5288-a9e5-26a42bad85ba",
     "slice_name": "Collection Time Heatmap (Month x Hour)", "viz_type": "heatmap",
     "dataset_key": "clip_overview",
     "params": {"viz_type": "heatmap", "all_columns_x": "month",
                "all_columns_y": "hour_of_day",
                "metric": _metric("month", "COUNT", "count"),
                "linear_color_scheme": "blue_white_yellow",
                "xscale_interval": 1, "yscale_interval": 1,
                "normalize_across": "heatmap", "show_legend": True,
                "show_perc": True, "show_values": False, "row_limit": 300}},

    # -- Split & platform --
    {"key": "split_pie", "uuid": "f999b4d4-1310-5bb7-a052-bac444c96bf8",
     "slice_name": "Train / Val / Test Split", "viz_type": "pie",
     "dataset_key": "clip_overview",
     "params": {"viz_type": "pie", "groupby": ["split"],
                "metric": _metric("split", "COUNT", "count"),
                "color_scheme": "supersetColors", "show_labels": True,
                "label_type": "key_percent", "show_legend": True,
                "innerRadius": 40, "outerRadius": 80, "row_limit": 10}},

    {"key": "platform_pie", "uuid": "e405aafa-0316-50ff-a087-30db6ef9c6d4",
     "slice_name": "Platform Class Distribution", "viz_type": "pie",
     "dataset_key": "clip_overview",
     "params": {"viz_type": "pie", "groupby": ["platform_class"],
                "metric": _metric("platform_class", "COUNT", "count"),
                "color_scheme": "supersetColors", "show_labels": True,
                "label_type": "key_percent", "show_legend": True, "row_limit": 10}},

    {"key": "camera_avail", "uuid": "45ad22c3-f886-5f6a-8808-043cba976cc2",
     "slice_name": "Camera Availability Across Clips", "viz_type": "dist_bar",
     "dataset_key": "clip_overview",
     "params": {"viz_type": "dist_bar", "groupby": ["num_cameras"],
                "metrics": [_metric("num_cameras", "COUNT", "Clip Count")],
                "columns": ["split"], "color_scheme": "supersetColors",
                "show_legend": True, "y_axis_format": ",d", "row_limit": 20}},

    # -- Radar overview --
    {"key": "radar_volume", "uuid": "1bcad982-b389-5da0-8d30-5226f31a1bcc",
     "slice_name": "Radar Detection Volume by Sensor", "viz_type": "dist_bar",
     "dataset_key": "radar_stats",
     "params": {"viz_type": "dist_bar", "groupby": ["sensor_name"],
                "metrics": [_metric("detection_count", "SUM", "Total Detections")],
                "columns": [], "color_scheme": "supersetColors",
                "show_legend": False, "y_axis_format": ",d",
                "order_bars": True, "row_limit": 25}},

    {"key": "radar_range_pie", "uuid": "bfb498f1-caf9-5b30-af97-4d8ba1e0f51a",
     "slice_name": "Radar Detection Range Distribution", "viz_type": "pie",
     "dataset_key": "radar_detections",
     "params": {"viz_type": "pie", "groupby": ["range_bucket"],
                "metric": _metric("range_bucket", "COUNT", "Detections"),
                "color_scheme": "supersetColors", "show_labels": True,
                "label_type": "key_percent", "show_legend": True, "row_limit": 10}},

    # -- Radar analysis --
    {"key": "radar_dist_type", "uuid": "bcc01c6f-ef40-5d37-9216-6cfe5ee4c124",
     "slice_name": "Avg Detection Distance by Radar Type", "viz_type": "dist_bar",
     "dataset_key": "radar_stats",
     "params": {"viz_type": "dist_bar", "groupby": ["radar_position"],
                "metrics": [_metric("avg_distance_m", "AVG", "Avg Distance (m)")],
                "columns": ["radar_type"], "color_scheme": "supersetColors",
                "show_legend": True, "y_axis_format": ",.1f", "row_limit": 50}},

    {"key": "radar_rcs_scatter", "uuid": "71b75bb1-f108-596c-9ea6-30c8f5eac5de",
     "slice_name": "Radar RCS vs Distance (sampled)", "viz_type": "echarts_timeseries_scatter",
     "dataset_key": "radar_detections",
     "params": {"viz_type": "echarts_timeseries_scatter", "x_axis": "distance",
                "metrics": [_metric("rcs", "AVG", "Avg RCS (dBsm)")],
                "groupby": ["radar_type"], "color_scheme": "supersetColors",
                "show_legend": True, "row_limit": 5000,
                "truncate_metric": True, "rich_tooltip": True}},

    # -- Ego dynamics --
    {"key": "ego_speed", "uuid": "c62120f6-4865-50fd-b3cf-84d55a4a1b09",
     "slice_name": "Ego Vehicle Speed Distribution", "viz_type": "histogram_v2",
     "dataset_key": "ego_motion",
     "params": {"viz_type": "histogram_v2", "all_columns_x": ["speed_kmh"],
                "color_scheme": "supersetColors", "normalize": False,
                "cumulative": False, "row_limit": 50000}},

    {"key": "ego_accel_curv", "uuid": "d58347bc-b2c9-5344-90c8-de462d46caca",
     "slice_name": "Acceleration vs Curvature", "viz_type": "bubble_v2",
     "dataset_key": "ego_motion",
     "params": {"viz_type": "bubble_v2",
                "x": _metric("abs_curvature", "AVG", "Avg |Curvature|"),
                "y": _metric("total_accel", "AVG", "Avg Total Accel"),
                "size": _metric("speed_kmh", "AVG", "Avg Speed (km/h)"),
                "entity": "clip_id", "color_scheme": "supersetColors",
                "show_legend": True, "max_bubble_size": 50, "row_limit": 50000}},

    # -- Architecture --
    {"key": "medallion_bar", "uuid": "67298aab-ee44-5587-8949-3ac5343b32ba",
     "slice_name": "Medallion Architecture: Row Counts", "viz_type": "dist_bar",
     "dataset_key": "layer_counts",
     "params": {"viz_type": "dist_bar", "groupby": ["tbl"],
                "metrics": [_metric("row_count", "SUM", "Rows")],
                "columns": ["layer"], "color_scheme": "supersetColors",
                "show_legend": True, "y_axis_format": ",d", "row_limit": 50}},

    {"key": "country_split_heat", "uuid": "00f7c7fa-5827-513b-a3aa-def4dca61e51",
     "slice_name": "Country x Split Coverage", "viz_type": "heatmap",
     "dataset_key": "clip_overview",
     "params": {"viz_type": "heatmap", "all_columns_x": "split",
                "all_columns_y": "country",
                "metric": _metric("split", "COUNT", "count"),
                "linear_color_scheme": "blue_white_yellow",
                "normalize_across": "y", "show_legend": True,
                "show_perc": True, "show_values": True, "row_limit": 300}},
]


# ---------------------------------------------------------------------------
# Dashboard layout rows
# ---------------------------------------------------------------------------

LAYOUT_ROWS = [
    [("total_clips", 3), ("total_countries", 3), ("total_radar", 3), ("radar_sensors", 3)],
    [("clips_country", 6), ("heatmap_time", 6)],
    [("split_pie", 4), ("platform_pie", 4), ("camera_avail", 4)],
    [("radar_volume", 6), ("radar_range_pie", 6)],
    [("radar_dist_type", 6), ("radar_rcs_scatter", 6)],
    [("ego_speed", 6), ("ego_accel_curv", 6)],
    [("medallion_bar", 6), ("country_split_heat", 6)],
]


# ---------------------------------------------------------------------------
# Build the ZIP
# ---------------------------------------------------------------------------

def dataset_filename(ds):
    safe = ds["table_name"].replace(" ", "_").replace("(", "").replace(")", "")
    return f"datasets/Trino/{safe}.yaml"


def chart_filename(ch):
    safe = ch["slice_name"].replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
    return f"charts/{safe}.yaml"


def build_dataset_yaml(ds):
    return {
        "table_name": ds["table_name"],
        "main_dttm_col": None,
        "description": None,
        "default_endpoint": None,
        "offset": 0,
        "cache_timeout": None,
        "catalog": ds["catalog"],
        "schema": ds["schema"],
        "sql": ds["sql"],
        "params": None,
        "template_params": None,
        "filter_select_enabled": True,
        "fetch_values_predicate": None,
        "extra": None,
        "normalize_columns": False,
        "always_filter_main_dttm": False,
        "uuid": ds["uuid"],
        "metrics": [],
        "columns": [],
        "database_uuid": DB_UUID,
        "version": "1.0.0",
    }


def build_chart_yaml(ch, ds):
    return {
        "slice_name": ch["slice_name"],
        "description": None,
        "certified_by": None,
        "certification_details": None,
        "viz_type": ch["viz_type"],
        "params": ch["params"],
        "query_context": None,
        "cache_timeout": None,
        "uuid": ch["uuid"],
        "version": "1.0.0",
        "dataset_uuid": ds["uuid"],
    }


def build_dashboard_yaml(chart_list):
    # Build position_json
    chart_by_key = {ch["key"]: ch for ch in chart_list}

    components = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [],
                     "parents": ["ROOT_ID"]},
        "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID",
                       "meta": {"text": "Nvidia PhysicalAI AV Dataset"}},
    }

    for row_idx, row_charts in enumerate(LAYOUT_ROWS):
        row_id = f"ROW-nvidia-r{row_idx}"
        components[row_id] = {
            "type": "ROW", "id": row_id, "children": [],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"0": "ROOT_ID", "background": "BACKGROUND_TRANSPARENT"},
        }
        components["GRID_ID"]["children"].append(row_id)

        for chart_key, width in row_charts:
            ch = chart_by_key[chart_key]
            chart_comp_id = f"CHART-{ch['uuid']}"
            height = 20 if row_idx == 0 else 50

            components[chart_comp_id] = {
                "type": "CHART", "id": chart_comp_id, "children": [],
                "parents": ["ROOT_ID", "GRID_ID", row_id],
                "meta": {
                    "chartId": ch["uuid"],
                    "width": width,
                    "height": height,
                    "sliceName": ch["slice_name"],
                    "uuid": ch["uuid"],
                },
            }
            components[row_id]["children"].append(chart_comp_id)

    return {
        "dashboard_title": "Nvidia PhysicalAI AV Dataset",
        "description": None,
        "css": None,
        "slug": "nvidia-physicalai",
        "uuid": DASH_UUID,
        "position": components,
        "metadata": {
            "color_scheme_domain": [],
            "shared_label_colors": {},
            "map_label_colors": {},
            "label_colors": {},
        },
        "version": "1.0.0",
    }


def build_db_yaml():
    return {
        "database_name": "Trino",
        "sqlalchemy_uri": "trino://admin@trino:8080/iceberg",
        "cache_timeout": None,
        "expose_in_sqllab": True,
        "allow_run_async": False,
        "allow_ctas": False,
        "allow_cvas": False,
        "allow_dml": False,
        "allow_file_upload": False,
        "extra": {"allows_virtual_table_explore": True},
        "impersonate_user": False,
        "uuid": DB_UUID,
        "version": "1.0.0",
    }


def build_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # metadata.yaml
        meta = {"version": "1.0.0", "type": "Dashboard",
                "timestamp": "2026-03-20T00:00:00.000000+00:00"}
        zf.writestr(f"{PREFIX}/metadata.yaml",
                     yaml.dump(meta, default_flow_style=False) + "\n")

        # database
        zf.writestr(f"{PREFIX}/databases/Trino.yaml",
                     yaml.dump(build_db_yaml(), default_flow_style=False) + "\n")

        # datasets
        for ds_key, ds in DATASETS.items():
            content = yaml.dump(build_dataset_yaml(ds), default_flow_style=False)
            zf.writestr(f"{PREFIX}/{dataset_filename(ds)}", content + "\n")

        # charts
        for ch in CHARTS:
            ds = DATASETS[ch["dataset_key"]]
            content = yaml.dump(build_chart_yaml(ch, ds), default_flow_style=False)
            zf.writestr(f"{PREFIX}/{chart_filename(ch)}", content + "\n")

        # dashboard
        dash = build_dashboard_yaml(CHARTS)
        content = yaml.dump(dash, default_flow_style=False)
        zf.writestr(f"{PREFIX}/dashboards/Nvidia_PhysicalAI_AV_Dataset.yaml",
                     content + "\n")

    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Nvidia PhysicalAI — Superset Dashboard Import")
    print("=" * 60)

    # Build ZIP
    print("\n[1/2] Building import bundle …")
    zip_buf = build_zip()
    zip_bytes = zip_buf.getvalue()
    print(f"  ZIP size: {len(zip_bytes):,} bytes")

    # Save a copy for debugging
    with open("superset/nvidia_dashboard_bundle.zip", "wb") as f:
        f.write(zip_bytes)
    print("  Saved to superset/nvidia_dashboard_bundle.zip")

    # Import via API
    print("\n[2/2] Importing via Superset API …")
    S = requests.Session()
    r = S.post(f"{SUPERSET_URL}/api/v1/security/login", json={
        "username": USERNAME, "password": PASSWORD,
        "provider": "db", "refresh": True,
    })
    token = r.json()["access_token"]
    S.headers["Authorization"] = f"Bearer {token}"

    r = S.get(f"{SUPERSET_URL}/api/v1/security/csrf_token/")
    csrf = r.json()["result"]
    S.headers.update({"X-CSRFToken": csrf, "Referer": SUPERSET_URL})

    # Remove Content-Type so requests sets multipart boundary automatically
    zip_buf.seek(0)
    r = S.post(
        f"{SUPERSET_URL}/api/v1/dashboard/import/",
        files={"formData": ("nvidia_dashboard.zip", zip_buf, "application/zip")},
        data={"overwrite": "true"},
    )
    print(f"  Import status: {r.status_code}")
    if r.status_code >= 400:
        print(f"  Response: {r.text[:1000]}")
    else:
        print(f"  Response: {r.json()}")

    print(f"\n  Dashboard URL: {SUPERSET_URL}/superset/dashboard/nvidia-physicalai/")
    print("=" * 60)


if __name__ == "__main__":
    main()
