# Slide Deck Plan: Data Lakehouse for Autonomous Driving Data Management

> **Presentation context:** Government project (KAIST/MOTIE) progress review panel
> **Audience:** Other participants in the government-funded project
> **Tone:** Technical but accessible; emphasize practical value and measurable results
> **Estimated duration:** 15–20 minutes (12 content slides + backup)
> **Date:** March 4, 2026
>
> **Key difference from paper:** The KAIST dataset schema and lakehouse design
> are for this project — no need to obscure the dataset origin. Present the
> 3-level schema as the KAIST E2E dataset schema rather than a "proposed
> generalization."

---

## Generated Figures

All figures have been pre-generated at 200 DPI and are located in
`paper/figures/`. Each figure reference below includes the exact filename.

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

## Slide 1 — Title Slide

**Layout:** Clean title slide, project logos if available (KAIST, MOTIE, NetAI)

**Content:**
- **Title:** "Fast, Scalable Data Infrastructure for Autonomous Driving ML Pipelines"
- **Subtitle:** "Getting training data from raw sensors to your model — structured, validated, and fast"
- **Presenter name & affiliation**
- **Date:** March 4, 2026
- **Project:** NetAI Digital Twin — Data Infrastructure Component

**Design notes:** Minimal, professional. Use a dark or navy background with white text. No figures.

> *Rationale for title change:* The original title ("Medallion-Architecture Data Lakehouse…") is meaningful to data engineers but opaque to AI researchers. The reframed title leads with what matters to the audience: getting training data to models quickly.

---

## Slide 2 — Problem Statement & Motivation

**Layout:** Left–right split. Left: bullet points. Right: illustrative diagram or icon set.

**Title:** "The Problem: Managing AD Sensor Data at Scale"

**Left column — Key problems (bulleted, framed as ML pain points):**
1. **Your training data is scattered:** A single training sample for 3D object detection requires data from 6+ separate files — camera paths, frame metadata, calibration, annotations, map info. Every `DataLoader.__getitem__` call has to stitch them together.
2. **The stitching code doesn't scale:** The standard approach — Python `for` loops over JSON dictionaries — works at nuScenes-mini scale (40 K rows). At nuPlan scale (~20 TB), it's the training bottleneck.
3. **Different models need different slices:** Object detection needs camera + 3D boxes. SLAM needs LiDAR + ego pose. Fusion needs everything. But the data is stored the same way regardless of which model is consuming it.
4. **No reproducibility guarantees:** If someone adds new data mid-training, your dataset changes silently. There's no way to pin "the exact data I trained on" without manual file snapshots.

**Right column — Visual illustration:**
- Show a "typical ML workflow" diagram: 7 JSON files → Python `for` loop with arrows between them → slow DataLoader → model. Label the bottleneck.
- OR show a comparison: left = "current: scattered files, manual joins" vs. right = "proposed: single query, pre-joined table"

**Speaker notes:** "If you've worked with nuScenes or any large AD dataset, you know this pain. To assemble one training sample for, say, BEVFormer, your data loader needs to find the camera image, look up the frame, cross-reference the calibration, find the matching annotations, and pull in HD map context. That's 6 file lookups per sample. The standard approach is Python loops over JSON dictionaries — it works fine on the mini split, but once you scale up, data loading becomes the bottleneck. And there's a reproducibility problem: if the dataset changes between experiment runs, you have no way to go back to the exact data you trained on."

---

## Slide 3 — Approach Overview (High-Level)

**Layout:** Full-width horizontal pipeline diagram

**Title:** "Our Approach: Domain-Specific Data Lakehouse"

**Content:**
- **One-sentence summary at top:** "A data infrastructure that takes raw AD sensor data and progressively transforms it into ML-ready tables — so your training code reads one table, not six."
- **Three contributions (numbered, large font, framed as what the audience gains):**
  1. **Three-layer pipeline** (Raw → Cleaned → ML-ready) that automatically ingests, validates, and structures 14 AD entity types into queryable tables
  2. **One table per ML task:** A single pre-built table for each of object detection, SLAM, and sensor fusion — no joins in your training code
  3. **Scales where Python scripts don't:** Sub-100 ms data retrieval at 50× dataset scale, vs. 733 ms for the conventional Python approach (~8× faster)

**Figure:** `paper/figures/medallion_pipeline.png` — placed below the three contributions, spanning full width.

**Speaker notes:** "The idea is simple: instead of every training script re-implementing the same 6-table join to assemble its input data, we do that join once — at data ingestion time — and store the result as an ML-ready table. Your training code just reads one table. We do this through a three-layer pipeline: raw data goes in, cleaned and partitioned data comes out in the middle, and fully joined training-ready tables come out at the end. The result is data retrieval that stays under 100 milliseconds even at 50× scale, compared to 733 milliseconds with conventional Python scripts."

---

## Slide 4 — System Architecture

**Layout:** Figure-dominant (figure occupies ~65% of the slide)

**Title:** "System Architecture: Five-Service Docker Stack"

**Figure:** `paper/figures/architecture.png` — centered, large

**Key callouts (3–4 bullets beside or below figure, explained in terms of what users interact with):**
- **Spark (PySpark):** Runs the data pipeline — transforms raw JSON into ML-ready tables. This is where the joins and optimizations happen, once, so your training code doesn't have to.
- **Polaris (Catalog):** A central registry so every tool sees the same tables. If Spark writes a Gold table, Trino and Superset can immediately query it — no file-path wrangling.
- **MinIO (Storage):** S3-compatible object storage. In production, swappable to Ceph or cloud S3 — your code doesn't change.
- **Trino + Superset:** *For you:* SQL query access and visual dashboards to explore the dataset without writing Python. E.g., "show me all frames from clip X where category = pedestrian."
- **One command:** `docker compose up` launches everything.

**Speaker notes:** "From your perspective as an ML researcher, the parts you'd interact with are: Trino, for running SQL queries to explore the data; Superset, for visual dashboards; and the Gold tables that your training code reads. Spark runs the pipeline behind the scenes. The key point is that all of these tools share the same catalog — so data written by Spark is immediately visible to Trino and Superset without copying anything. And the whole stack launches with a single docker-compose command."

---

## Slide 5 — KAIST Data Model (3-Level Hierarchy)

**Layout:** Figure-dominant with annotation sidebar

**Title:** "KAIST E2E Data Model: 3-Level Hierarchy"

**Figure:** `paper/figures/data_model.png` — large, centered

**Sidebar annotations (3–4 bullets):**
- **Session → Clip → Frame** hierarchy supports long-duration, multi-session autonomous driving recordings
- Generalizes nuScenes' 2-level (Scene → Sample) model by adding the Session level for multi-drive campaigns
- **14 entity types** total: 3 hierarchy (Session, Clip, Frame), 4 sensors (Camera, LiDAR, Radar, Ego Motion), 4 annotations (Dynamic Object, Occupancy, Motion, Category), 3 metadata (Calibration, HD Map, Session Ego Motion)
- Named geometric structs: **SE3** (4×4 transform), **Quaternion** (qw,qx,qy,qz), **Box3D** (7-DOF bounding box), **Translation3D** (x,y,z)

**Speaker notes:** "The KAIST E2E dataset uses a three-level hierarchy. A Session represents an entire driving session. Each Session contains multiple Clips — contiguous recording segments. Each Clip contains Frames — single time-steps. At the Frame level, we have all sensor modalities and annotations attached. This is richer than nuScenes' two-level model and supports the kind of long-duration, multi-session recordings we expect from the project's vehicles."

---

## Slide 6 — Three-Layer Pipeline: Raw → Cleaned → ML-Ready

**Layout:** Three-column layout with details, or use `medallion_pipeline.png` at top and detail table below

**Title:** "Three-Layer Pipeline: Raw Data → Cleaned Tables → ML-Ready Tables"

**Figure:** `paper/figures/medallion_pipeline.png` (smaller, top ⅓ of slide)

**Detail table (below figure, reframed as "what happens / why you care"):**

| Layer | What happens | Why you care | Tables |
|-------|-------------|--------------|--------|
| **Bronze** (Raw) | Each JSON file becomes one table. Schema is enforced — if a field is missing or wrong-typed, ingestion fails. | **Data integrity from day one.** You won't discover corrupt data mid-training. The raw data is always preserved for debugging. | 14 tables |
| **Silver** (Cleaned) | Data is physically reorganized: camera data stored by camera name, frames stored in temporal order within each clip. Statistics recorded on every column. | **Fast sensor-specific queries.** Ask for "all CAM_FRONT data from clip X" and the system skips 83% of unrelated data automatically. Frames come back in time order without explicit sorting. | 11 tables |
| **Gold** (ML-ready) | The exact joins your training code needs are pre-computed into single flat tables — one per ML task. | **Zero data-wrangling code in your training pipeline.** Read one table, get everything: image paths, 3D boxes, calibration, ego pose — all pre-joined. | 3 tables |

**Key point (bold, below table):**
> "Each layer is designed around how AD ML pipelines actually access data — by sensor, by time range, and by task."

**Speaker notes:** "Think of this as three stages. Stage one: raw data comes in, we validate the schema, and store it as-is — this is your audit trail. Stage two: we reorganize the data based on how ML pipelines actually query it. If your object detection code always asks for 'all CAM_FRONT data from clip X,' we physically group the data that way so the system can skip 83% of irrelevant files without scanning them. Stage three: we pre-compute the joins. Instead of your DataLoader joining 6 tables every batch, we do that join once and store the result. Your training code reads one table."

---

## Slide 7 — Gold Table Designs

**Layout:** Figure-dominant with the three Gold table cards

**Title:** "Gold Tables: Pre-Joined, ML-Ready"

**Figure:** `paper/figures/gold_tables.png` — spanning full width

**Additional notes (below figure, 2 lines):**
- Each Gold table eliminates a specific multi-table join pattern that ML training code would otherwise perform at runtime
- Partition keys chosen to match the dominant filter predicate for each workload (sensor name for detection, clip for temporal workloads)

**Table (compact, reinforcing the figure):**

| Gold Table | ML Workload | Joins Eliminated | Partition Key | Speedup |
|---|---|---|---|---|
| `camera_annotations` | Object detection | 6-table join | `camera_name` | **3.2×** |
| `lidar_with_ego` | SLAM / localization | 3-table join | `clip_id` | **2.2×** |
| `sensor_fusion_frame` | Multi-modal fusion | 5-table join + 3 agg. | `clip_id` | **2.0×** |

**Speaker notes:** "For object detection, training code needs camera images joined with frame metadata, clip hierarchy, calibration, annotations, and HD map data — that's a 6-table join. The camera_annotations Gold table pre-computes all of this, partitioned by camera name. For SLAM, the lidar_with_ego table pre-joins LiDAR with ego motion and calibration. For sensor fusion, we aggregate all modalities into one row per frame. The speedups range from 2× to 3.2×."

---

## Slide 8 — What "Workload Benchmark" Means (and Doesn't Mean)

**Layout:** Top: framing text. Middle: three-column "workload card" layout. Bottom: bar chart.

**Title:** "What We Measured: Data Retrieval for ML Training Pipelines"

**Important framing text (show at top of slide, prominent):**
> **We did not run model training.** We measured the *data retrieval step* — the
> query that an ML training pipeline executes to assemble its input batch.
> Every model needs this step; it runs once per epoch; it is the I/O
> bottleneck that scales with dataset size.

**Three-column workload explanation (the core of this slide):**

Each column describes one workload in terms an ML researcher would recognize:

| | Object Detection | SLAM / Localization | Sensor Fusion |
|---|---|---|---|
| **Example models** | BEVFormer, DETR3D, CenterPoint | ORB-SLAM, LIO-SAM, KISS-ICP | TransFusion, BEVFusion, UniAD |
| **What training code needs** | Camera image path + 3D bounding boxes + category labels + camera intrinsics/extrinsics, *for one specific camera* | LiDAR point cloud path + ego vehicle pose (translation + quaternion) + extrinsic calibration, *for one driving clip* | All sensors (6 cameras + LiDAR + radar) + annotations aggregated into *one row per time-step*, for one clip |
| **Where that data lives (Silver)** | Scattered across 6 tables: `camera`, `frame`, `clip`, `calibration`, `dynamic_object`, `hdmap` | Across 3 tables: `lidar`, `ego_motion`, `calibration` | Across 5 tables + 3 group-by aggregations: `frame`, `camera`, `lidar`, `radar`, `dynamic_object` |
| **Where that data lives (Gold)** | Single table: `camera_annotations`, partitioned by camera name | Single table: `lidar_with_ego`, partitioned by clip | Single table: `sensor_fusion_frame`, partitioned by clip |
| **Analogy** | Like calling `nuScenes.get_sample_data()` with annotations, but pre-materialized | Like reading a single KITTI sequence directory, but as a table query | Like assembling a full `nuscenes Sample` across all modalities |

**Bar chart:** `paper/figures/workload_benchmark.png` — smaller, placed in lower ⅓

**Result table (compact, beside chart):**

| Workload | Gold (ms) | Silver JOIN (ms) | Speedup | Rows |
|---|---|---|---|---|
| Object Detection | 79 | 255 | **3.2×** | 23,150 |
| SLAM / Localization | 64 | 138 | **2.2×** | 389 |
| Sensor Fusion | 49 | 99 | **2.0×** | 389 |

**Speaker notes:** "I want to be precise about what we measured here, because we did *not* run model training end-to-end. What we measured is the data retrieval step — the query that a training pipeline runs to load its input data. If you're training BEVFormer for 3D object detection, your data loader needs camera images, bounding boxes, categories, and calibration for a specific camera. Without the lakehouse, that data is scattered across 6 separate tables — camera metadata, frame info, clip hierarchy, calibration parameters, annotations, and HD map data. Your training code has to join all 6 at runtime, every epoch. With the Gold table, it's a single filtered read — the join was done once at ingestion time. The 3.2× speedup means that this data assembly step takes 79 ms instead of 255 ms. That matters because at real dataset scale — tens of millions of frames — this I/O step becomes the dominant bottleneck, and it repeats every training epoch."

---

## Slide 8b — Benchmark Methodology (Backup Detail)

> **Note:** This is an optional slide to show *only if asked* about methodology
> details. Do not present it in the main flow. Keep it ready for Q&A.

**Layout:** Text-heavy detail slide

**Title:** "Benchmark Methodology Detail"

**Key points:**
- **Fair comparison:** Each Silver query replicates *exactly* the same join graph used to build the corresponding Gold table (e.g., the 6-table Object Detection Silver query mirrors `build_camera_annotations()` line-for-line)
- **Same filter predicate** applied to both Gold and Silver (e.g., `WHERE camera_name = 'CAM_BACK'`) — isolates join cost, not filter cost
- **Timing protocol:** JVM pre-warmed (3 throwaway queries) → 2 untimed warmup runs → 5 timed runs → **median** reported
- **Metric:** `df.count()` action — measures scan + join time only, excludes Python serialization overhead
- **Real predicates:** Filter values sampled from live data, not hardcoded
- KAIST simulated dataset · 14 tables · 140K camera annotations · 3,935 frames
- Environment: Single-node Docker, Spark 3.5.5, Iceberg 1.8.1, Polaris REST catalog, MinIO

---

## Slide 9 — Experiment 2: Scalability (nuScenes)

**Layout:** Chart-dominant

**Title:** "Scalability: Latency vs. Data Scale (nuScenes, 1×–50×)"

**Figure:** `paper/figures/scalability.png` — large, upper ⅔ of slide

**Key findings (3 bullets below chart, framed as impact on training):**
1. **Gold stays under 100 ms at every scale** (42 ms → 87 ms at 50×). That means data loading never becomes your training bottleneck — even as the dataset grows 50×.
2. **The conventional Python approach slows linearly** (15 ms → 733 ms). At full KAIST dataset scale, this would dominate your per-epoch time.
3. **At small scale, Python is actually faster** (no Spark startup overhead). The advantage flips at ~20× and the gap widens to 8.4× at 50×. This tells us: the infrastructure pays for itself once datasets are non-trivial.

**Workload description (small italic text):**
> **Task:** "Load front-camera images with adult-pedestrian 3D annotations" — the data step you'd run before feeding a batch to BEVFormer or DETR3D. Tested on nuScenes v1.0-mini, 18 scale points from SF 1 to 50.

**Speaker notes:** "This chart shows what happens as the dataset grows. The task is realistic: load camera images and pedestrian annotations for the front camera — exactly what you'd do at the start of a training loop for 3D object detection. With the conventional Python approach — the kind of `for` loop you see in nuScenes tutorials — data loading time scales linearly. At 50× scale, that's 733 milliseconds per query. With the Gold table, it stays at 87 milliseconds — because the join was already done, and the system skips irrelevant data files. The takeaway is: at small scale, just use Python. But once you're working with real project-scale data, the infrastructure pays for itself immediately."

---

## Slide 10 — Built-in Features That Matter for ML Workflows

**Layout:** Three-panel figure with supporting text

**Title:** "Built-in Features That Matter for ML Workflows"

**Figure:** `paper/figures/supplementary_benchmarks.png` — full width, upper ⅔

**Three-column callouts (below figure, framed as ML scenarios):**

| ML Scenario | What the system does automatically | Measured impact |
|-------------|------------------------------------|-----------------|
| **"I only need CAM_FRONT data"** | The system physically groups data by sensor name. When you filter by camera, it skips the files for the other 5 cameras entirely — no scanning needed. | 83% of data skipped automatically; combined camera + clip filter → 98.4% skipped |
| **"I need frames in time order for a clip"** | Data is pre-sorted by timestamp within each clip on disk. Sequential replay reads data in order without an explicit sort. | 1.8× faster than assembling the sequence at query time |
| **"I only need data from a 5-second window"** | Timestamp statistics are stored per data file. The system checks each file's min/max timestamp and skips files outside your window before reading anything. | 4.8× speedup for narrow time-range queries |

**Additional validated feature (text only, important for ML reproducibility):**
- **Dataset pinning / "time travel":** You can tag a specific version of the data and read it back later, even after new data has been added. We validated this: after doubling the dataset (23,150 → 46,300 rows), querying the pinned version returned exactly 23,150 rows. This means you can always reproduce exactly the data you trained on — without manual file snapshots.

**Speaker notes:** "These features come free with the infrastructure — you don't write extra code for them. If your training script asks for CAM_FRONT data, the system physically skips the other 5 cameras' files. That's 83% of I/O eliminated automatically. If you need frames in time order for sequential models like video transformers, the data is already stored in timestamp order. And if you need to reproduce a specific experiment, you can pin the exact dataset version and read it back months later, even after the dataset has been updated. That last point is especially important for this project — when we submit results, we need to be able to say exactly which data was used."

---

## Slide 11 — Data Quality: "Is the Data Correct?"

**Layout:** Table/figure with pipeline reliability callout

**Title:** "Automated Validation: Catching Data Errors Before They Reach Your Model"

**Figure:** `paper/figures/validation_summary.png` — upper half

**Key points (below table, framed as what kind of errors are caught):**

| What we check | Why it matters for ML | Count |
|---------------|----------------------|-------|
| **No duplicate records** | Duplicate frames would bias your training distribution. We verify every record is unique. | 6 checks |
| **Cross-table references are valid** | If a camera record references frame_id "X", frame "X" must exist. Broken references → missing data in your training batch. | 4 checks |
| **Rotation quaternions are unit-norm** | $\|q\| \approx 1.0 \pm \epsilon$. A non-unit quaternion means corrupted ego-pose or annotation rotation — your 3D boxes would be wrong. | 2 checks |
| **Timestamps are non-negative** | Negative timestamps indicate data corruption. Would break any time-based filtering or temporal model. | 4 checks |
| **Gold table row counts match** | Verifies that the pre-joining step didn't drop or duplicate data. | 4 checks |
| **TOTAL** | **All 20 checks pass** on every run | **20** |

**Pipeline execution summary (compact box):**
```
[PHASE 1/4] Ingest raw data           ─── 14 tables from JSON
[PHASE 2/4] Reorganize for fast access ─── 11 optimized tables
[PHASE 3/4] Build ML-ready tables      ─── 3 pre-joined tables
[PHASE 4/4] Validate everything        ─── 20 checks, ALL PASS
Total: ~24 seconds end-to-end
```

**Speaker notes:** "Every time data flows through the pipeline, 20 automated checks run. These aren't abstract database checks — they catch real problems. Duplicate frames would bias your training set. Broken cross-references would mean your DataLoader gets empty annotations for some frames. Non-unit quaternions would mean your ego-pose or bounding box rotations are wrong — your 3D geometry would be silently corrupted. We check all of this automatically, every run. If any critical check fails, the pipeline stops before bad data can reach a Gold table."

---

## Slide 12 — Current Status & Next Steps

**Layout:** Two-column: left = accomplished, right = future work

**Title:** "Current Status & Roadmap"

**Left column — Accomplished (with checkmarks):**
- [x] Full medallion pipeline (Bronze → Silver → Gold → Validate) operational
- [x] 14 Bronze tables, 11 Silver tables, 3 Gold tables
- [x] KAIST 3-level schema implemented with 14 entity types
- [x] Validated on KAIST-simulated data and nuScenes v1.0-mini (public)
- [x] 5-service Docker Compose stack (Spark, Polaris, MinIO, Trino, Superset)
- [x] Benchmark suite: 5 experiments, all results reproducible
- [x] Paper draft in preparation (domestic conference, 2 pages)

**Right column — Next steps:**
- [ ] **Production-scale validation:** Test with full KAIST E2E dataset on multi-node cluster
- [ ] **Streaming ingestion:** Integrate live vehicle sensor data via Kafka → Iceberg append
- [ ] **PyTorch DataLoader integration:** Direct ML training from Gold Iceberg tables (no intermediate export)
- [ ] **Ceph S3 backend:** Replace MinIO with production Ceph object storage
- [ ] **Extended scalability testing:** Beyond 50× synthetic scale to real TB-scale data

**Known limitations (small text, bottom):**
- Current benchmarks are single-node; Silver skips 3 low-priority tables (occupancy, motion, session_ego_motion); 2 schemas use placeholder fields

**Speaker notes:** "To summarize the current status: the full pipeline is operational end-to-end. All ingestion, transformation, and validation works. We've validated it on simulated KAIST data and the public nuScenes dataset. The Docker stack launches with a single command. Going forward, the key priorities are testing at production scale with the real KAIST data, adding streaming ingestion for live vehicle data, and building a direct PyTorch DataLoader so training pipelines can read from Gold tables without intermediate export steps."

---

## Slide 13 — Summary / Conclusion

**Layout:** Clean summary slide with key numbers

**Title:** "Summary"

**Three key takeaways (large font, one per section):**

1. **Your training code gets simpler:** Instead of writing 6-table join logic in every training script, read a single ML-ready table. We handle ingestion, validation, and pre-joining for 14 AD entity types automatically.
   
2. **Data loading gets 2–8× faster:** Pre-joined tables are 2–3× faster than runtime joins for object detection, SLAM, and sensor fusion. At 50× dataset scale, the gap vs. conventional Python scripts widens to 8.4×.

3. **Reproducibility is built in:** Pin your training dataset to a specific version. Even after new data arrives, you can re-read the exact data you trained on — no manual snapshots needed.

**Bottom banner (bold):**
> "Open-source data infrastructure for the KAIST/MOTIE AD project: raw sensors in → validated, ML-ready tables out."

**Speaker notes:** "Three things to take away. First: this infrastructure means less boilerplate in your training code. You don't write join logic — you read one table. Second: that simplification also makes data loading faster — 2 to 3× for the core workloads, and 8× faster than Python scripts once datasets get large. Third: reproducibility. You can pin the exact version of the data you trained on and come back to it months later. That's important for paper submissions and for regulatory compliance. The whole stack is open source and launches with one command."

---

## Backup Slide A — Technology Stack Details

**Layout:** Table-dominant

**Title:** "Technology Stack"

| Component | Technology | Version | Role |
|-----------|-----------|---------|------|
| ETL Engine | Apache Spark (PySpark) | 3.5.5 | Bronze→Silver→Gold pipeline |
| Table Format | Apache Iceberg | 1.8.1 (v2) | ACID, time travel, schema evolution |
| Catalog | Apache Polaris | Latest | REST catalog, unified metadata |
| Object Storage | MinIO | 2025-09 | S3-compatible (dev); swappable to Ceph |
| Query Engine | Trino | 479 | Interactive SQL, BI queries |
| BI Dashboard | Apache Superset | Latest | Visualization, exploration |
| Orchestration | Docker Compose | — | Single-command deployment |

---

## Backup Slide B — Schema Details (KAIST 14 Tables)

**Layout:** Compact multi-column table

**Title:** "KAIST Schema: 14 Entity Types"

| Table | Primary Key | Key Fields | Partition (Silver) |
|-------|------------|------------|-------------------|
| session | session_id | session_name, clip_id_list | — |
| clip | clip_id | session_id, clip_idx, date | session_id |
| frame | frame_id | clip_id, frame_idx, sensor_timestamps | clip_id |
| calibration | clip_id+sensor_name | extrinsics (SE3), camera_intrinsics | clip_id, sensor_name |
| camera | frame_id+camera_name | clip_id, sensor_timestamp, filename | camera_name, clip_id |
| lidar | frame_id | clip_id, sensor_timestamp, filename | clip_id |
| radar | frame_id+radar_name | clip_id, sensor_timestamp, filename | radar_name, clip_id |
| category | category | (reference table) | — |
| dynamic_object | frame_id | clip_id, boxes_3d (Box3D), category | clip_id |
| ego_motion | frame_id | clip_id, translation (3D), rotation (Quat) | clip_id |
| occupancy | frame_id | clip_id, occupancy_data* | clip_id |
| motion | frame_id | clip_id, motion_data* | clip_id |
| session_ego_motion | session_id | translation, rotation, start, goal | — |
| hdmap | clip_id | filename, city, site | — |

*Placeholder schemas — to be refined with actual KAIST data

---

## Backup Slide C — Full Scalability Data Table

**Layout:** Dense data table

**Title:** "nuScenes Scalability — Full Results (18 Scale Factors)"

| SF | Effective Rows | Python (ms) | Silver (ms) | Gold (ms) | Gold vs Python |
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

---

## Backup Slide D — Benchmark Methodology

**Layout:** Text-heavy methodology slide

**Title:** "Benchmark Methodology"

**Experiment 1 (KAIST — Three Workloads):**
- Dataset: KAIST-simulated 3-level dataset (14 tables, 140K camera annotations, 3,935 frames)
- Methodology: 2 warmup + 5 timed runs, median
- Metric: `df.count()` to isolate scan+join time (no serialization overhead)
- Environment: Single-node Docker, Spark 3.5.5, Iceberg 1.8.1, Polaris REST catalog, MinIO

**Experiment 2 (nuScenes — Scalability):**
- Dataset: nuScenes v1.0-mini (public), 7 core JSON tables
- Scaling: Synthetic replication of observation tables (sample_data) from 1× to 50× (18 sample points)
- Reference tables (category, sensor) remain at 1× — mimics realistic growth
- Python baseline: median of 5 runs; Spark strategies: 1 warmup + median of 3 runs
- Workload: "Front camera images with adult pedestrian 3D annotations"

---

## Design & Formatting Guidelines

**General:**
- Use a clean, modern slide template (dark header bar, white body)
- Consistent color coding throughout: Gold = amber/orange (#E8A838), Silver = steel blue (#6C8EBF), Python/Bronze = contextual
- All charts use the pre-generated figures from `paper/figures/`
- Slide numbers in footer
- Project name and date in footer

**Typography:**
- Slide titles: 28–32 pt, bold
- Body text: 18–22 pt
- Table text: 14–16 pt
- Speaker notes: not displayed, for presenter reference

**Figure placement:**
- Figures should fill at least 50% of the slide area when they are the primary content
- Use consistent margins and alignment
- No figure borders; figures have built-in white backgrounds

**Transitions:**
- Simple fade or none — no animated transitions
- Build bullets one at a time where it aids storytelling (slides 2, 9, 12)
