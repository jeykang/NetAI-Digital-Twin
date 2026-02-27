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
across all three workloads; on nuScenes with synthetic scaling to 50×, the
optimized layout achieves ~8× speedup over a conventional Python baseline
while maintaining sub-100 ms query latency.

---

## I. Introduction (~0.45 col)

- AD datasets are multi-modal (camera, LiDAR, radar), hierarchical, and append-heavy — TB to PB scale
- Current practice: nested-loop JSON parsing in Python; no ACID, no schema enforcement, no partition pruning
- **Gap:** no open-standard lakehouse architecture designed for AD-specific access patterns (sensor-filtered reads, temporal replay, multi-table joins per ML workload)
- **Contributions:**
  1. A medallion (Bronze → Silver → Gold) Iceberg lakehouse with domain-aware partitioning aligned to AD ML training access patterns
  2. Workload-specific Gold tables for object detection, SLAM, and sensor fusion that eliminate runtime joins
  3. Quantitative evaluation: 2–3× Gold vs. Silver speedup across three AD workloads; ~8× vs. Python baseline at 50× data scale on nuScenes

---

## II. System Design (~0.9 col)

### II-A. Architecture Overview
- Five-service Docker Compose stack: Spark 3.5.5 (ETL), Polaris REST catalog, MinIO (S3 storage), Trino (interactive SQL), Superset (BI)
- Single Iceberg v2 catalog shared across all engines → unified metadata

> **Fig. 1** — System architecture (1 diagram, ~⅓ col): Query Layer → Catalog → Iceberg v2 → S3 Storage
> Source: `docker-compose.yml`

### II-B. Data Model
- Proposed **3-level hierarchy** (Session → Clip → Frame → Sensors + Annotations) generalizing nuScenes' 2-level model for long-duration, multi-session AD recordings
- 14 entity types with named geometric structs (SE3, Quaternion, Box3D)
- Validated via simulated data (derived from nuScenes) and the public nuScenes v1.0-mini dataset

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
- **Datasets:** (1) KAIST-simulated 3-level dataset (14 tables, 140 K camera annotations, 3 935 frames) for Gold vs. Silver workload comparison; (2) nuScenes v1.0-mini (public) with synthetic 1×–50× scaling (18 sample points) for scalability
- **Environment:** Single-node Docker, Spark 3.5.5, Iceberg 1.8.1, Polaris REST catalog, MinIO
- **Methodology:** 2 warmup + 5 timed runs, median; `count()` action to isolate scan+join time

### III-B. Experiment 1 — Gold vs. Silver for Three AD Workloads
- Directly validates the core claim: workload-specific Gold tables eliminate runtime joins

| Workload | Gold (s) | Silver JOIN (s) | Speedup | Rows |
|---|---|---|---|---|
| Object detection | 0.079 | 0.255 | **3.2×** | 23 150 |
| SLAM / localization | 0.064 | 0.138 | **2.2×** | 389 |
| Sensor fusion | 0.049 | 0.099 | **2.0×** | 389 |

> **Fig. 2** — Grouped bar chart: Gold vs. Silver latency per workload
> Source: `benchmarks/benchmark_results.json` Exp 1

### III-C. Experiment 2 — Scalability (nuScenes)
- Workload: "Retrieve front-camera images with adult-pedestrian 3D annotations"
- Three strategies: (1) Pure Python nested-loop, (2) Spark Iceberg Silver join, (3) Spark Iceberg Gold table

| Scale Factor | Python (s) | Silver JOIN (s) | Gold (s) |
|---|---|---|---|
| 1× | 0.015 | 0.267 | 0.042 |
| 10× | 0.153 | 0.198 | 0.060 |
| 25× | 0.373 | 0.351 | 0.073 |
| 50× | **0.733** | 0.499 | **0.087** |

- Gold maintains sub-100 ms across entire 1×–50× range; Python degrades linearly → **~8.4× gap** at 50×
- Silver JOIN crosses Python at SF ≈ 20 (both ~0.297 s); sub-linear growth to 0.499 s at 50×
- At low SF, Spark's JIT overhead makes Python faster; the gap inverts and widens with scale

> **Fig. 3** — Line chart: latency vs. scale factor for three strategies (18 sample points, SF 1–50)
> Source: `nuscenes_experiment/README.md` §5; `scalability_chart.png`; `scalability_results.json`

---

## IV. Conclusion & Future Work (~0.25 col)

- A medallion-architecture Iceberg lakehouse with domain-aware partitioning and pre-computed Gold tables delivers 2–3× speedup for three core AD ML workloads and scales to ~8× vs. Python baselines at 50× data scale
- The architecture additionally supports partition pruning (83.3% data skipped on sensor filters), Iceberg time travel for training-set pinning, and column-level metrics for timestamp predicate pushdown — validated in supplementary experiments
- **Limitations:** single-node benchmarks; simulated 3-level data; scalability beyond nuScenes-mini is analytical; three entity types use placeholder schemas
- **Future work:** production-scale validation, streaming ingestion for live vehicle data, direct PyTorch DataLoader integration from Gold Iceberg tables

---

## Figures & Tables Summary (2-page budget)

| # | Type | Caption (working) | Source |
|---|------|-------------------|--------|
| Fig. 1 | Architecture diagram | System architecture: layered stack | `docker-compose.yml` |
| Fig. 2 | Grouped bar chart | Gold vs. Silver latency for 3 AD workloads | `benchmarks/benchmark_results.json` Exp 1 |
| Fig. 3 | Line chart | Latency vs. scale factor (3 strategies, SF 1–50) | `nuscenes_experiment/scalability_chart.png` |
| Table 1 | Inline | Gold table designs (§II-C) | `build_gold.py` |
| Table 2 | Inline | Three-workload benchmark (§III-B) | `benchmark_results.json` Exp 1 |
| Table 3 | Inline | nuScenes scalability (§III-C) | `nuscenes_experiment/scalability_results.json` |

> **Space estimate:** 1 architecture diagram (~⅓ col) + 2 result figures (~⅓ col each) + 3 small inline tables ≈ fits within 2 IEEE two-column pages with ~0.25 page for references.

---

## Remaining Implementation Notes

> **Status (updated):** The full pipeline (Bronze → Silver → Gold → Validate)
> runs end-to-end successfully (all 20 validations pass, ~24 s). All experiment
> scripts use the Polaris REST catalog, and all benchmark results are exported
> to `benchmarks/benchmark_results.json`.

### Known Limitations (non-blocking for paper)

| # | Item | Detail | Impact |
|---|------|--------|--------|
| D2 | **Silver skips 3 tables** | `occupancy`, `motion`, `session_ego_motion` have no Silver transform; Bronze only. Gold tables do not reference them. | Noted in §IV Limitations. |
| D3 | **Placeholder schemas** | `OccupancySchema` and `MotionSchema` use `StringType` placeholder fields. Simulated data files contain empty arrays. | No impact on results. |

### Remaining Figures to Produce

| # | Outline ref | What's needed |
|---|-------------|---------------|
| C1 | Fig. 1 (§II-A) | System architecture diagram (draw.io / TikZ) from `docker-compose.yml` |
| C2 | Fig. 2 (§III-B) | Grouped bar chart from `benchmark_results.json` Exp 1 |
| C3 | Fig. 3 (§III-C) | nuScenes scalability line chart from `draw_result.ipynb` |
