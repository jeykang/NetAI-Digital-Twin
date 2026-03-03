# Slide Deck Plan: Data Lakehouse for Autonomous Driving Data Management

> **Presentation context:** Government project (KAIST/MOTIE) quarterly development progress check-in
> **Audience:** Other participants in the government-funded project — AI/ML researchers, not data engineers. They know the broad strokes of what our team does; this is the technical detail.
> **Tone:** Progress report — here's what we built, here's how it performs, here are the open questions. Not a pitch.
> **Format:** 4 poster-density slides — each one a self-contained reference sheet
> **Estimated duration:** 15–20 minutes
> **Date:** March 4, 2026

---

## Generated Figures

All figures pre-generated at 200 DPI in `paper/figures/`.

| # | Filename | Content |
|---|----------|---------|
| F1 | `architecture.png` | System architecture (5-service Docker stack) |
| F2 | `data_model.png` | KAIST 3-level hierarchy diagram |
| F3 | `medallion_pipeline.png` | Bronze → Silver → Gold pipeline flow |
| F4 | `workload_benchmark.png` | Grouped bar chart — Gold vs Silver, 3 workloads |
| F5 | `scalability.png` | Line chart — latency vs scale factor (1×–50×) |
| F6 | `supplementary_benchmarks.png` | 3-panel: partition pruning, temporal replay, column metrics |
| F7 | `gold_tables.png` | Gold table design cards (3 tables) |
| F8 | `validation_summary.png` | Data quality validation table (20 checks) |

---

## Slide 1 — Architecture, Data Model & Technology Stack

> *Everything about what we built — the system, the schema, the tech.*

**Layout:** Dense four-quadrant. Top-left: architecture figure. Top-right: data model figure. Bottom-left: schema reference table. Bottom-right: deployment detail. Title banner across the top.

### Top Banner — Project Context

> **What this is:** The data infrastructure component of the NetAI Digital Twin project. Takes raw KAIST E2E autonomous driving sensor data (14 entity types across cameras, LiDAR, radar, ego pose, annotations, maps) and transforms it into ML-ready tables via a three-layer pipeline (Bronze → Silver → Gold). Five-service Docker stack, single-command deployment.

### Top-Left Quadrant — System Architecture

**Figure:** `paper/figures/architecture.png` (compact)

**Five-service stack (labeled on or beside figure):**

| Service | Technology | Version | Role (ML-user perspective) |
|---------|-----------|---------|---------------------------|
| **ETL Engine** | Apache Spark (PySpark) | 3.5.5 | Runs the 3-layer pipeline: raw JSON → ML-ready tables. Performs all joins and physical optimizations once so training code doesn't have to. |
| **Table Format** | Apache Iceberg | 1.8.1 (v2) | ACID transactions, time travel (pin dataset versions), schema evolution, partition pruning, column-level statistics. The reason Gold queries are fast. |
| **Catalog** | Apache Polaris | Latest | REST catalog — central registry so Spark, Trino, and Superset all see the same tables. No file-path wrangling. |
| **Object Storage** | MinIO | 2025-09 | S3-compatible storage (dev). Swappable to Ceph or cloud S3 — code doesn't change. |
| **Query + BI** | Trino 479 + Apache Superset | Latest | Interactive SQL and dashboards to explore the dataset without Python. E.g., `SELECT * FROM kaist_gold.camera_annotations WHERE camera_name = 'CAM_FRONT' AND category = 'pedestrian'` |

**Deployment:** `docker compose up` → all 5 services + Polaris catalog initialization. Single `.env` file for configuration.

### Top-Right Quadrant — KAIST 3-Level Data Model

**Figure:** `paper/figures/data_model.png` (compact)

**Hierarchy:** Session → Clip → Frame → Sensors/Annotations
- Generalizes nuScenes' 2-level model (Scene → Sample) by adding Session level for multi-drive campaigns
- **14 entity types total:**
  - *3 Hierarchy:* Session, Clip, Frame
  - *4 Sensors:* Camera, LiDAR, Radar, Ego Motion
  - *4 Annotations:* Dynamic Object, Occupancy, Motion, Category
  - *3 Metadata:* Calibration, HD Map, Session Ego Motion
- **Named geometric structs:**
  - **SE3** — 4×4 rigid transform (rotation 3×3 + translation 3D)
  - **Quaternion** — (qw, qx, qy, qz), unit-norm enforced by validation
  - **Box3D** — 7-DOF bounding box (center xyz + size wlh + yaw)
  - **Translation3D** — (x, y, z)

### Bottom-Left Quadrant — Full Schema Reference (14 Tables)

| Table | Primary Key | Key Fields | Silver Partition | Silver Sort |
|-------|------------|------------|-----------------|-------------|
| session | session_id | session_name, clip_id_list | — | — |
| clip | clip_id | session_id, clip_idx, date | session_id | clip_idx |
| frame | frame_id | clip_id, frame_idx, sensor_timestamps | clip_id | frame_idx |
| calibration | clip_id + sensor_name | extrinsics (SE3), camera_intrinsics (3×3) | clip_id, sensor_name | — |
| camera | frame_id + camera_name | clip_id, sensor_timestamp, filename | camera_name, clip_id | sensor_timestamp |
| lidar | frame_id | clip_id, sensor_timestamp, filename | clip_id | sensor_timestamp |
| radar | frame_id + radar_name | clip_id, sensor_timestamp, filename | radar_name, clip_id | sensor_timestamp |
| ego_motion | frame_id | clip_id, translation (3D), rotation (Quat) | clip_id | sensor_timestamp |
| dynamic_object | frame_id | clip_id, boxes_3d (Box3D[]), category | clip_id | sensor_timestamp |
| category | category | (reference table, no FK) | — | — |
| occupancy | frame_id | clip_id, occupancy_data* | clip_id | sensor_timestamp |
| motion | frame_id | clip_id, motion_data* | clip_id | sensor_timestamp |
| session_ego_motion | session_id | translation, rotation, start, goal | — | — |
| hdmap | clip_id | filename, city, site | — | — |

\* Placeholder schemas — to be refined with actual KAIST data. Silver skips 3 low-priority tables (occupancy, motion, session_ego_motion).

### Bottom-Right Quadrant — Docker Deployment Detail

```
5 services · 1 command · ~60 s cold start
┌────────────────────────────────────────────┐
│  docker compose up                         │
│  ├─ spark-iceberg   (Spark 3.5.5 + Py)    │
│  ├─ polaris         (REST catalog)         │
│  ├─ minio           (S3 storage)           │
│  ├─ trino           (SQL engine, port 8080)│
│  └─ superset        (BI, port 8088)        │
│  + polaris-setup    (one-shot catalog init) │
│  + trino-setup      (one-shot schema reg.) │
└────────────────────────────────────────────┘
Storage backend is pluggable: MinIO (dev) → Ceph or AWS S3 (prod)
```

**Speaker notes:** "This is the system overview. Top-left: the five services — Spark runs the pipeline, Polaris keeps a central catalog, MinIO stores the data, Trino + Superset are for querying and exploration. Top-right: the KAIST 3-level hierarchy — Session, Clip, Frame — with 14 entity types and custom geometric types. Bottom-left: every table in the schema with its keys and how it's partitioned — note that some of these are still placeholders pending the next schema review with the data team. Bottom-right: Docker deployment — one command launches everything. All five services share Polaris as the single source of truth for table metadata."

---

## Slide 2 — Pipeline, Gold Tables & Data Validation

> *How data flows from raw JSON to ML-ready tables, what the output looks like, and how we guarantee correctness.*

**Layout:** Three horizontal bands. Top band: pipeline flow with layer details. Middle band: Gold table designs. Bottom band: validation matrix. Figures placed inline.

### Top Band — Three-Layer Medallion Pipeline

**Figure:** `paper/figures/medallion_pipeline.png` (compact, spanning width)

| Layer | What Happens | Implementation Detail | Why It Matters for ML | Count |
|-------|-------------|----------------------|----------------------|-------|
| **Bronze** (Raw Ingest) | Each of 14 JSON files → 1 Iceberg table. Full PySpark `StructType` schema enforcement at write time. Wrong type or missing field → hard failure. Raw data preserved immutably. | `BronzeIngester.ingest_table()` — schema-driven, zero hardcoded column names. Schema defined once in `schemas.py` (14 `StructType` definitions). | **Data integrity from ingest.** No corrupt data silently entering the pipeline. Bronze is your audit trail — always reprocessable. | 14 tables |
| **Silver** (Domain-Optimized) | Physical reorganization: partition by access pattern (camera by `camera_name`, temporal tables by `clip_id`), sort within partitions by `sensor_timestamp`, write Iceberg column-level min/max statistics on every column via `METRICS_CONFIG`. | `SilverTransformer` with 3 config dicts: `PARTITION_CONFIG` (11 entries), `SORT_CONFIG` (8 entries), `METRICS_CONFIG` (8 entries). Uses Iceberg `write.metadata.metrics.column.*` properties. | **Automatic I/O elimination.** Filter by `camera_name = 'CAM_FRONT'` → skip 5/6 of camera files (83%). Filter by clip + camera → skip 98.4%. Temporal queries use per-file timestamp ranges to skip files outside the window. Data comes pre-sorted for sequential models. | 11 tables |
| **Gold** (ML-Ready) | Pre-compute the exact multi-table joins each ML task needs. Materialize as flat, partitioned Iceberg tables. One table per workload. | `GoldTableBuilder` with 3 build methods. Each executes the join, repartitions, sorts within partitions, and writes with full column metrics. | **Zero join code in training pipeline.** `DataLoader.__getitem__` reads one table. All image paths, 3D boxes, calibration, ego pose — pre-joined. | 3 tables |

**Full pipeline execution:**
```
[PHASE 1/4] Ingest Bronze    ─── 14 JSON → 14 Iceberg tables         (schema-enforced)
[PHASE 2/4] Transform Silver  ─── 14 → 11 domain-optimized tables     (partitioned + sorted + metrics)
[PHASE 3/4] Build Gold        ─── 11 → 3 ML-ready pre-joined tables   (one per workload)
[PHASE 4/4] Validate          ─── 20 automated checks, ALL PASS       (blocks on failure)
Total: ~24 seconds end-to-end (KAIST-simulated, single node)
```

### Middle Band — Gold Table Designs

**Figure:** `paper/figures/gold_tables.png` (spanning width)

| Gold Table | ML Task | Example Models | Source Tables Joined | Key Output Columns | Partition Key | Sort Key | Rows |
|---|---|---|---|---|---|---|---|
| `camera_annotations` | 3D Object Detection | BEVFormer, DETR3D, CenterPoint | camera ⋈ frame ⋈ clip ⋈ calibration ⋈ dynamic_object ⋈ hdmap (6 tables) | camera_filename, sensor_timestamp, frame_idx, clip_date, extrinsics (SE3), camera_intrinsics (3×3), boxes_3d (Box3D[]), category, hdmap_filename, city | `camera_name` | sensor_timestamp | 23,150 |
| `lidar_with_ego` | SLAM / Localization | ORB-SLAM, LIO-SAM, KISS-ICP | lidar ⋈ ego_motion ⋈ calibration (3 tables) | lidar_filename, sensor_timestamp, ego_translation (3D), ego_rotation (Quat), extrinsics (SE3), clip_id | `clip_id` | sensor_timestamp | 389 |
| `sensor_fusion_frame` | Multi-Modal Fusion | TransFusion, BEVFusion, UniAD | frame ⋈ camera ⋈ lidar ⋈ radar ⋈ dynamic_object (5 tables + 3 group-by aggregations) | frame_idx, sensor_timestamp, camera_list (agg), lidar_filename, radar_list (agg), all_boxes_3d (agg), num_cameras, num_radars, clip_id | `clip_id` | sensor_timestamp | 389 |

**Design principle:** Each Gold table's partition key matches the dominant filter predicate for its workload — `camera_name` for detection (users query one camera at a time), `clip_id` for temporal workloads (users process one driving sequence at a time).

### Bottom Band — Automated Validation (20 Checks)

**Figure:** `paper/figures/validation_summary.png` (compact)

| Check Category | What We Verify | Why It Matters for ML | Severity | Count |
|---|---|---|---|---|
| **Primary key uniqueness** | Every record ID is unique within its table (session_id, clip_id, frame_id, etc.) | Duplicate frames bias training distribution; duplicate annotations inflate loss | CRITICAL | 6 |
| **Foreign key integrity** | Cross-table references resolve (e.g., camera.frame_id → frame.frame_id exists) | Broken FK → `DataLoader` gets NULL annotations or missing calibration for some frames | CRITICAL | 4 |
| **Quaternion unit-norm** | $\|q\| = \sqrt{q_w^2 + q_x^2 + q_y^2 + q_z^2} \approx 1.0 \pm \epsilon$ for all ego_motion and calibration rotations | Non-unit quaternion → corrupted ego-pose transform → wrong 3D bounding box projections | CRITICAL | 2 |
| **Timestamp validity** | All `sensor_timestamp` values ≥ 0 | Negative timestamp → data corruption; breaks time-range filters and temporal ordering | CRITICAL | 4 |
| **Gold row-count consistency** | Gold table row count matches expected count from source join | Mismatch → the pre-join step dropped or duplicated data silently | CRITICAL | 4 |
| **TOTAL** | **All 20 checks pass on every pipeline run** | Pipeline halts on any CRITICAL failure — bad data never reaches Gold tables | | **20** |

**Speaker notes:** "Slide 2 is the pipeline deep-dive. Top band: three layers — Bronze enforces schema on ingest, Silver reorganizes data physically for fast access (partitioning, sorting, column statistics), Gold pre-computes joins. The full pipeline runs in about 24 seconds on the simulated dataset. Middle band: the three Gold tables in detail — camera_annotations eliminates a 6-table join for object detection, lidar_with_ego eliminates a 3-table join for SLAM, sensor_fusion_frame eliminates 5 tables plus 3 aggregations for fusion. Bottom band: 20 automated validation checks that run after every pipeline execution. These catch real problems — duplicate frames, broken references, non-unit quaternions (which would silently corrupt your 3D geometry), negative timestamps, and row-count mismatches. If any critical check fails, the pipeline halts before bad data reaches a Gold table."

---

## Slide 3 — All Benchmarks: Methodology, Results & Analysis

> *Every experiment, every number, full methodology. We measured data retrieval, not model training.*

**Layout:** Dense five-section layout. Top: methodology + disclaimer. Upper-middle: Experiment 1 (three workloads). Lower-middle: Experiment 2 (scalability). Bottom-left: supplementary experiments. Bottom-right: time travel validation.

### Top Section — Scope Disclaimer & Methodology

> **What we measured and what we did not:** We measured the *data retrieval step* — the query that an ML training pipeline executes to assemble its input batch. We did **not** run model training end-to-end. Every ML model needs this data retrieval step; it runs once per epoch; it is the I/O bottleneck that scales with dataset size.

**Benchmark methodology (applies to all experiments):**

| Aspect | Detail |
|--------|--------|
| **Fair comparison** | Each Silver query replicates *exactly* the same join graph used to build the corresponding Gold table (e.g., the 6-table Object Detection Silver query mirrors `GoldTableBuilder.build_camera_annotations()` line-for-line) |
| **Same filter predicate** | Identical `WHERE` clause applied to both Gold and Silver (e.g., `camera_name = 'CAM_BACK'`) — isolates join cost, not filter selectivity |
| **JVM warmup** | 3 throwaway Spark SQL queries before timing begins |
| **Timing protocol** | 2 untimed warmup runs → 5 timed runs → **median** reported |
| **Metric** | `df.count()` action — forces full scan + join execution; excludes Python serialization overhead (measures pure engine time) |
| **Filter values** | Sampled from live data, not hardcoded (e.g., `camera_name` drawn from actual table) |
| **Environment** | Single-node Docker: Spark 3.5.5, Iceberg 1.8.1, Polaris REST catalog, MinIO |

### Experiment 1 — Three AD Workloads: Gold vs. Silver (KAIST Dataset)

**Dataset:** KAIST-simulated, 14 tables, 140 K camera annotations, 3,935 frames

**Figure:** `paper/figures/workload_benchmark.png`

| Workload | Example Models | Gold Query | Silver JOIN Query | Gold (ms) | Silver (ms) | Speedup | Rows |
|---|---|---|---|---|---|---|---|
| **Object Detection** | BEVFormer, DETR3D, CenterPoint | `SELECT * FROM camera_annotations WHERE camera_name = ?` | 6-table join: camera ⋈ frame ⋈ clip ⋈ calibration ⋈ dynamic_object ⋈ hdmap | **79** | 255 | **3.2×** | 23,150 |
| **SLAM / Localization** | ORB-SLAM, LIO-SAM, KISS-ICP | `SELECT * FROM lidar_with_ego WHERE clip_id = ?` | 3-table join: lidar ⋈ ego_motion ⋈ calibration | **64** | 138 | **2.2×** | 389 |
| **Sensor Fusion** | TransFusion, BEVFusion, UniAD | `SELECT * FROM sensor_fusion_frame WHERE clip_id = ?` | 5-table join + 3 aggregations: frame ⋈ camera ⋈ lidar ⋈ radar ⋈ dynamic_object | **49** | 99 | **2.0×** | 389 |

**What each workload retrieves (ML context):**
- **Object Detection:** Camera image path + 3D bounding boxes + category labels + camera intrinsics/extrinsics, for one specific camera. Analogous to `nuScenes.get_sample_data()` with annotations, but pre-materialized.
- **SLAM:** LiDAR point cloud path + ego vehicle pose (translation + quaternion) + extrinsic calibration, for one driving clip. Analogous to reading a single KITTI sequence directory as a table query.
- **Sensor Fusion:** All sensors (6 cameras + LiDAR + radar) + annotations aggregated into one row per time-step, for one clip. Analogous to assembling a full nuScenes `Sample` across all modalities.

### Experiment 2 — Scalability: Latency vs. Data Scale (nuScenes, 1×–50×)

**Dataset:** nuScenes v1.0-mini (public), 7 core JSON tables, synthetically replicated from 1× to 50× (18 scale points). Observation tables scaled; reference tables (category, sensor) remain at 1× — mimics realistic growth.
**Task:** "Load front-camera images with adult-pedestrian 3D annotations" — the data step before feeding a batch to BEVFormer or DETR3D.
**Python baseline:** Conventional `for`-loop over JSON dictionaries (nuScenes tutorial style). Median of 5 runs.
**Spark strategies:** 1 warmup + median of 3 runs.

**Figure:** `paper/figures/scalability.png`

| SF | Rows | Python (ms) | Silver (ms) | Gold (ms) | Gold vs. Python |
|---:|---:|---:|---:|---:|---:|
| 1× | 27,483 | 15 | 267 | 42 | 0.4× |
| 2× | 54,966 | 31 | 227 | 47 | 0.7× |
| 3× | 82,449 | 48 | 184 | 50 | 1.0× |
| 5× | 137,415 | 78 | 221 | 63 | 1.2× |
| 10× | 274,830 | 153 | 198 | 60 | 2.6× |
| 15× | 412,245 | 220 | 242 | 69 | 3.2× |
| 20× | 549,660 | 297 | 297 | 68 | 4.4× |
| 25× | 687,075 | 373 | 351 | 73 | 5.1× |
| 30× | 824,490 | 447 | 385 | 75 | 6.0× |
| 35× | 961,905 | 492 | 397 | 82 | 6.0× |
| 40× | 1,099,320 | 622 | 437 | 91 | 6.8× |
| 45× | 1,236,735 | 623 | 481 | 82 | 7.6× |
| 50× | 1,374,150 | 733 | 499 | 87 | **8.4×** |

**Key findings:**
1. **Gold stays under 100 ms at every scale** (42 ms → 87 ms at 50×). Data loading never becomes the training bottleneck.
2. **Python slows linearly** (15 ms → 733 ms). At full KAIST dataset scale, this dominates per-epoch time.
3. **Crossover at ~3×:** Below SF 3, Python is faster (no Spark overhead). Above SF 3, Gold wins. Gap widens to **8.4×** at SF 50.
4. **Silver plateaus around 400–500 ms** — join overhead dominates at scale, but still better than Python above SF 20.

### Supplementary Experiments — Iceberg Features

**Figure:** `paper/figures/supplementary_benchmarks.png`

| Experiment | What It Tests | Setup | Result | ML Implication |
|---|---|---|---|---|
| **Partition Pruning** | How much I/O is eliminated when filtering by partition key | Filter by `camera_name` (1/6 cameras): files scanned? Add `clip_id`: files scanned? | **83% skipped** (camera only), **98.4% skipped** (camera + clip) | "I only need CAM_FRONT for clip X" → system reads 1.6% of data |
| **Temporal Replay** | Cost of reading frames in time order for sequential models | Pre-sorted (Silver/Gold) vs. explicit `ORDER BY sensor_timestamp` at query time | **1.8× faster** with pre-sorted data | Video transformers, sequence models get frames in order without explicit sort |
| **Column-Level Metrics** | Benefit of per-file min/max statistics for range predicates | Narrow time-range query (`sensor_timestamp BETWEEN t1 AND t1+5s`): metrics-enabled vs. disabled | **4.8× speedup** | "Give me a 5-second window of data" → system checks each file's timestamp range, skips files entirely |
| **Time Travel (Snapshot Pinning)** | Can you reproduce the exact dataset after new data arrives? | Write 23,150 rows → record snapshot ID → append 23,150 more rows → read at pinned snapshot | Returns exactly **23,150 rows** (not 46,300) ✓ | Pin dataset version before training → reproduce exact data months later. Critical for paper submissions and regulatory compliance. |

**Speaker notes:** "This slide is the evidence. I want to be precise: we did not run model training end-to-end — we measured the data retrieval step, which is the I/O bottleneck in every training pipeline. The methodology is designed for fairness: the Silver query replicates the exact same join logic that built the Gold table, with the same filter predicate, so we're isolating the cost of pre-joining vs. runtime joining. JVM is pre-warmed, 2 untimed warmup runs, 5 timed runs, median reported. Three workloads: object detection gets 3.2× faster, SLAM 2.2×, fusion 2.0×. The scalability experiment on nuScenes shows Gold stays under 100 ms at every scale while Python scripts slow linearly to 733 ms at 50× — that's an 8.4× gap. The supplementary experiments show that Iceberg's built-in features — partition pruning, pre-sorted data, column statistics, snapshot pinning — each contribute measurable speedups. The time travel experiment is particularly important: you can pin your training data to a specific snapshot and read it back identically after the dataset has been updated."

---

## Slide 4 — Status, Open Questions & Next Steps

> *What's done, what needs cross-team decisions, and where we go from here.*

**Layout:** Three horizontal bands. Top: status matrix. Middle: open design questions + planned work. Bottom: results summary.

### Top Band — Current Status (What's Operational Today)

| Deliverable | Status | Detail |
|-------------|--------|--------|
| Full medallion pipeline (Bronze → Silver → Gold → Validate) | ✅ Operational | 4-phase automated pipeline, ~24 s end-to-end on simulated data |
| KAIST 3-level schema | ✅ Implemented | 14 entity types, 4 named geometric structs (SE3, Quaternion, Box3D, Translation3D) |
| Bronze layer | ✅ Complete | 14 Iceberg tables, schema-enforced, raw-preserving |
| Silver layer | ✅ Complete | 11 domain-optimized tables (3 low-priority tables deferred: occupancy, motion, session_ego_motion) |
| Gold layer | ✅ Complete | 3 ML-ready pre-joined tables (camera_annotations, lidar_with_ego, sensor_fusion_frame) |
| Automated validation | ✅ Complete | 20 checks (PK uniqueness, FK integrity, quaternion norms, timestamps, row-count consistency). All pass. |
| 5-service Docker stack | ✅ Deployed | Spark 3.5.5, Polaris, MinIO, Trino 479, Superset. Single `docker compose up` command. |
| Benchmark suite | ✅ Complete | 5 experiments (three-workload, scalability, partition pruning, temporal replay, column metrics + time travel). All reproducible. |
| nuScenes cross-validation | ✅ Complete | Pipeline validated on nuScenes v1.0-mini (public dataset, 7 tables). Confirms generalizability beyond KAIST schema. |
| Paper draft | ✅ In preparation | Domestic conference, 2-page format |

### Middle Band — Open Design Questions (For Cross-Team Discussion)

These are decisions that affect other teams and need joint resolution. The lakehouse can support any of the listed options — the question is which policy the project adopts.

| Question | Context | Options on the Table | Who Decides |
|----------|---------|---------------------|-------------|
| **How do schema updates propagate?** | The data schema team may add/rename/restructure fields. Currently, schema changes require updating `schemas.py` + downstream Silver/Gold logic (~235 hardcoded column references across 5 files). | **(a)** Schema team sends high-level definition (DBML/Avro), we implement pipeline changes. **(b)** Build auto-generation tooling (DBML → PySpark StructType) to reduce manual work. **(c)** Schema team works directly in codebase (high coordination cost). | Data schema team + us |
| **Pre-Bronze data retention policy** | Bronze layer currently preserves raw JSON immutably (audit trail, reprocessing). At production scale, this doubles storage. | **(a)** Keep originals indefinitely (safest, most expensive). **(b)** Delete originals after Bronze ingest is validated (saves space, irreversible). **(c)** Move originals to cold storage / archive tier after N days. | Project-wide policy |
| **Placeholder schemas (occupancy, motion)** | 2 of 14 table schemas have placeholder fields — we need the actual data format from the vehicle/annotation teams. Silver layer skips these 3 tables until schemas are finalized. | Waiting on field definitions from data collection team. | Data collection + annotation teams |
| **End-to-end ML validation** | Our benchmarks measure data retrieval only. Validating impact on actual model training time (e.g., BEVFormer epoch time with Gold tables vs. conventional data loading) would strengthen the case but requires GPU resources + model code. | **(a)** We run it (need GPU allocation). **(b)** An ML team runs it using our Gold tables. **(c)** Defer to next quarter. | ML teams + us |
| **Storage backend for production** | MinIO is dev-only. Production needs a decision on Ceph (on-prem) vs. cloud S3. Code is storage-agnostic (S3 API), so the switch is configuration-only. | Depends on project infrastructure decisions. | Infrastructure team |

### Middle Band (cont.) — Planned Next Steps

| Next Step | Status | Detail |
|-----------|--------|--------|
| **Production-scale validation** | Blocked on real data | Test full pipeline with actual KAIST E2E dataset on multi-node Spark cluster |
| **Streaming ingestion** | Planned | Live vehicle sensor data → Kafka → Iceberg append. Architecture supports it; implementation not started. |
| **PyTorch DataLoader integration** | Planned | Direct `torch.utils.data.Dataset` reading from Gold Iceberg tables — no intermediate CSV/Parquet export |
| **Extended scalability testing** | Planned | Beyond 50× synthetic scale to real TB-scale data |

### Bottom Band — Summary of Current Results

| What We Built | Key Numbers | Current Scope |
|---------------|-------------|---------------|
| 3-layer pipeline (Bronze → Silver → Gold) with 20-check automated validation | ~24 s end-to-end on simulated data. All 20 validation checks pass every run. | KAIST-simulated (14 tables, 140 K camera annotations, 3,935 frames). Also validated on nuScenes v1.0-mini. |
| 3 Gold tables pre-joining data for object detection, SLAM, and sensor fusion | **2.0–3.2×** faster data retrieval vs. runtime joins (Gold vs. Silver). Object detection: 79 ms vs. 255 ms. | Single-node Docker. Measured data retrieval step (not model training). |
| Scalability tested 1×–50× on nuScenes | **8.4×** faster than conventional Python at 50× scale. Gold stays sub-100 ms at every scale. Crossover at ~SF 3. | Synthetic scaling of nuScenes-mini. Not yet tested at real TB-scale. |
| Iceberg features: partition pruning, temporal sort, column metrics, time travel | 83–98.4% I/O skipped via pruning. 1.8× temporal replay speedup. 4.8× column-metrics speedup. Snapshot pinning verified. | Demonstrated on KAIST-simulated dataset. |
| 5-service Docker stack (Spark, Polaris, MinIO, Trino, Superset) | Single `docker compose up`. ~60 s cold start. | Dev environment. Production deployment (Ceph, multi-node) TBD. |

**Speaker notes:** "To close: the top table is everything that's operational today. The middle section is what I'd like to discuss — these are design decisions that affect multiple teams. Schema evolution is the big one: right now, a schema change from the data team means we manually update about 235 column references across 5 pipeline files. We should decide on a workflow — whether you send us a high-level spec and we implement, or whether we invest in auto-generation tooling. The data retention question is about cost: keeping raw JSON doubles storage, but deleting it is irreversible. And we'd love to run an end-to-end training benchmark — BEVFormer epoch time with Gold tables vs. conventional loading — but we need GPU access and possibly help from one of the ML teams. The bottom table summarizes current results: 2–3× faster data retrieval, 8× faster than Python scripts at scale, and the pipeline catches data errors automatically. All of this works today on a single Docker command — production deployment is the next milestone."

---

## Design & Formatting Guidelines

**General:**
- **Poster-density format.** Each slide is a self-contained reference sheet, not a traditional bullet-point presentation slide. Design each as a dense quadrant/band layout that can be read as a standalone document.
- Use a clean, modern slide template (dark header bar, white body)
- Consistent color coding: **Gold = amber/orange (#E8A838)**, **Silver = steel blue (#6C8EBF)**, **Bronze = warm gray**, **Python baseline = muted green**
- All charts use the pre-generated figures from `paper/figures/`
- Slide numbers in footer; project name and date in footer

**Typography (adjusted for density):**
- Slide titles: 24–28 pt, bold
- Section sub-headers within a slide: 18–20 pt, bold
- Body text: 14–16 pt
- Table text: 11–13 pt (dense tables are expected and acceptable)
- Speaker notes: not displayed, for presenter reference

**Figure placement:**
- Figures are embedded inline within their section band — smaller than in a traditional deck
- Multiple figures per slide is normal (Slide 1 has 2, Slide 2 has 3, Slide 3 has 3)
- No figure borders; figures have built-in white backgrounds

**Slide dimensions:**
- Consider 16:9 widescreen for maximum horizontal space
- If content overflows, widen tables rather than cutting content — information density is the design goal

**Transitions:**
- None. These slides are reference-grade — no animation needed.
