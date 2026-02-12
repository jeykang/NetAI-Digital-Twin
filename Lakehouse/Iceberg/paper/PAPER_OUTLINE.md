# Paper Outline: Domain-Specific Data Lakehouse Architecture for Autonomous Driving Datasets

> **Target venue:** Domestic conference (low-stakes)
> **Estimated length:** 6–8 pages (IEEE-style two-column)
> **Due:** ~end of February 2026
>
> **Confidentiality note:** All content based on publicly available datasets
> (nuScenes, nuPlan) and our own architectural design. The extended 3-level
> schema is presented as our *proposed* generalization for production-scale
> AD data — no private dataset details are disclosed.

---

## Title (working)

**A Medallion-Architecture Data Lakehouse for Multi-Modal Autonomous Driving Data Management**

---

## Abstract

*~150 words. Problem → approach → key result.*

---

## I. Introduction

### I-A. Problem Statement
- Explosive growth of autonomous driving datasets (camera, LiDAR, radar) — TB to PB scale
- Current practice: ad-hoc Python scripts with nested-loop JSON parsing; no schema enforcement, no ACID, no lineage
- Gap: no open-standard lakehouse architecture specifically designed for the access patterns of AD data

### I-B. Contributions
1. A medallion-architecture (Bronze/Silver/Gold) data lakehouse tailored to multi-modal AD sensor data
2. Domain-aware partitioning and schema design aligned with ML training access patterns
3. Workload-specific Gold table designs for object detection, SLAM, and sensor fusion
4. Quantitative evaluation on the public nuScenes dataset demonstrating up to 14× query speedup over baseline approaches

| **Figure/Table** | **Description** | **Source in codebase** |
|---|---|---|
| — | *(none in this section)* | — |

---

## II. Background and Related Work

### II-A. Data Lakehouses and Open Table Formats
- Delta Lake, Apache Iceberg, Apache Hudi — convergence of warehouse + lake
- Iceberg v2: hidden partitioning, schema evolution, time travel, partition pruning

### II-B. Autonomous Driving Datasets
- nuScenes (2-level: Scene → Sample), nuPlan (~20 TB full) — public benchmarks
- Common characteristics across AD datasets: multi-modal, hierarchical, append-only, sensor-centric access
- Limitations of nuScenes' 2-level hierarchy when scaling to long-duration, multi-session recordings

### II-C. Medallion Architecture
- Bronze (raw) → Silver (cleaned/partitioned) → Gold (denormalized, ML-ready) pattern
- Prior applications in enterprise BI; limited adoption in scientific/ML data management

| **Figure/Table** | **Description** | **Source in codebase** |
|---|---|---|
| **Table I** | Comparison of AD dataset structural patterns: 2-level (nuScenes-style) vs. proposed 3-level (Session → Clip → Frame) hierarchy — differences in sensor layout, calibration scope, annotation types | Generalized from `kaist_ingestion/KAIST_INGESTION_PLAN.md` §1.2 (with private names removed) |

---

## III. System Architecture

### III-A. Infrastructure Overview

- Five-service stack: Spark (ETL), Polaris (REST catalog), MinIO/Ceph (S3 storage), Trino (SQL), Superset (BI)
- All services share a single Iceberg catalog → unified metadata for both batch ETL and interactive SQL

| **Figure/Table** | **Description** | **Source in codebase** |
|---|---|---|
| **Fig. 1** | System architecture diagram — layered view: Query Layer (Trino, Spark, Superset) → Catalog Layer (Polaris REST) → Table Format (Iceberg v2) → Storage (MinIO → Ceph) | Redraw from ASCII art in `docker-compose.yml` service topology |

### III-B. Proposed Data Model: Extended AD Entity Relationships

- Motivation: nuScenes' 2-level hierarchy (Scene → Sample) is insufficient for production-scale recordings with long sessions, multiple driving clips, and per-clip calibration
- **Proposed 3-level hierarchy**: Session → Clip → Frame → Sensors + Annotations
- 14 entity types: session, clip, frame, camera, lidar, radar, calibration, dynamic_object, occupancy, motion, ego_motion, session_ego_motion, hdmap, category
- Design informed by common patterns across public AD datasets (nuScenes, nuPlan, Waymo Open)

| **Figure/Table** | **Description** | **Source in codebase** |
|---|---|---|
| **Fig. 2** | Entity-relationship diagram: Session→Clip→Frame fan-out, with sensor and annotation branches | Redraw from generic ER structure in `kaist_ingestion/schemas.py` (table definitions) |

### III-C. Schema Design for Geometric Types

- Named complex structs: SE3 pose, Quaternion, Translation3D, Box3D, Matrix3×3
- Design rationale: type safety for spatial data; enables downstream geometric validation (e.g., unit-quaternion check)

| **Figure/Table** | **Description** | **Source in codebase** |
|---|---|---|
| **Table II** | Complex type definitions: AD geometric type → Iceberg/Spark type mapping (SE3, Quaternion, Box3D, etc.) | `kaist_ingestion/schemas.py` (StructType definitions) |

---

## IV. Medallion Layer Design

### IV-A. Bronze Layer — Raw Ingestion
- 1:1 mapping from JSON source files; no transformations, no partitioning
- Preserves lineage and enables schema evolution
- 14 tables across 3 Iceberg namespaces (bronze, silver, gold)

### IV-B. Silver Layer — Cleaned and Partitioned
- Per-table transformations: null array cleanup, sensor name normalization (regex)
- **Domain-aware partitioning**: sensor tables partitioned by `sensor_name` then `clip_id` — aligned with the dominant ML access pattern ("all data from CAM_FRONT")
- Sort orders for temporal locality (`sensor_timestamp` within partitions)

| **Figure/Table** | **Description** | **Source in codebase** |
|---|---|---|
| **Table III** | Silver layer partitioning & sort strategy per table | `kaist_ingestion/transform_silver.py` |

### IV-C. Gold Layer — ML-Ready Denormalized Tables
- Three Gold tables, each targeting a specific ML workload:
  1. **`camera_annotations`** — object detection training: Camera ← Frame ← Clip ← Calibration ← DynamicObject ← HDMap; partitioned by `camera_name` (6 partitions)
  2. **`lidar_with_ego`** — SLAM / localization: Lidar ← EgoMotion ← Calibration; partitioned by `clip_id`
  3. **`sensor_fusion_frame`** — multi-modal perception: all sensors + annotations aggregated per frame; partitioned by `clip_id`
- Zero-join reads at query time; all joins pre-computed at ETL time

| **Figure/Table** | **Description** | **Source in codebase** |
|---|---|---|
| **Fig. 3** | Medallion data flow diagram: Bronze → Silver → Gold, showing table fan-in per Gold table (which Silver tables feed each Gold table) | Derived from lineage in `kaist_ingestion/build_gold.py` join logic |
| **Table IV** | Gold table schemas: columns, types, source lineage, partition key, and target ML workload for each of the three Gold tables | `kaist_ingestion/build_gold.py` |

---

## V. Data Quality Framework

### V-A. Validation Architecture
- Generic validators: PK uniqueness, null detection, FK integrity (left-anti join), array completeness
- Domain-specific validators: unit-quaternion norm check ($\|q\| \approx 1.0 \pm \epsilon$), non-negative timestamps

### V-B. Severity-Based Reporting
- CRITICAL (pipeline fails) vs. WARNING (logged) vs. INFO (metrics only)
- Validation suites defined per layer (Bronze, Silver, Gold)

| **Figure/Table** | **Description** | **Source in codebase** |
|---|---|---|
| **Table V** | Validation rules by layer: rule name, target table, severity, description | `kaist_ingestion/validators.py` |

---

## VI. Evaluation

### VI-A. Experimental Setup
- Dataset: nuScenes v1.0-mini (public; + synthetic scaling via data replication, 1×–49× scale factors)
- Environment: Docker Compose stack (Spark 3.5.5, Iceberg 1.8.1, MinIO)
- Workload: "Retrieve front-camera images with adult pedestrian 3D annotations"
- Three strategies compared: (1) Pure Python nested-loop, (2) Spark Iceberg normalized (Silver-level join), (3) Spark Iceberg denormalized (Gold table)

### VI-B. Query Performance Results
- Gold table maintains ~80 ms at 49× scale vs. ~1.13 s for Python baseline → **~14× speedup**
- Silver join strategy: better than Python at scale but shuffle-limited

| **Figure/Table** | **Description** | **Source in codebase** |
|---|---|---|
| **Fig. 4** | Line chart: Query latency (y-axis, seconds) vs. data scale factor (x-axis, 1×–49×) for three strategies | Regenerate from benchmark table in `nuscenes_experiment/README.md` §5; drawing code in `nuscenes_experiment/03_ipynb_exp_yes-def/draw_result.ipynb` |
| **Table VI** | Raw benchmark numbers: scale factor × strategy → latency (seconds) | `nuscenes_experiment/README.md` §5 "Result Table" |

### VI-C. Partition Pruning Analysis
- Analytical model for pruning effectiveness based on the proposed schema's partition structure
- At a projected 20 TB scale (calibrated against nuPlan v1.1): `camera_name = 'CAM_FRONT'` prunes 83.3% of data (5 of 6 camera partitions skipped)
- With both predicates (`camera_name` + `clip_id`): 99.99% pruning

| **Figure/Table** | **Description** | **Source in codebase** |
|---|---|---|
| **Fig. 5** | Bar chart: data scanned (%) for four query selectivity scenarios (no pruning, sensor-only, sensor+clip, Gold single-partition) at projected 20 TB scale | Compute from partition cardinality analysis (6 cameras × N clips) |

### VI-D. Scalability Projections
- Calibrated against nuPlan v1.1 public reference (2 TB test → ~20 TB full)
- Gold single-partition query: <100 ms (dev) → 1–5 s (20 TB) → 10–30 s (2 PB)
- Storage tiering strategy: Hot (NVMe, ~5%), Warm (HDD-EC, ~30%), Cold (HDD-EC-compressed, ~65%)

| **Figure/Table** | **Description** | **Source in codebase** |
|---|---|---|
| **Table VII** | Scalability projections: dataset size → row counts, Parquet file counts, estimated Gold query latency (calibrated against nuPlan v1.1 metrics) | Derived from nuPlan public statistics + our partition model |
| **Fig. 6** | Storage tiering diagram: hot/warm/cold tiers with data percentage and hardware type | Original design diagram |

---

## VII. Discussion

### VII-A. Cross-Dataset Generality
- Architecture designed to generalize across AD datasets with varying hierarchy depths (2-level nuScenes vs. proposed 3-level)
- nuScenes successfully ingested end-to-end; proposed extended schema implemented and tested with simulated data derived from nuScenes

### VII-B. Limitations and Threats to Validity
- Current benchmarks on nuScenes-mini (small scale); scalability projections are analytical, not measured at 20 TB
- Single-node Spark; production would use distributed cluster
- Gold table maintenance cost (re-materialization on schema change) not yet measured
- Extended schema not yet validated against a real production-scale 3-level dataset

---

## VIII. Conclusion and Future Work

- Summary of contributions
- Future work:
  - Validation with production-scale AD datasets as they become available
  - Streaming ingestion for live vehicle data (Spark Structured Streaming)
  - Direct PyTorch DataLoader integration from Gold Iceberg tables
  - Federated querying across multi-fleet datasets

---

## Figures & Tables Summary

| # | Type | Caption (working) | Can be produced from |
|---|------|-------------------|----------------------|
| Fig. 1 | Architecture diagram | System architecture: query, catalog, table format, and storage layers | `docker-compose.yml` service topology |
| Fig. 2 | ER diagram | Proposed extended AD data model: Session → Clip → Frame hierarchy | `kaist_ingestion/schemas.py` table definitions |
| Fig. 3 | Data flow diagram | Medallion architecture: Bronze → Silver → Gold table lineage | `kaist_ingestion/build_gold.py` join logic |
| Fig. 4 | Line chart | Query latency vs. data scale factor (3 strategies) | Benchmark data in `nuscenes_experiment/README.md` §5; code in `draw_result.ipynb` |
| Fig. 5 | Bar chart | Partition pruning effectiveness: % data scanned per query selectivity | Partition cardinality model (6 cameras × N clips) |
| Fig. 6 | Tiered diagram | Hot/Warm/Cold storage tiering strategy | Original design |
| Table I | Comparison | AD hierarchy patterns: 2-level (nuScenes) vs. proposed 3-level | Generalized from public dataset documentation |
| Table II | Type mapping | Complex geometric types: AD type → Iceberg/Spark definitions | `kaist_ingestion/schemas.py` |
| Table III | Partitioning | Silver layer: per-table partition columns, sort columns, transformations | `kaist_ingestion/transform_silver.py` |
| Table IV | Schema | Gold table designs: columns, lineage, partition key, target ML workload | `kaist_ingestion/build_gold.py` |
| Table V | Validation | Data quality rules by layer: rule, table, severity | `kaist_ingestion/validators.py` |
| Table VI | Benchmark | Raw query latency numbers: scale factor × strategy | `nuscenes_experiment/README.md` §5 |
| Table VII | Projections | Scalability: dataset size → rows, files, query latency (nuPlan-calibrated) | nuPlan public statistics + partition model |
