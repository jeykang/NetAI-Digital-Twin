#!/usr/bin/env python3
"""rollouts.py — every closed-loop rollout on disk, keyed by its episode: the input of eval.rollout.

    .skip_venv/bin/python rollouts.py                    # -> ../user_data/rollouts.parquet
    docker exec -w /opt/spark spark-iceberg /opt/spark/bin/spark-submit nvidia_ingestion/build_rollout_table.py

One row per rollout: AlpaSim, per clip and rollout_id of every run under alpasim/runs/ that has a
per_clip.parquet (alpasim/per_clip.py, AlpaSim's own aggregation); HUGSIM, per episode directory
under hugsim/runs/pai*_ltf/ (one seed each). Each row carries the episode it ran, the same
episode_id as nvidia_gold.episode (episodes.py), so closed-loop outcomes join to the scenario x
episode space and to the curation scores:

  AlpaSim over NVIDIA's NuRec scene (catalog or a local copy)  <clip>:nurec:<uuid>                       closedloop-nurec
  AlpaSim over our NuRec twin                                   <clip>:twin:closedloop-nurec-ours:<run>  closedloop-nurec-ours
  HUGSIM over our HUGS twin                                     <clip>:twin:closedloop-hugsim:<scene>    closedloop-hugsim

Each simulator keeps its own metrics; `outcome` and `failed` are the one place they meet, and
they are not interchangeable (HUGSIM.md caveats: a roadside barrier is off-road in AlpaSim, where
scenery has no collision geometry, and a background collision in HUGSIM):
  AlpaSim  outcome = collision (collision_any) | off-road (offroad) | clean, within the span
           AlpaSim scores; failed = offroad_or_collision
  HUGSIM   outcome = how the episode ended: collision | off-route (> 10 m from the recorded path)
           | complete | step-cap; failed = collision
How each run was configured (policy, route generator, image format, camera, map layers: NVIDIA's,
borrowed by our twin, or none) is read from the run's own files, not from its name.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import subprocess
import time

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ALPA = os.path.join(HERE, "alpasim")
HUG = os.path.join(HERE, "hugsim")
SIM_SCENES = os.path.join(ALPA, "repo", "data", "scenes", "sim_scenes.csv")
STAGED = os.path.join(HERE, "ncore", "staged")
NUREC_OUT = os.path.join(HERE, "nurec", "out")
ALPASIM_METRICS = ["progress_rel", "dist_traveled_m", "dist_to_gt_trajectory", "collision_any",
                   "collision_at_fault", "collision_rear", "offroad", "offroad_or_collision",
                   "offroad_or_collision_at_fault", "duration_frac_20s", "min_distance_to_obstacle_m"]


def twin_episode_id(clip: str, mode: str, name: str) -> str:   # same as episodes.twin_episode_id
    return f"{clip}:twin:{mode}:{name}"


def _grep(path: str, key: str):
    if not os.path.exists(path):
        return None
    m = re.search(rf"^\s*{key}:\s*(\S+)", open(path).read(), re.M)
    return None if m is None or m.group(1) == "null" else m.group(1).strip("'\"")


def _nurec_uuid() -> dict:
    """clip -> uuid of its NuRec scene: the newest catalog row, as episodes.nurec_scenes() picks it."""
    newest = {}
    for r in csv.DictReader(open(SIM_SCENES)):
        if r["scene_id"] not in newest or r["last_modified"] > newest[r["scene_id"]]["last_modified"]:
            newest[r["scene_id"]] = r
    return {sid.replace("clipgt-", ""): r["uuid"] for sid, r in newest.items()}


def _full_ids() -> dict:
    out = {c[:8]: c for c in os.listdir(STAGED)} if os.path.isdir(STAGED) else {}
    for f in glob.glob(os.path.join(NUREC_OUT, "*.twin.json")):
        c = json.load(open(f)).get("clip")
        if c:
            out.setdefault(c[:8], c)
    return out


def _alpasim_twin(local_dir: str | None):
    """(serving_mode, twin name or None) from the run's local USDZ directory."""
    if not local_dir:
        return "closedloop-nurec", None                        # catalog scenes
    b = os.path.basename(local_dir.rstrip("/"))
    if "_ours" not in b:
        return "closedloop-nurec", None                        # a local copy of NVIDIA's scene
    if b.startswith("local_scenes_v3_"):
        return "closedloop-nurec-ours", "ac73935a_a10_prod_v3"
    if b.startswith("local_scenes_v2b_"):
        return "closedloop-nurec-ours", "ac73935a_a10_noaux_v2b"
    m = re.match(r"local_scenes_([0-9a-f]{8})_ours", b)
    return "closedloop-nurec-ours", (f"{m.group(1)}_a10_prod" if m else b)


def alpasim_rows(uuid_of: dict) -> list[dict]:
    rows = []
    for pc in sorted(glob.glob(os.path.join(ALPA, "runs", "*", "per_clip.parquet"))):
        rd = os.path.dirname(pc); run = os.path.basename(rd)
        mt = _grep(os.path.join(rd, "driver-config.yaml"), "model_type")
        ck = _grep(os.path.join(rd, "driver-config.yaml"), "checkpoint_path")
        policy = "vavam" if mt == "vam" else (ck if mt == "harness" else mt)
        local = _grep(os.path.join(rd, "wizard-config.yaml"), "local_usdz_dir")
        uc = os.path.join(rd, "generated-user-config-0.yaml")
        route, imgfmt = _grep(uc, "route_generator_type"), _grep(uc, "image_format") or "jpeg"
        mode, twin = _alpasim_twin(local)
        lb = os.path.basename((local or "").rstrip("/"))
        map_layers = "nvidia" if mode == "closedloop-nurec" else ("borrowed" if "_ours_map" in lb else "none")
        df = pd.read_parquet(pc)
        for r in df.to_dict("records"):
            clip = r["clip_id"]
            ep = (f"{clip}:nurec:{uuid_of[clip]}" if mode == "closedloop-nurec" and clip in uuid_of
                  else twin_episode_id(clip, mode, twin) if twin else None)
            oc = "collision" if r.get("collision_any") else "off-road" if r.get("offroad") else "clean"
            rows.append({"rollout_key": f"alpasim:{run}:{clip}:{r['rollout_id']}", "simulator": "alpasim",
                         "run": run, "clip_id": clip, "episode_id": ep, "serving_mode": mode, "twin": twin,
                         "policy": policy, "rollout": str(r["rollout_id"]), "seed": None,
                         "route_generator": route, "image_format": imgfmt, "camera": "front-wide-120-ftheta",
                         "map_layers": map_layers,
                         "scenario_variant": None, "outcome": oc, "failed": bool(r.get("offroad_or_collision")),
                         "dist_m": r.get("dist_traveled_m"),
                         **{k: (None if pd.isna(r.get(k)) else float(r[k])) for k in ALPASIM_METRICS if k in r}})
    return rows


def hugsim_rows(full: dict) -> list[dict]:
    out = os.path.join(HUG, "runs", ".rollouts_summary.json")
    subprocess.run(["docker", "run", "--rm", "-v", f"{HUG}:{HUG}", "-w", f"{HUG}/repo", "hugsim-dev:cu118",
                    "pixi", "run", "python", f"{HUG}/summarize_runs.py", "--json", out, "runs/pai*_ltf/*"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rows = []
    for r in json.load(open(out)):
        prefix, epname = r["episode_dir"].split("/")[1].removesuffix("_ltf"), r["episode_dir"].split("/")[2]
        parts = epname.rsplit("_", 2)
        scene, variant = parts[0], "_".join(parts[1:])
        clip = full.get(scene[:8])
        policy = "vavam" if "vavam" in prefix else "constant_velocity" if prefix.endswith("_cv") else "ltf"
        m = re.search(r"_s(\d+)$", prefix)
        oc = {"collision": "collision", "off path": "off-route", "complete": "complete"}.get(r["end"], "step-cap")
        rows.append({"rollout_key": f"hugsim:{prefix}:{epname}", "simulator": "hugsim", "run": prefix,
                     "clip_id": clip, "episode_id": twin_episode_id(clip, "closedloop-hugsim", scene) if clip else None,
                     "serving_mode": "closedloop-hugsim", "twin": scene, "policy": policy,
                     "rollout": m.group(1) if m else "0", "seed": int(m.group(1)) if m else None,
                     "route_generator": "recorded-path", "image_format": "render", "map_layers": "none",
                     "camera": "front-100-pinhole" if "front100" in prefix else "nuscenes-front-65-pinhole",
                     "scenario_variant": variant, "outcome": oc, "failed": oc == "collision",
                     "dist_m": r["dist_m"], "sim_s": r["sim_s"], "max_gap_m": r["max_gap_m"],
                     "nc": r.get("nc"), "dac": r.get("dac"), "ttc": r.get("ttc"), "comfort": r.get("c"),
                     "rc": r.get("rc"), "hdscore": r.get("hdscore")})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(HERE, "..", "user_data", "rollouts.parquet"))
    ap.add_argument("--no-hugsim", action="store_true")
    a = ap.parse_args()
    rows = alpasim_rows(_nurec_uuid())
    if not a.no_hugsim:
        rows += hugsim_rows(_full_ids())
    df = pd.DataFrame(rows)
    df["collected_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    for c in ("seed",):
        df[c] = df[c].astype("Int64")
    df.to_parquet(a.out, index=False)
    print(f"wrote {a.out}: {len(df)} rollouts, {df['episode_id'].isna().sum()} without an episode id")
    print(df.groupby(["simulator", "serving_mode", "policy"]).agg(
        rollouts=("rollout_key", "size"), clips=("clip_id", "nunique"), failed=("failed", "mean")).round(3).to_string())


if __name__ == "__main__":
    main()
