#!/usr/bin/env python3
"""storage_sizing.py — size accumulation (축적) and serving (진열) storage separately.

The lakehouse registers raw data in place, so Bronze/Silver/Gold cost no storage of
their own; what the serving tier really holds is the *derived* artifacts a validator
needs — a NuRec twin per Gold scene, augmented variants, rollout outputs. This model
separates the two tiers, sizes each from measured constants, and puts a number on the
store-vs-regenerate question for augmented variants: below a break-even re-curation
interval it is cheaper to keep variants; above it, to regenerate them.

Every constant is either measured in this repo (cited) or an explicit assumption
(flagged). Run it to print the tables and write STORAGE_SIZING.md next to it; use
the CLI to move the assumptions.
"""
from __future__ import annotations

import argparse
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------------- measured constants
MEASURED = {
    # accumulation tier
    "raw_full_sensor_clip_mb": 600,     # camera 235 + lidar 356 + radar 8 + labels 0.4 MB, clip 2daf9698 (NFS, 2026-09-21)
    "raw_on_disk_mean_mb": 409,         # 13.5 TB / 32,986 clips on disk (MEDALLION_PROGRESS.md); most clips lack lidar
    "corpus_clips": 306_152,            # clip_index.parquet
    "on_disk_clips": 32_986,            # MEDALLION_PROGRESS.md
    "gold_clips": 3_176,                # MEDALLION_PROGRESS.md (noisy-OR union, sensor-covered)
    # serving tier
    "nurec_scene_gb_local": 1.60,       # 65 GB / 41 cached 26.04 artifacts (alpasim/repo/data/nre-artifacts)
    "nurec_scene_gb_catalog": 1.79,     # FEASIBILITY.md, 26.04 release average
    "variant_single_cam_window_mb": 8,  # 121-frame (4 s) single-camera Cosmos output; 39 MB per 20 s camera clip x 0.2 (estimate)
    "variant_full_clip_6cam_mb": 235,   # one condition rendered for all 6 cameras, full clip = the camera set size
    "rollout_output_mb": 16,            # 474 MB / 30 scenes, alpasim/runs/vavam-batch2 (videos + metrics)
    # regeneration
    "cosmos_window_gpu_min": 33.6,      # 7 h / 50 windows on 4 x A100-40GB = 8.4 wall-min x 4 GPUs (E-B, git 167a3f4)
    "cosmos_keep_rate": 0.86,           # 43 / 50 passed the hallucination gate (E-B)
    "nurec_scene_gpu_h": None,          # not measured: per-scene optimisation, >24 GB VRAM (FEASIBILITY.md 3c)
    "openloop_s_per_clip": 0.46,        # track-only, 8 workers (BENCHMARKS.md)
    "closedloop_s_per_scene": 33,       # VaVAM, 30 scenes in 15.5 min locally (alpasim/runs/vavam-batch2)
}


def fmt_tb(gb): return f"{gb/1024:.2f} TB" if gb >= 1024 else f"{gb:.0f} GB"


def model(a):
    m = MEASURED
    out = []
    P = out.append

    # ---------------------------------------------------------------- accumulation tier
    P("## Accumulation tier (축적)\n")
    P("Raw logs as recorded. This tier is sized by the fleet, not by curation; the "
      "lakehouse only registers it in place.\n")
    fleet_tb_yr = a.cars * a.hours_per_car_day * 365 * a.clips_per_hour * m["raw_full_sensor_clip_mb"] / 1e6
    P("| quantity | value | basis |\n|---|---|---|")
    P(f"| full-sensor clip | {m['raw_full_sensor_clip_mb']} MB | measured, one clip on NFS |")
    P(f"| on-disk mean clip | {m['raw_on_disk_mean_mb']} MB | 13.5 TB / 32,986 clips |")
    P(f"| NVIDIA corpus, full-sensor | {fmt_tb(m['corpus_clips']*m['raw_full_sensor_clip_mb']/1024)} | 306,152 clips x 600 MB |")
    P(f"| project fleet, raw per year | {fleet_tb_yr:.0f} TB | {a.cars} cars x {a.hours_per_car_day} h/day x {a.clips_per_hour} clips/h x 600 MB (assumption) |")
    P(f"| retained after redundancy cull | {fleet_tb_yr*a.retain:.0f} TB/yr | retain {a.retain:.0%} (the professor's 100-to-10 rule; our on-disk to Gold is {m['gold_clips']/m['on_disk_clips']:.1%}) |")
    P("")

    # ---------------------------------------------------------------- serving tier
    P("## Serving tier (진열)\n")
    P("Derived artifacts per Gold clip, for a Gold tier of N clips. Bronze/Silver/Gold views "
      "themselves are metadata only (register-in-place).\n")
    P("| Gold clips N | twin (NuRec) | + variants stored, v cond x 6 cam | + rollout outputs, p policies | total (store) | total (regenerate) |\n|---|---|---|---|---|---|")
    for N in a.gold_sizes:
        twin = N * m["nurec_scene_gb_catalog"]
        var = N * a.variants * m["variant_full_clip_6cam_mb"] / 1024
        roll = N * a.policies * (1 + a.variants) * m["rollout_output_mb"] / 1024
        P(f"| {N:,} | {fmt_tb(twin)} | {fmt_tb(var)} | {fmt_tb(roll)} | {fmt_tb(twin+var+roll)} | {fmt_tb(twin+roll)} |")
    P("")
    P(f"Assumptions: v = {a.variants} augmentation conditions per Gold clip, p = {a.policies} policies "
      f"evaluated per re-curation, twin = {m['nurec_scene_gb_catalog']} GB/scene (catalog mean; local mean "
      f"{m['nurec_scene_gb_local']} GB), variant = {m['variant_full_clip_6cam_mb']} MB per condition for all six "
      f"cameras over the whole clip (the camera set size; the E-B batch rendered 4 s single-camera windows of "
      f"about {m['variant_single_cam_window_mb']} MB).\n")

    # ---------------------------------------------------------------- store vs regenerate
    P("## Store or regenerate the variants?\n")
    gpu_h_per_clip = m["cosmos_window_gpu_min"] / 60 * (20 / 4) * 6 / m["cosmos_keep_rate"]   # full clip, 6 cams, gate loss
    P(f"Regenerating one condition for one Gold clip (20 s, 6 cameras) costs about "
      f"**{gpu_h_per_clip:.1f} A100-GPU-hours** (E-B: {m['cosmos_window_gpu_min']} GPU-min per 4 s single-camera "
      f"window, x5 duration x6 cameras, / {m['cosmos_keep_rate']:.0%} gate keep-rate). Storing it costs "
      f"{m['variant_full_clip_6cam_mb']} MB.\n")
    store_usd_yr = m["variant_full_clip_6cam_mb"] / 1024 / 1024 * a.tb_month_usd * 12
    regen_usd = gpu_h_per_clip * a.gpu_hour_usd
    breakeven_yr = store_usd_yr / regen_usd if regen_usd else float("inf")
    P("| | per clip-condition | basis |\n|---|---|---|")
    P(f"| store, per year | ${store_usd_yr:.4f} | {m['variant_full_clip_6cam_mb']} MB x ${a.tb_month_usd}/TB-month (assumption) |")
    P(f"| regenerate, once | ${regen_usd:.2f} | {gpu_h_per_clip:.1f} GPU-h x ${a.gpu_hour_usd}/GPU-h (assumption) |")
    P(f"| break-even storage horizon | {1/breakeven_yr:.0f} years | storing beats regenerating unless a variant is kept that long unused |")
    P("")
    P(f"At these prices a stored variant pays for its regeneration after {1/breakeven_yr:.0f} years, so "
      f"**store every variant that was rendered**; the tension the professor describes is not about the "
      f"variants that exist but about the ones that do not: the space of harder situations (a pedestrian "
      f"stepping out, a different weather) is open-ended, so it cannot be pre-rendered, and what must be sized "
      f"is the GPU budget per re-curation, not the disk.\n")
    P("| re-curation interval | new Gold fraction per cycle (turnover) | GPU-h per cycle for v conditions, N Gold | GPU-h per year |\n|---|---|---|---|")
    for months in a.recuration_months:
        for turnover in (0.1, 0.3):
            for N in (a.gold_sizes[0], a.gold_sizes[-1]):
                per_cycle = N * turnover * a.variants * gpu_h_per_clip
                P(f"| {months} mo | {turnover:.0%} | N={N:,}: {per_cycle:,.0f} | {per_cycle*12/months:,.0f} |")
    P("")
    P("Reading: with Gold shifting every 6 months and 30% of it new each time (his 6-month drift), "
      f"a {a.gold_sizes[-1]:,}-clip Gold with {a.variants} conditions needs roughly "
      f"{a.gold_sizes[-1]*0.3*a.variants*gpu_h_per_clip*2:,.0f} A100-GPU-hours a year of Cosmos-Transfer1 "
      f"generation, which is the number to negotiate for, against a serving disk of "
      f"{fmt_tb(a.gold_sizes[-1]*(m['nurec_scene_gb_catalog'] + a.variants*m['variant_full_clip_6cam_mb']/1024))}.\n")

    # ---------------------------------------------------------------- twin reconstruction
    P("## The twin itself\n")
    P(f"NuRec reconstruction per scene is not measured here (needs >24 GB VRAM; FEASIBILITY.md 3c). Its storage is "
      f"known: {m['nurec_scene_gb_catalog']} GB/scene, so a full-Gold twin of {m['gold_clips']:,} scenes is "
      f"{fmt_tb(m['gold_clips']*m['nurec_scene_gb_catalog'])} — {m['gold_clips']*m['nurec_scene_gb_catalog']/(m['gold_clips']*m['raw_full_sensor_clip_mb']/1024):.1f}x "
      f"the raw media of the same clips. The twin, not the variants, is what dominates serving storage, and it is "
      f"also what re-curation churns: every clip that enters Gold needs a reconstruction, every clip that leaves "
      f"holds {m['nurec_scene_gb_catalog']} GB until evicted. Measuring one reconstruction on an L40S is the "
      f"missing constant.\n")

    # ---------------------------------------------------------------- validation cost
    P("## Validation cost per re-curation\n")
    P("| step | per clip | N = 3,176 Gold, one policy | basis |\n|---|---|---|---|")
    P(f"| open-loop screen | {m['openloop_s_per_clip']} s | {m['gold_clips']*m['openloop_s_per_clip']/3600:.1f} h | BENCHMARKS.md, 8 workers |")
    P(f"| closed-loop rollout, small policy | {m['closedloop_s_per_scene']} s | {m['gold_clips']*m['closedloop_s_per_scene']/3600:.1f} h | vavam-batch2 locally |")
    P(f"| closed-loop at a {a.budget:.0%} skip budget | — | {m['gold_clips']*a.budget*m['closedloop_s_per_scene']/3600:.1f} h | evaluation/skip.py |")
    P("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cars", type=int, default=21, help="project fleet size (assumption)")
    ap.add_argument("--hours-per-car-day", type=float, default=8)
    ap.add_argument("--clips-per-hour", type=float, default=180, help="20 s clips per recording hour")
    ap.add_argument("--retain", type=float, default=0.10, help="fraction kept after redundancy cull")
    ap.add_argument("--gold-sizes", type=lambda s: [int(x) for x in s.split(",")], default=[500, 1000, 3176, 10000])
    ap.add_argument("--variants", type=int, default=3, help="augmentation conditions per Gold clip (night, rain, fog)")
    ap.add_argument("--policies", type=int, default=3)
    ap.add_argument("--recuration-months", type=lambda s: [int(x) for x in s.split(",")], default=[6, 12])
    ap.add_argument("--tb-month-usd", type=float, default=20.0, help="storage price assumption")
    ap.add_argument("--gpu-hour-usd", type=float, default=2.0, help="A100 price assumption")
    ap.add_argument("--budget", type=float, default=0.5, help="skip-policy rollout budget")
    ap.add_argument("--out", default=os.path.join(HERE, "STORAGE_SIZING.md"))
    a = ap.parse_args()

    body = model(a)
    head = ("# Storage sizing — accumulation vs serving (2026-09-21)\n\n"
            "Generated by `storage_sizing.py`; rerun with different assumptions rather than editing.\n\n")
    open(a.out, "w").write(head + body)
    print(body)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
