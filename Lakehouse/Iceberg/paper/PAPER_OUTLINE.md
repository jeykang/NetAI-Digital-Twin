# Paper Outline: Domain-Specific Data Lakehouse for Autonomous Driving Data

> **Target venue:** Domestic conference (low-stakes)
> **Page limit:** 2 pages (IEEE-style two-column)
> **Due:** ~end of February 2026
>
> **Confidentiality note:** All content based on publicly available datasets
> (nuScenes, nuPlan) and our own architectural design. The extended 3-level
> schema is presented as our *proposed* generalization — no private dataset
> details are disclosed.

---

## Title (working)

**A Medallion-Architecture Data Lakehouse for Multi-Modal Autonomous Driving Data Management**

---

## Abstract (~100 words)

*Problem:* Managing multi-modal AD sensor data at scale is hindered by ad-hoc
scripts without schema enforcement, ACID guarantees, or query optimization.
*Approach:* We present a medallion-architecture data lakehouse on Apache
Iceberg with domain-aware partitioning and pre-computed Gold tables targeting
three AD workloads (object detection, SLAM, sensor fusion).
*Results:* Gold tables deliver 2–3× speedup over Silver-layer runtime joins
across all three workloads. Under synthetic scaling to 1000× (23.4 M rows),
the Gold layer maintains constant ~33 ms latency — **140× faster** than a
Python baseline (4.66 s) and **36× faster** than Silver-layer joins (1.20 s).

---

## I. Introduction (~0.45 col)

- AD datasets are multi-modal (camera, LiDAR, radar), hierarchical, and append-heavy — TB to PB scale
- Current practice: nested-loop JSON parsing in Python; no ACID, no schema enforcement, no partition pruning
- **Gap:** no open-standard lakehouse architecture designed for AD-specific access patterns (sensor-filtered reads, temporal replay, multi-table joins per ML workload)
- **Contributions:**
  1. A medallion (Bronze → Silver → Gold) Iceberg lakehouse with domain-aware partitioning aligned to AD ML training access patterns
  2. Workload-specific Gold tables for object detection, SLAM, and sensor fusion that eliminate runtime joins
  3. Quantitative evaluation on actual medallion tiers: 2–3× Gold vs. Silver speedup across three AD workloads; **140× vs. Python baseline** at 1000× data scale (23.4 M rows) with constant ~33 ms Gold latency

---

## II. System Design (~0.9 col)

### II-A. Architecture Overview
- Seven-service Docker Compose stack (dev): Spark 3.5.5 (ETL), Polaris REST catalog, MinIO (S3-compatible storage), Trino 479 (interactive SQL), Superset (BI dashboards), PostgreSQL + Redis (Superset backend)
- Production target: Ceph S3 + Kubernetes (Docker Compose is dev/benchmark environment only)
- Single Iceberg v2 catalog shared across all engines → unified metadata, engine-agnostic table access

> **Fig. 1** — System architecture data-flow diagram (~⅓ col): Host ↔ Docker layers (BI → Compute → Infrastructure)
> Source: `docker-compose.yml`; generated as `paper/figures/data_flow.png`

### II-B. Data Model
- Proposed **3-level hierarchy** (Session → Clip → Frame → Sensors + Annotations) designed for long-duration, multi-session AD recordings
- 14 entity types with named geometric structs (SE3, Quaternion, Box3D)
- Validated via simulated data conforming to the proposed schema

### II-C. Medallion Layers
- **Bronze:** 1:1 JSON ingestion into 14 Iceberg tables — preserves lineage, no transformations
- **Silver:** Domain-aware partitioning (sensor tables by `camera_name`/`clip_id`), Iceberg-native sort orders for temporal locality, column-level min/max metrics for predicate pushdown, snapshot retention for time-travel reproducibility — all applied automatically on every write
- **Gold:** Three pre-joined, ML-ready tables eliminating all runtime joins:

| Gold Table | ML Workload | Joins Eliminated | Partition Key |
|---|---|---|---|
| `camera_annotations` | Object detection | 6-table join | `camera_name` |
| `lidar_with_ego` | SLAM / localization | 3-table join | `clip_id` |
| `sensor_fusion_frame` | Multi-modal fusion | 5-table join + 3 agg. | `clip_id` |

> Source: `kaist_ingestion/build_gold.py`, `transform_silver.py`

### II-D. Data Quality
- Automated validators per layer: PK uniqueness, FK integrity, quaternion normalization ($\|q\| \approx 1.0 \pm \epsilon$), non-negative timestamps
- 20 checks (16 CRITICAL, 4 WARNING), all passing

---

## III. Evaluation (~0.9 col)

### III-A. Setup
- **Dataset:** Simulated 3-level dataset conforming to the proposed schema (14 Bronze tables, 11 Silver tables, 3 Gold tables; 140 080 camera annotations, 3 935 frames, 14 008 LiDAR scans)
- **Environment:** Single-node Docker, Spark 3.5.5, Iceberg 1.8.1, Polaris REST catalog, MinIO S3
- **Methodology:** 2 warmup + 3–5 timed runs, median; `count()` action to isolate scan+join time from serialization
- **Scalability:** Synthetic replication of fact tables (camera, dynamic_object for Silver; camera_annotations for Gold) at SF 1–1000× while dimension tables remain at 1× — realistic growth model where sessions accumulate sensor data

### III-B. Experiment 1 — Gold vs. Silver for Three AD Workloads
- Directly validates the core claim: workload-specific Gold tables eliminate runtime joins
- Queries the **actual** Gold and Silver Iceberg tables via Spark SQL

| Workload | Gold (ms) | Silver JOIN (ms) | Speedup | Rows |
|---|---|---|---|---|
| Object detection | 79 | 255 | **3.2×** | 23 150 |
| SLAM / localization | 64 | 138 | **2.2×** | 389 |
| Sensor fusion | 49 | 99 | **2.0×** | 389 |

> **Fig. 2** — Grouped bar chart: Gold vs. Silver latency per workload
> Source: `benchmarks/benchmark_results.json` (Three-Workload experiment); generated as `paper/figures/workload_benchmark.png`

### III-C. Experiment 2 — Scalability (SF 1–1000×)
- Workload: "Assemble all front-camera images + annotations + calibration for object detection training" — the same 6-table join pattern used by `build_gold.build_camera_annotations()`
- Three strategies on **actual medallion tiers:** (1) Pure Python dict-lookup join over original JSON files, (2) Spark Iceberg Silver 6-table JOIN (`silver.*`), (3) Spark Iceberg Gold single-table scan (`gold.camera_annotations`, partitioned by `camera_name`)
- Fact tables scaled synthetically 1×–1000× (11 data points); dimension tables held at 1×

| Scale Factor | Python (ms) | Silver JOIN (ms) | Gold (ms) | Gold Rows |
|---|---|---|---|---|
| 1× | 1.8 | 277 | 42 | 23 420 |
| 100× | 301 | 341 | 41 | 2 342 000 |
| 500× | 2 041 | 700 | 31 | 11 710 000 |
| 1000× | **4 661** | **1 204** | **33** | 23 420 000 |

- **Gold latency is constant** (~29–49 ms) across the entire 1×–1000× range — Iceberg partition pruning confines the scan to a single `camera_name` partition regardless of total table size
- Python degrades linearly (O(n) dict lookups): 1.8 ms → 4.66 s — a **140× gap** vs. Gold at SF 1000
- Silver JOIN grows sub-linearly (Spark optimizer + columnar I/O): 277 ms → 1.20 s — a **36× gap** vs. Gold at SF 1000
- At low SF, Spark's JIT overhead makes Python faster; by SF ~100 Python is already slower than both Spark strategies

> **Fig. 3** — Line chart: latency vs. scale factor for 3 strategies (11 data points, SF 1–1000)
> Source: `benchmarks/kaist_scalability_benchmark.py`; `benchmarks/kaist_scalability_results.json`; generated as `paper/figures/scalability.png`

### III-D. Supplementary Experiments

Three additional micro-benchmarks validate Iceberg-specific features on the lakehouse:

| Experiment | Key Result | Source |
|---|---|---|
| **Partition Pruning** | Combined sensor + clip filter on `camera_annotations` reduces scanned data from 140 080 → 2 290 rows (98.4% skipped); 0.62 s vs. 3.35 s unpartitioned | `benchmark_results.json` Exp 2 |
| **Temporal Replay** | Gold `lidar_with_ego` temporal range query: 81 ms vs. Silver JOIN 143 ms (1.8× speedup); Iceberg sort-order enables efficient timestamp scans | `benchmark_results.json` Exp 3 |
| **Column Metrics** | Narrow timestamp filter on Silver `lidar` table: 18 ms (min/max metadata skips non-matching files) vs. 87 ms full scan (4.7× speedup) | `benchmark_results.json` Exp 5 |

> **Fig. 4** — Three-panel supplementary chart (pruning, replay, column metrics)
> Source: `benchmarks/benchmark_results.json` Exps 2, 3, 5; generated as `paper/figures/supplementary_benchmarks.png`

---

## IV. Conclusion & Future Work (~0.25 col)

- A medallion-architecture Iceberg lakehouse with domain-aware partitioning and pre-computed Gold tables delivers 2–3× speedup for three core AD ML workloads and **140× speedup** vs. Python baselines at 1000× data scale (23.4 M rows), with constant ~33 ms Gold latency
- Iceberg-native features provide additional gains: partition pruning (98.4% data skipped), time travel for training-set pinning, sort orders for temporal replay (1.8× Gold vs. Silver), and column-level metrics for predicate pushdown (4.7× speedup)
- **Limitations:** single-node benchmarks (no distributed Spark); simulated 3-level data derived from nuScenes-mini; three entity types (`occupancy`, `motion`, `session_ego_motion`) use placeholder schemas
- **Future work:** production-scale validation on Ceph + Kubernetes, streaming ingestion for live vehicle data, direct PyTorch DataLoader integration from Gold Iceberg tables

---

## Figures & Tables Summary (2-page budget)

| # | Type | Caption (working) | File | Status |
|---|------|-------------------|------|--------|
| Fig. 1 | Data-flow diagram | System architecture: layered Docker stack | `paper/figures/data_flow.png` | ✅ Generated |
| Fig. 2 | Grouped bar chart | Gold vs. Silver latency for 3 AD workloads | `paper/figures/workload_benchmark.png` | ✅ Generated |
| Fig. 3 | Line chart | Latency vs. scale factor (3 strategies, SF 1–1000) | `paper/figures/scalability.png` | ✅ Generated |
| Fig. 4 | 3-panel chart | Supplementary: pruning, replay, column metrics | `paper/figures/supplementary_benchmarks.png` | ✅ Generated |
| Table 1 | Inline | Gold table designs (§II-C) | — | In outline |
| Table 2 | Inline | Three-workload benchmark (§III-B) | — | In outline |
| Table 3 | Inline | Scalability at key SFs (§III-C) | `paper/figures/scalability_table.png` | ✅ Generated |
| Table 4 | Inline | Supplementary experiments summary (§III-D) | — | In outline |

**Additional generated figures** (available for supplementary / poster use):

| File | Content |
|---|---|
| `paper/figures/data_model.png` | 3-level hierarchy (Session → Clip → Frame) |
| `paper/figures/medallion.png` | Bronze → Silver → Gold pipeline flow |
| `paper/figures/gold_tables.png` | Gold table structure + partition / sort details |
| `paper/figures/validation.png` | 20-check data quality dashboard |

> **Space estimate:** 1 architecture diagram (~⅓ col) + 2 result figures (~⅓ col each) + optional supplementary panel + 3–4 small inline tables ≈ fits within 2 IEEE two-column pages with ~0.25 page for references.

---

## Implementation Status

> **Status (2026-03-04):** All pipeline stages, benchmarks, and figures are complete.

| Component | Status | Notes |
|---|---|---|
| Bronze → Silver → Gold pipeline | ✅ Complete | 14 → 11 → 3 tables; all 20 validations pass (~24 s) |
| Three-workload benchmark | ✅ Complete | `benchmarks/ad_workload_benchmark.py` (1001 lines, 5 experiments) |
| Scalability benchmark (SF 1–1000) | ✅ Complete | `benchmarks/kaist_scalability_benchmark.py` (355 lines, 33 results) |
| All figures (8 + 1 table image) | ✅ Generated | `paper/figures/*.png` via `paper/generate_figures.py` |
| Mermaid diagrams | ✅ Available | Docker setup diagram |

### Known Limitations (non-blocking for paper)

| # | Item | Detail | Impact |
|---|------|--------|--------|
| D1 | **Single-node only** | All benchmarks on single Docker node; no distributed Spark | Noted in §IV |
| D2 | **Silver skips 3 tables** | `occupancy`, `motion`, `session_ego_motion` have no Silver transform; Bronze only. Gold tables do not reference them. | Noted in §IV |
| D3 | **Placeholder schemas** | `OccupancySchema` and `MotionSchema` use `StringType` placeholder fields. Simulated data files contain empty arrays. | No impact on results |
| D4 | **Scalability is synthetic** | Fact-table replication, not real additional driving sessions | Noted in §III-C |
