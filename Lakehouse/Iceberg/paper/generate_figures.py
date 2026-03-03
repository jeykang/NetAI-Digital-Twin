#!/usr/bin/env python3
"""Generate all figures for the slide deck presentation."""

import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import numpy as np
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "paper" / "figures"
OUT.mkdir(exist_ok=True)

# ============================================================================
# Color palette (professional, presentation-ready)
# ============================================================================
C_GOLD = "#E8A838"
C_SILVER = "#6C8EBF"
C_PYTHON = "#D4526E"
C_BRONZE = "#CD7F32"
C_BG = "#FAFAFA"
C_GRID = "#E0E0E0"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 13,
    "axes.facecolor": C_BG,
    "figure.facecolor": "white",
    "axes.grid": True,
    "grid.color": C_GRID,
    "grid.alpha": 0.6,
})


# ============================================================================
# Figure 1: System Architecture Diagram
# ============================================================================
def fig1_architecture():
    fig, ax = plt.subplots(figsize=(14, 8))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 8)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    def draw_box(x, y, w, h, label, color, sublabel=None, fontsize=13):
        rect = mpatches.FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.15",
            facecolor=color, edgecolor="#333333", linewidth=1.5, alpha=0.92
        )
        ax.add_patch(rect)
        ax.text(x + w/2, y + h/2 + (0.12 if sublabel else 0), label,
                ha="center", va="center", fontsize=fontsize, fontweight="bold",
                color="white" if color not in ["#F0F0F0", "#E8F4FD", "#FFF8E1"] else "#333333",
                path_effects=[pe.withStroke(linewidth=2, foreground="#00000030")])
        if sublabel:
            ax.text(x + w/2, y + h/2 - 0.22, sublabel,
                    ha="center", va="center", fontsize=9, color="white",
                    alpha=0.85)

    def draw_layer_label(y, label, color="#888888"):
        ax.text(0.3, y, label, ha="left", va="center", fontsize=11,
                fontweight="bold", color=color, fontstyle="italic")

    # Layer labels
    draw_layer_label(7.3, "QUERY LAYER", "#555555")
    draw_layer_label(5.5, "CATALOG LAYER", "#555555")
    draw_layer_label(3.7, "TABLE FORMAT", "#555555")
    draw_layer_label(1.9, "STORAGE LAYER", "#555555")

    # Layer backgrounds
    for y, c in [(6.5, "#E8F4FD40"), (4.7, "#FFF8E140"), (2.9, "#E8F5E940"), (1.1, "#FCE4EC40")]:
        ax.add_patch(mpatches.FancyBboxPatch(
            (2.0, y), 10.5, 1.4, boxstyle="round,pad=0.1",
            facecolor=c, edgecolor="#CCCCCC", linewidth=0.8
        ))

    # Query Layer
    draw_box(2.5, 6.7, 2.8, 1.0, "Apache Spark", "#4A90D9", "ETL / ML (PySpark)")
    draw_box(5.8, 6.7, 2.2, 1.0, "Trino", "#7B68EE", "Interactive SQL")
    draw_box(8.5, 6.7, 2.8, 1.0, "Apache Superset", "#E67E22", "BI / Dashboards")

    # Catalog Layer
    draw_box(4.8, 4.9, 3.4, 1.0, "Apache Polaris", "#2ECC71", "REST Catalog (Iceberg v2)")

    # Table Format Layer
    draw_box(4.8, 3.1, 3.4, 1.0, "Apache Iceberg v2", "#34495E", "ACID · Time Travel · Schema")

    # Storage Layer
    draw_box(4.8, 1.3, 3.4, 1.0, "MinIO (S3)", "#C0392B", "Object Storage")

    # Arrows
    arrow_style = dict(arrowstyle="-|>", color="#555555", lw=1.8, mutation_scale=15)
    for sx in [3.9, 6.9, 9.9]:
        ax.annotate("", xy=(6.5, 6.0), xytext=(sx, 6.7),
                     arrowprops=dict(arrowstyle="-|>", color="#888888", lw=1.2, mutation_scale=12))
    ax.annotate("", xy=(6.5, 4.0), xytext=(6.5, 4.9), arrowprops=arrow_style)
    ax.annotate("", xy=(6.5, 2.2), xytext=(6.5, 3.1), arrowprops=arrow_style)

    # Title
    ax.text(7.0, 0.45, "Docker Compose — Single-node Development Stack",
            ha="center", va="center", fontsize=10, color="#888888", fontstyle="italic")

    fig.savefig(OUT / "architecture.png", dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  ✓ {OUT / 'architecture.png'}")


# ============================================================================
# Figure 2: Data Model — 3-Level Hierarchy
# ============================================================================
def fig2_data_model():
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 7)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    def draw_entity(x, y, w, h, label, color, sublabel=None, fontsize=12):
        rect = mpatches.FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.12",
            facecolor=color, edgecolor="#333333", linewidth=1.5, alpha=0.92
        )
        ax.add_patch(rect)
        ax.text(x + w/2, y + h/2 + (0.1 if sublabel else 0), label,
                ha="center", va="center", fontsize=fontsize, fontweight="bold", color="white")
        if sublabel:
            ax.text(x + w/2, y + h/2 - 0.18, sublabel,
                    ha="center", va="center", fontsize=8.5, color="white", alpha=0.8)

    # Level 1: Session
    draw_entity(5.5, 5.8, 3.0, 0.8, "Session", "#8E44AD", "Long-duration drive")

    # Level 2: Clip
    draw_entity(5.5, 4.2, 3.0, 0.8, "Clip", "#2980B9", "Contiguous segment")

    # Level 3: Frame
    draw_entity(5.5, 2.6, 3.0, 0.8, "Frame", "#27AE60", "Single time-step")

    # Sensors & Annotations (Level 4)
    sensor_y = 0.8
    draw_entity(0.5, sensor_y, 2.0, 0.8, "Camera", "#E74C3C", "6 views")
    draw_entity(3.0, sensor_y, 2.0, 0.8, "LiDAR", "#D35400", "Point cloud")
    draw_entity(5.5, sensor_y, 2.0, 0.8, "Radar", "#F39C12", "Doppler")
    draw_entity(8.0, sensor_y, 2.2, 0.8, "Ego Motion", "#16A085", "SE3 pose")
    draw_entity(10.7, sensor_y, 2.5, 0.8, "Annotations", "#7F8C8D", "3D boxes, cat.")

    # Arrows
    arrow_kw = dict(arrowstyle="-|>", color="#555555", lw=1.8, mutation_scale=14)
    ax.annotate("", xy=(7.0, 5.0), xytext=(7.0, 5.8), arrowprops=arrow_kw)
    ax.annotate("", xy=(7.0, 3.4), xytext=(7.0, 4.2), arrowprops=arrow_kw)
    # Frame to sensors
    for tx in [1.5, 4.0, 6.5, 9.1, 11.95]:
        ax.annotate("", xy=(tx, 1.6), xytext=(7.0, 2.6), arrowprops=dict(
            arrowstyle="-|>", color="#888888", lw=1.0, mutation_scale=10
        ))

    # Multiplicity labels
    ax.text(7.2, 5.45, "1 : N", fontsize=9, color="#555", fontstyle="italic")
    ax.text(7.2, 3.85, "1 : N", fontsize=9, color="#555", fontstyle="italic")
    ax.text(4.3, 2.15, "1 : N per sensor", fontsize=9, color="#555", fontstyle="italic")

    # Title / legend
    ax.text(7.0, 6.8, "KAIST 3-Level Data Hierarchy: Session → Clip → Frame → Sensors",
            ha="center", fontsize=14, fontweight="bold", color="#333333")
    ax.text(7.0, 0.15, "14 entity types  ·  Named geometric structs (SE3, Quaternion, Box3D)  ·  Generalizes nuScenes 2-level model",
            ha="center", fontsize=9.5, color="#888888", fontstyle="italic")

    fig.savefig(OUT / "data_model.png", dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  ✓ {OUT / 'data_model.png'}")


# ============================================================================
# Figure 3: Medallion Pipeline (Bronze → Silver → Gold)
# ============================================================================
def fig3_medallion():
    fig, ax = plt.subplots(figsize=(15, 5.5))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 5.5)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    def draw_layer_box(x, y, w, h, title, color, items, title_fontsize=14):
        # Main box
        rect = mpatches.FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.15",
            facecolor=color, edgecolor="#333333", linewidth=2, alpha=0.15
        )
        ax.add_patch(rect)
        # Header bar
        header = mpatches.FancyBboxPatch(
            (x, y+h-0.6), w, 0.6, boxstyle="round,pad=0.1",
            facecolor=color, edgecolor="none", alpha=0.85
        )
        ax.add_patch(header)
        ax.text(x + w/2, y + h - 0.3, title, ha="center", va="center",
                fontsize=title_fontsize, fontweight="bold", color="white")
        for i, item in enumerate(items):
            ax.text(x + 0.3, y + h - 1.05 - i*0.35, f"• {item}",
                    fontsize=9, color="#333333", va="center")

    # Bronze
    draw_layer_box(0.3, 0.5, 3.8, 4.2, "Bronze Layer", C_BRONZE, [
        "1:1 JSON → Iceberg tables",
        "14 tables, all entity types",
        "Schema-enforced ingestion",
        "No transformations",
        "Preserves lineage",
        "ACID guarantees",
    ])

    # Silver
    draw_layer_box(5.3, 0.5, 4.2, 4.2, "Silver Layer", C_SILVER, [
        "Domain-aware partitioning",
        "camera → by camera_name, clip_id",
        "Iceberg sort orders (temporal)",
        "Column-level min/max metrics",
        "Predicate pushdown enabled",
        "Snapshot retention (time travel)",
        "11 tables optimized",
    ])

    # Gold
    draw_layer_box(10.7, 0.5, 4.0, 4.2, "Gold Layer", C_GOLD, [
        "camera_annotations (Obj. Det.)",
        "  → 6-table pre-join, by camera",
        "lidar_with_ego (SLAM)",
        "  → 3-table pre-join, by clip",
        "sensor_fusion_frame (Fusion)",
        "  → 5-table pre-join + 3 aggs",
        "Zero runtime joins",
    ])

    # Arrows between layers
    arrow_kw = dict(arrowstyle="-|>", color="#333333", lw=2.5, mutation_scale=20)
    ax.annotate("", xy=(5.2, 2.6), xytext=(4.2, 2.6), arrowprops=arrow_kw)
    ax.annotate("", xy=(10.6, 2.6), xytext=(9.6, 2.6), arrowprops=arrow_kw)

    ax.text(4.7, 3.05, "Partition &\nOptimize", ha="center", fontsize=8.5, color="#555",
            fontweight="bold")
    ax.text(10.1, 3.05, "Pre-join &\nDenormalize", ha="center", fontsize=8.5, color="#555",
            fontweight="bold")

    ax.text(7.5, 0.12, "Medallion Architecture — Each layer adds optimizations for AD workloads",
            ha="center", fontsize=10, color="#888888", fontstyle="italic")

    fig.savefig(OUT / "medallion_pipeline.png", dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  ✓ {OUT / 'medallion_pipeline.png'}")


# ============================================================================
# Figure 4: Gold vs Silver Benchmark (3 Workloads) — Grouped Bar Chart
# ============================================================================
def fig4_workload_benchmark():
    with open(BASE / "benchmarks" / "benchmark_results.json") as f:
        data = json.load(f)

    three_wl = [d for d in data if d["experiment"] == "Three-Workload"]

    workloads = ["Object Detection", "SLAM / Localization", "Multi-Modal Fusion"]
    gold_times = []
    silver_times = []
    row_counts = []

    for wl in workloads:
        gold = [d for d in three_wl if d["variant"].startswith("Gold:") and wl.split("/")[0].strip() in d["variant"]][0]
        silver = [d for d in three_wl if d["variant"].startswith("Silver JOIN:") and wl.split("/")[0].strip() in d["variant"]][0]
        gold_times.append(gold["elapsed_seconds"] * 1000)  # ms
        silver_times.append(silver["elapsed_seconds"] * 1000)
        row_counts.append(gold["row_count"])

    x = np.arange(len(workloads))
    width = 0.32

    fig, ax = plt.subplots(figsize=(10, 5.5))
    bars_gold = ax.bar(x - width/2, gold_times, width, label="Gold (pre-joined)",
                        color=C_GOLD, edgecolor="#333", linewidth=0.8, zorder=3)
    bars_silver = ax.bar(x + width/2, silver_times, width, label="Silver (runtime JOIN)",
                          color=C_SILVER, edgecolor="#333", linewidth=0.8, zorder=3)

    # Speedup annotations
    speedups = ["3.2×", "2.2×", "2.0×"]
    for i, sp in enumerate(speedups):
        ax.annotate(sp, xy=(x[i] + width/2, silver_times[i]),
                     xytext=(0, 8), textcoords="offset points",
                     ha="center", fontsize=11, fontweight="bold", color=C_PYTHON)

    # Value labels on bars
    for bar in bars_gold:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                f"{bar.get_height():.0f}", ha="center", va="bottom", fontsize=9, color="#555")
    for bar in bars_silver:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                f"{bar.get_height():.0f}", ha="center", va="bottom", fontsize=9, color="#555")

    ax.set_ylabel("Query Latency (ms)", fontsize=12)
    ax.set_xticks(x)
    ax.set_xticklabels(workloads, fontsize=11)
    ax.set_title("Gold vs. Silver Query Latency — Three AD Workloads", fontsize=14, fontweight="bold", pad=12)
    ax.legend(fontsize=11, loc="upper right")
    ax.set_ylim(0, max(silver_times) * 1.25)

    fig.savefig(OUT / "workload_benchmark.png", dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  ✓ {OUT / 'workload_benchmark.png'}")


# ============================================================================
# Figure 5: Scalability Line Chart (nuScenes 1×–50×)
# ============================================================================
def fig5_scalability():
    with open(BASE / "nuscenes_experiment" / "scalability_results.json") as f:
        data = json.load(f)

    strategies = {"Python Baseline": C_PYTHON, "Silver JOIN": C_SILVER, "Gold": C_GOLD}

    fig, ax = plt.subplots(figsize=(11, 6))

    for strat, color in strategies.items():
        pts = sorted([d for d in data if d["strategy"] == strat], key=lambda d: d["scale_factor"])
        sfs = [d["scale_factor"] for d in pts]
        times = [d["elapsed_seconds"] * 1000 for d in pts]  # ms
        marker = "o" if strat == "Python Baseline" else ("s" if strat == "Silver JOIN" else "D")
        ax.plot(sfs, times, marker=marker, label=strat, color=color,
                linewidth=2.2, markersize=5, zorder=3)

    # Highlight crossover and 50× gap
    ax.axhline(y=100, color="#999", linestyle="--", linewidth=0.8, alpha=0.6)
    ax.text(51, 100, "100 ms", fontsize=8, color="#999", va="bottom")

    # Annotations at SF=50
    ax.annotate("733 ms", xy=(50, 733), xytext=(44, 770), fontsize=9, color=C_PYTHON,
                fontweight="bold", arrowprops=dict(arrowstyle="-", color=C_PYTHON, lw=0.8))
    ax.annotate("499 ms", xy=(50, 499), xytext=(44, 540), fontsize=9, color=C_SILVER,
                fontweight="bold", arrowprops=dict(arrowstyle="-", color=C_SILVER, lw=0.8))
    ax.annotate("87 ms", xy=(50, 87), xytext=(44, 130), fontsize=9, color=C_GOLD,
                fontweight="bold", arrowprops=dict(arrowstyle="-", color=C_GOLD, lw=0.8))

    # Crossover annotation
    ax.annotate("Crossover\n≈ SF 20", xy=(20, 297), xytext=(25, 400),
                fontsize=8.5, color="#555", ha="center",
                arrowprops=dict(arrowstyle="->", color="#555", lw=0.8))

    # Speedup box at SF=50
    ax.text(36, 680, "~8.4× gap at SF 50", fontsize=10, fontweight="bold",
            color=C_PYTHON, bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFF0F0", edgecolor=C_PYTHON, alpha=0.8))

    ax.set_xlabel("Scale Factor", fontsize=12)
    ax.set_ylabel("Query Latency (ms)", fontsize=12)
    ax.set_title("Scalability: Latency vs. Data Scale (nuScenes, 1×–50×)", fontsize=14, fontweight="bold", pad=12)
    ax.legend(fontsize=11, loc="upper left")
    ax.set_xlim(0, 53)
    ax.set_ylim(0, 820)

    fig.savefig(OUT / "scalability.png", dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  ✓ {OUT / 'scalability.png'}")


# ============================================================================
# Figure 6: Supplementary Benchmarks Summary (Partition Pruning, Time Travel, etc.)
# ============================================================================
def fig6_supplementary():
    with open(BASE / "benchmarks" / "benchmark_results.json") as f:
        data = json.load(f)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))

    # --- Panel A: Partition Pruning ---
    ax = axes[0]
    pruning = [d for d in data if d["experiment"] == "Partition Pruning"]
    labels = ["No filter\n(all parts.)", "1 partition\n(sensor)", "Combined\n(sensor+clip)"]
    vals = [pruning[0]["elapsed_seconds"]*1000, pruning[1]["elapsed_seconds"]*1000, pruning[2]["elapsed_seconds"]*1000]
    rows = [pruning[0]["row_count"], pruning[1]["row_count"], pruning[2]["row_count"]]
    colors_p = ["#95A5A6", C_SILVER, C_GOLD]
    bars = ax.bar(labels, vals, color=colors_p, edgecolor="#333", linewidth=0.8, width=0.6, zorder=3)
    for bar, rc in zip(bars, rows):
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+30,
                f"{rc:,} rows", ha="center", fontsize=8, color="#555")
    ax.set_ylabel("Latency (ms)", fontsize=10)
    ax.set_title("Partition Pruning", fontsize=12, fontweight="bold")
    ax.text(1.0, vals[1]*0.85, "83.3%\nskipped", ha="center", fontsize=9, color="white", fontweight="bold")

    # --- Panel B: Temporal Replay (Gold vs Silver) ---
    ax = axes[1]
    temporal = [d for d in data if d["experiment"] == "Temporal Replay"]
    gold_t = [d for d in temporal if d["variant"].startswith("Gold")][0]
    silver_t = [d for d in temporal if d["variant"].startswith("Silver JOIN")][0]
    labels_t = ["Gold\n(pre-sorted)", "Silver JOIN\n(runtime sort)"]
    vals_t = [gold_t["elapsed_seconds"]*1000, silver_t["elapsed_seconds"]*1000]
    bars = ax.bar(labels_t, vals_t, color=[C_GOLD, C_SILVER], edgecolor="#333", linewidth=0.8, width=0.5, zorder=3)
    ax.set_title("Temporal Replay", fontsize=12, fontweight="bold")
    ax.set_ylabel("Latency (ms)", fontsize=10)
    ax.annotate(f"1.8×", xy=(1, vals_t[1]), xytext=(0, 8), textcoords="offset points",
                ha="center", fontsize=11, fontweight="bold", color=C_PYTHON)

    # --- Panel C: Column Metrics ---
    ax = axes[2]
    metrics = [d for d in data if d["experiment"] == "Column Metrics"]
    narrow = [d for d in metrics if "Narrow" in d["variant"]][0]
    full = [d for d in metrics if "Full" in d["variant"]][0]
    labels_m = ["Narrow\ntimestamp", "Full scan\n(no filter)"]
    vals_m = [narrow["elapsed_seconds"]*1000, full["elapsed_seconds"]*1000]
    bars = ax.bar(labels_m, vals_m, color=[C_GOLD, "#95A5A6"], edgecolor="#333", linewidth=0.8, width=0.5, zorder=3)
    ax.set_title("Column-Level Metrics", fontsize=12, fontweight="bold")
    ax.set_ylabel("Latency (ms)", fontsize=10)
    ax.annotate(f"4.8×", xy=(1, vals_m[1]), xytext=(0, 8), textcoords="offset points",
                ha="center", fontsize=11, fontweight="bold", color=C_PYTHON)

    fig.suptitle("Supplementary Iceberg Features — Validated on KAIST Dataset", fontsize=13, fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(OUT / "supplementary_benchmarks.png", dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  ✓ {OUT / 'supplementary_benchmarks.png'}")


# ============================================================================
# Figure 7: Gold Table Design Overview
# ============================================================================
def fig7_gold_tables():
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 5)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    table_data = [
        {
            "name": "camera_annotations",
            "workload": "Object Detection",
            "joins": "6 Silver tables",
            "partition": "camera_name",
            "rows": "140K annotations",
            "color": "#E74C3C",
            "x": 0.3,
        },
        {
            "name": "lidar_with_ego",
            "workload": "SLAM / Localization",
            "joins": "3 Silver tables",
            "partition": "clip_id",
            "rows": "3,935 frames",
            "color": "#2980B9",
            "x": 4.95,
        },
        {
            "name": "sensor_fusion_frame",
            "workload": "Multi-Modal Fusion",
            "joins": "5 Silver + 3 aggs",
            "partition": "clip_id",
            "rows": "3,935 frames",
            "color": "#27AE60",
            "x": 9.6,
        },
    ]

    for td in table_data:
        x = td["x"]
        w = 4.1
        # Main card
        rect = mpatches.FancyBboxPatch(
            (x, 0.5), w, 3.8, boxstyle="round,pad=0.15",
            facecolor="white", edgecolor=td["color"], linewidth=2.5
        )
        ax.add_patch(rect)
        # Header
        header = mpatches.FancyBboxPatch(
            (x, 3.5), w, 0.8, boxstyle="round,pad=0.1",
            facecolor=td["color"], edgecolor="none", alpha=0.9
        )
        ax.add_patch(header)
        ax.text(x+w/2, 3.9, td["name"], ha="center", va="center",
                fontsize=11, fontweight="bold", color="white", family="monospace")
        # Content
        lines = [
            f"ML Workload:  {td['workload']}",
            f"Joins eliminated:  {td['joins']}",
            f"Partition key:  {td['partition']}",
            f"Scale:  {td['rows']}",
        ]
        for i, line in enumerate(lines):
            ax.text(x + 0.3, 3.0 - i*0.55, line, fontsize=10, color="#333", va="center")

    ax.text(7.0, 4.65, "Gold Table Designs — Pre-Joined, ML-Ready", ha="center",
            fontsize=14, fontweight="bold", color="#333333")

    fig.savefig(OUT / "gold_tables.png", dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  ✓ {OUT / 'gold_tables.png'}")


# ============================================================================
# Figure 8: Validation Summary
# ============================================================================
def fig8_validation():
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.axis("off")
    fig.patch.set_facecolor("white")

    # Table data
    cols = ["Check Type", "Count", "Status"]
    rows = [
        ["PK Uniqueness", "6", "PASS"],
        ["FK Integrity", "4", "PASS"],
        ["Quaternion Normalization", "2", "PASS"],
        ["Non-negative Timestamps", "4", "PASS"],
        ["Gold Row Consistency", "4", "PASS"],
        ["TOTAL", "20 checks", "ALL PASS"],
    ]

    table = ax.table(cellText=rows, colLabels=cols, loc="center",
                     cellLoc="center", colColours=["#34495E"]*3)
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.0, 1.6)

    # Style header
    for j in range(3):
        table[0, j].set_text_props(color="white", fontweight="bold")
        table[0, j].set_facecolor("#34495E")

    # Style last row (totals)
    for j in range(3):
        table[len(rows), j].set_facecolor("#E8F5E9")
        table[len(rows), j].set_text_props(fontweight="bold")

    # Alternate row colors
    for i in range(1, len(rows)):
        for j in range(3):
            if i < len(rows):
                table[i, j].set_facecolor("#F8F8F8" if i % 2 == 0 else "white")

    ax.set_title("Data Quality Validation Summary", fontsize=13, fontweight="bold", pad=15)

    fig.savefig(OUT / "validation_summary.png", dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  ✓ {OUT / 'validation_summary.png'}")


# ============================================================================
# Main
# ============================================================================
if __name__ == "__main__":
    print("Generating slide deck figures...")
    fig1_architecture()
    fig2_data_model()
    fig3_medallion()
    fig4_workload_benchmark()
    fig5_scalability()
    fig6_supplementary()
    fig7_gold_tables()
    fig8_validation()
    print(f"\nAll figures saved to: {OUT}/")
