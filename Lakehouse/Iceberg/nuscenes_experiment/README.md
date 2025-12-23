# Performance Analysis of Data Lakehouse based on Iceberg OTF

<img width="984" height="584" alt="output" src="https://github.com/user-attachments/assets/08912181-8d2e-4d5d-b9d3-19d3d7c181e5" />

This project investigates the design and performance of a **Data Lakehouse** using **Apache Iceberg**, focusing on the migration from a legacy file-based data lake to a structured Lakehouse architecture.

The experiments utilize the **[nuScenes v1.0-mini](https://www.nuscenes.org/nuscenes)** autonomous driving dataset to compare performance across three evolutionary stages: **Baseline (Legacy)**, **Iceberg-Silver (Relational)**, and **Iceberg-Gold (Optimized)**.

---

## 📂 1. Dataset Overview: nuScenes v1.0-mini (Partial)

We utilized a subset of the **[nuScenes v1.0-mini](https://www.nuscenes.org/nuscenes)** dataset. The raw data consists of directory-based sensor files (images, pcd) and highly structured metadata stored in JSON format.

### Source Data Schema (Baseline Input)

For this experiment, we utilized 7 distinct JSON files to represent the dataset metadata. To generate the training dataset, the legacy system requires parsing and iteratively joining these files based on token keys.

* **Core Metadata:** `sample.json`, `sample_data.json`
* **Sensor Metadata:** `sensor.json`, `calibrated_sensor.json`
* **Annotation Metadata:** `sample_annotation.json`, `instance.json`, `category.json`

> **⚠️ Baseline Bottleneck:** Retrieving data for a specific condition (e.g., *"Front Camera only"*) requires scanning unrelated JSON objects and performing heavy in-memory joins using Python loops.

---

## 🏗️ 2. Architecture & Experimental Stages

This research compares three distinct architectural approaches to handling this complex metadata.

---

### Phase 1: Baseline (File-based Data Lake)

* **Structure:** **Raw Directory & Distributed JSONs**.
* The dataset consists of scattered sensor files and **7 distinct JSON metadata files** (e.g., `sample.json`, `sample_data.json`).
* **State:** Unstructured and schema-on-read; no indexing or partitioning is applied.


* **Method:** **Iterative Parsing & In-memory Join**.
* The system must **load all JSON files** into memory and parse them as Python dictionaries.
* Data linkage relies on **iterative lookups** (Python loops) to manually associate `sample`  `sample_data`  `annotation`.


* **Limitation:**
* Performance is **bottlenecked by sequential I/O and CPU overhead**. Retrieving specific data requires scanning entire JSON files regardless of the filter condition.



---

### Phase 2: Iceberg-Silver (Relational Lakehouse)

* **Structure:** **Normalized Tables (1:1 migration)**.
* Data is stored in separate Iceberg tables (e.g., `nessie.nusc_db.samples`, `nessie.nusc_db.annotations`).
* **Optimization:** The `sample_data` table is **partitioned by `channel**`, enabling **Partition Pruning** during sensor data retrieval.


* **Method:** **Runtime SQL Joins**.
* Queries must execute complex **multi-way joins** at runtime to link the filtered sensor data with annotations.


* **Limitation:**
* Despite partition pruning on `sample_data`, performance is **bottlenecked by the Shuffle Join** overhead. The engine must scan the large, unpartitioned `annotations` table and shuffle data across the cluster to match records.



---

### Phase 3: Iceberg-Gold (Optimized Data Mart)

* **Structure:** **Single Denormalized Table**.
* All necessary features (Image paths, 3D Boxes, Categories, Channels) are **pre-joined** into a single table: `nessie.nusc_db.sample_data_gold`.
* **Optimization:** The entire table is physically **partitioned by `channel**`, aligning data storage with the query pattern.


* **Method:** **Zero-Join & Partition Pruning**.
* The query engine leverages **Partition Pruning** to read *only* the specific folder (e.g., `channel=CAM_FRONT`), skipping all unrelated data.
* No runtime joins are required, as the schema is already flattened.


* **Advantage:**
* **Eliminates Shuffle Joins** entirely and **minimizes I/O** to the absolute minimum, resulting in consistent sub-second query latency suitable for ML data loading.

## ❄️ 3. Migrated Table Schema (Gold Layer)

The **Iceberg-Gold** table is designed to support ML data loading workloads efficiently. It consolidates all features into a flat schema.

| Column Name | Data Type | Description | Source (Origin) |
| --- | --- | --- | --- |
| `img_path` | `string` | File path derived from `filename` | `sample_data` |
| `translation` | `array<double>` | 3D Global coordinates (x, y, z) | `sample_annotation` |
| `size` | `array<double>` | Object dimensions (w, l, h) | `sample_annotation` |
| `rotation` | `array<double>` | Orientation (Quaternion) | `sample_annotation` |
| `category_name` | `string` | Object classification | `category` |
| **`channel`** | **`string`** | **Sensor Channel (Partition Key)** | `sensor` |

> **Note on Partitioning:** The table is partitioned by the **`channel`** column (e.g., `CAM_FRONT`, `LIDAR_TOP`). This allows the query engine to instantly skip unrelated sensor partitions.

---

## 🎯 4. Experimental Workload

We designed a specific query workload to measure the performance gap between the Baseline, Silver, and Gold stages.

### Target Scenario

The experiment simulates a real-world Autonomous Driving ML data preparation task:

> *"Retrieve image paths and 3D bounding box parameters for **Adult Pedestrians** captured by the **Front Camera**."*

### Query Filters

To evaluate **Partition Pruning** and **Column Projection** capabilities, we applied the following filters:

1. **Sensor Filter:** `channel = 'CAM_FRONT'` (Tests Partition Pruning)
2. **Category Filter:** `category_name = 'human.pedestrian.adult'` (Tests Row Filtering)

### Final Output Data

All three experiments produce the exact same dataset required for training 3D object detection models:

```json
{
  "img_path": "samples/CAM_FRONT/n015-2018...jpg",
  "bbox_translation": [373.21, 1130.48, 1.25],
  "bbox_size": [0.62, 0.67, 1.64],
  "bbox_rotation": [0.98, 0.00, 0.00, -0.18]
}

```

---

## 📊 5. Performance Benchmarks

We measured query execution time across different data scales to evaluate scalability.

### Experiment Conditions

* **Metric:** Query execution time (seconds)
* **Variable:** Scale Factor (N), resulting in approx  data growth.

### Result Table

| Scale Factor (N) | Multiplier () | Approx. Row Count | Baseline (File-based) | Iceberg-Silver (Relational Join) | Iceberg-Gold (Single-table) |
| --- | --- | --- | --- | --- | --- |
| **1** | 1x | 27,483 | 0.0620s | 0.2445s | 0.0675s |
| **3** | 9x | 247,347 | 0.4626s | 0.4353s | 0.0993s |
| **5** | 25x | 687,075 | 1.1693s | 0.6587s | 0.1250s |
| **7** | 49x | 1,346,667 | **2.1338s** | **0.9681s** | **0.1497s** |

### Key Findings

1. **Bottleneck of Legacy System:**
* The **Baseline** shows linear (or worse) performance degradation () as data volume increases. The overhead of listing files and parsing JSON in Python becomes the dominant factor.


2. **Cost of Joins (Silver):**
* **Iceberg-Silver** is initially slower than Baseline at low scale () due to the overhead of distributed computing (Spark) and metadata handling.
* While it scales better than Baseline, it still suffers from **Runtime Join costs** between the partitioned `sample_data` and unpartitioned `annotations`.


3. **Efficiency of Lakehouse (Gold):**
* **Iceberg-Gold** demonstrates superior scalability, maintaining sub-second latency () even at 49x scale.
* By leveraging **Partition Pruning** (skipping files) and **Pre-computation** (eliminating joins), it outperforms the Baseline by approximately **14x** at scale.
