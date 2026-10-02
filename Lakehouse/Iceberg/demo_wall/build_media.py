#!/usr/bin/env python3
"""build_media.py — build the wall's media library from the proving-ground outputs.

Everything the wall shows beyond the baked numbers in js/data.js comes from here,
read from the runs already on this server. Outputs go to demo_wall/assets/media/
(gitignored, regenerable) plus one generated script, assets/media/media.js, that sets
window.WALL_MEDIA. A <script> tag loads it, so the same build works served over
HTTP and from file:// (portable copy).

  twins/<short>.mp4    real camera | NuRec twin render | twin depth, front-wide camera,
                       the twin's validation frames (evaluation/nurec/out/*/val)
  pairs/<short>.mp4    VaVAM closed-loop in AlpaSim: our twin | NVIDIA's NuRec scene,
                       cut at each side's scored end (alpasim/runs/<short>_*_vavam)
  cosmos/<id>.mp4      recorded window | Cosmos-Transfer variant, only the variants
                       the hallucination gate kept (cosmos_augmentation/gate_report.json)

and annotates the real-clip library (assets/clips/manifest.json, from
extract_assets.py) with each clip's Gold difficulty from user_data/wall_scores.parquet.

Data exporters that need other environments run first (see README):
  export_scores.py  (inside spark-iceberg)  -> user_data/wall_scores.{parquet,json}
  export_triage.py  (evaluation/.skip_venv) -> user_data/wall_triage.json

Run from Lakehouse/Iceberg with the wall venv:
  demo_wall/.venv/bin/python demo_wall/build_media.py            # incremental
  demo_wall/.venv/bin/python demo_wall/build_media.py --force    # re-encode all
"""
from __future__ import annotations

import argparse
import bisect
import glob
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent            # demo_wall/
ROOT = HERE.parent                                # Lakehouse/Iceberg
EVAL = ROOT / "evaluation"
NUREC_OUT = EVAL / "nurec" / "out"
RUNS = EVAL / "alpasim" / "runs"
OUT = HERE / "assets" / "media"
CLIPS_MANIFEST = HERE / "assets" / "clips" / "manifest.json"
USER_DATA = ROOT / "user_data"
NFS = ROOT / "netai-e2e" / "nvidia-physicalai-av-subset"
VARIANTS_DEFAULT = Path.home() / "jeykang" / "pdsw26-artifact-data" / "variants"

# The first twin (clip ac73935a) predates twin_pipeline.sh: its own directory and run names.
SPECIAL_TWINS = {
    "ac73935a": {"val": "ac73935a_a10_prod_v3", "ours": "v3_ours_map_vavam_rec",
                 "nvidia": "v3_nvidia_vavam_rec", "ours_cv": "v3_ours_map", "nvidia_cv": "v3_nvidia"},
}

# AlpaSim rollout video layout (900x1000): front camera below, BEV map top-left.
CAM_CROP = "crop=840:430:30:560"                  # below the "Command:" label
MAP_CROP = "crop=472:472:63:31"
ROLLOUT_FPS = 2.0                                 # AlpaSim writes 2 frames per sim-second
SEASONS = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
           6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}


def log(*a):
    print("[media]", *a, flush=True)


def ffmpeg_bin() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        exe = shutil.which("ffmpeg")
        if not exe:
            sys.exit("no ffmpeg: pip install imageio-ffmpeg (see requirements.txt)")
        return exe


FFMPEG = None


def run_ffmpeg(args: list[str], out: Path):
    """Encode to a temp file and rename, so a half-written video is never served."""
    tmp = out.with_suffix(".tmp.mp4")
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args,
           "-c:v", "libx264", "-preset", "slow", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", str(tmp)]
    subprocess.run(cmd, check=True)
    tmp.replace(out)


def fresh(out: Path, inputs: list[Path], force: bool) -> bool:
    if force or not out.exists():
        return False
    t = out.stat().st_mtime
    return all(p.stat().st_mtime <= t for p in inputs if p.exists())


# ----------------------------------------------------------------------------- metadata
def load_collection() -> dict:
    """clip_id -> {country, hour, month} from the dataset's data_collection.parquet."""
    path = NFS / "metadata" / "data_collection.parquet"
    if not path.exists():
        log("no data_collection.parquet (NFS not mounted?) — twin metadata will be sparse")
        return {}
    import pyarrow.parquet as pq
    t = pq.read_table(path, columns=["clip_id", "country", "hour_of_day", "month"]).to_pydict()
    return {c: {"country": co, "hour": h, "month": m}
            for c, co, h, m in zip(t["clip_id"], t["country"], t["hour_of_day"], t["month"])}


def where_of(meta: dict | None) -> dict:
    if not meta:
        return {}
    # no day/night label: hour_of_day disagrees with the frames for some clips (ba91fe2c
    # is tagged 02:00 and filmed in daylight)
    h, m = meta.get("hour"), meta.get("month")
    out = {"country": meta.get("country")}
    if h is not None:
        out["hour"] = int(h)
    if m is not None:
        out["season"] = SEASONS.get(int(m))
    return out


def per_clip(run: str) -> dict | None:
    """First row of an AlpaSim run's per_clip.parquet, as an outcome record."""
    p = RUNS / run / "per_clip.parquet"
    if not p.exists():
        return None
    import pyarrow.parquet as pq
    r = {k: v[0] for k, v in pq.read_table(p).to_pydict().items()}
    outcome = ("collision" if r["collision_any"] > 0 else "offroad" if r["offroad"] > 0 else "clean")
    return {"outcome": outcome, "at_fault": bool(r["offroad_or_collision_at_fault"] > 0),
            "dist_m": round(float(r["dist_traveled_m"]), 1),
            "t_end_s": round(float(r["duration_frac_20s"]) * 20.0, 2)}


def rollout_mp4(run: str) -> Path | None:
    fs = sorted(glob.glob(str(RUNS / run / "rollouts" / "*" / "*" / "*camera_front_wide_120fov*.mp4")))
    return Path(fs[0]) if fs else None


def psnr_of(val: Path) -> float | None:
    p = val / "metrics.yaml"
    if not p.exists():
        return None
    m = re.search(r"test/psnr:\s*\n\s*aggregation_method:\s*mean\s*\n\s*value:\s*([0-9.]+)", p.read_text())
    return round(float(m.group(1)), 2) if m else None


def timings_of(short: str) -> dict | None:
    """Per-step minutes from twin_pipeline.sh's <short>.twin.json (cumulative t_s)."""
    p = NUREC_OUT / f"{short}.twin.json"
    if not p.exists():
        return None
    steps = json.loads(p.read_text()).get("steps", {})
    t = {k: v.get("t_s") for k, v in steps.items() if isinstance(v, dict)}
    order = [t.get(k) for k in ("convert", "instant", "aux", "train", "ground", "bundle")]
    if any(v is None for v in order) or any(b < a for a, b in zip(order, order[1:])):
        # a resumed run restarts the clock (e.g. ba91fe2c: aux on 09-21, training on 09-23),
        # so step lengths cannot be read off the cumulative times
        return {"resumed": True}
    try:
        return {
            "convert_min": round(t["convert"] / 60, 1),                  # PAI clip -> NCore v4
            "aux_min": round((t["aux"] - t["instant"]) / 60, 1),          # road / semantic labels
            "train_min": round((t["train"] - t["aux"]) / 60, 1),          # NuRec reconstruction
            "ground_min": round((t["ground"] - t["train"]) / 60, 1),      # ground mesh
            "bundle_min": round((t["bundle"] - t["ground"]) / 60, 1),     # AlpaSim bundle
            "total_min": round(t["bundle"] / 60, 1),
        }
    except (KeyError, TypeError):
        return None


# ----------------------------------------------------------------------------- twins + pairs
def twin_specs() -> list[dict]:
    specs = []
    for j in sorted(NUREC_OUT.glob("*.twin.json")):
        short = j.name.split(".")[0]
        specs.append({"short": short, "clip_id": json.loads(j.read_text()).get("clip"),
                      "val": f"{short}_a10_prod", "ours": f"{short}_ours_map_vavam",
                      "nvidia": f"{short}_nvidia_vavam", "ours_cv": f"{short}_ours_map_cv",
                      "nvidia_cv": f"{short}_nvidia_cv"})
    for short, s in SPECIAL_TWINS.items():
        cid = next((Path(p).name.split("_", 1)[1] for p in glob.glob(str(NUREC_OUT / f"instant_{short}*"))), None)
        specs.append({"short": short, "clip_id": cid, **s})
    return specs


def build_twin(spec: dict, force: bool) -> dict | None:
    val = NUREC_OUT / spec["val"] / "val"
    kinds = ["input_rgb", "pred_rgb", "pred_distance"]
    dirs = [val / k / "cam_00" for k in kinds]          # cam_00 = camera_front_wide_120fov
    if not all(d.is_dir() for d in dirs):
        log(f"  twin {spec['short']}: no validation frames, skipped")
        return None
    frames = sorted(p.name for p in dirs[0].glob("*.png"))
    if not frames:
        return None
    start = int(frames[0].split(".")[0])
    out = OUT / "twins" / f"{spec['short']}.mp4"
    if not fresh(out, [dirs[0] / frames[-1]], force):
        args = []
        for d in dirs:     # 10 fps validation frames played at 20 fps: 2x speed
            args += ["-framerate", "20", "-start_number", str(start), "-i", str(d / "%06d.png")]
        run_ffmpeg(args + ["-filter_complex", "[0:v][1:v][2:v]hstack=inputs=3[v]", "-map", "[v]",
                           "-frames:v", str(len(frames)), "-crf", "20"], out)
        log(f"  twin {spec['short']}: {len(frames)} frames -> {out.name}")
    return {"short": spec["short"], "video": f"assets/media/twins/{out.name}",
            "frames": len(frames), "fps": 20, "psnr": psnr_of(val), "build": timings_of(spec["short"])}


def build_pair(spec: dict, force: bool) -> dict | None:
    ours, nvidia = per_clip(spec["ours"]), per_clip(spec["nvidia"])
    a, b = rollout_mp4(spec["ours"]), rollout_mp4(spec["nvidia"])
    if not (ours and nvidia and a and b):
        log(f"  pair {spec['short']}: missing run(s), skipped")
        return None
    hold = 0.5     # seconds of sim time shown past the scored end
    ends = [min(20.0, r["t_end_s"] + hold) for r in (ours, nvidia)]
    span = max(ends)
    out = OUT / "pairs" / f"{spec['short']}.mp4"
    if not fresh(out, [a, b], force):
        chains = []
        for i, end in enumerate(ends):
            # each side stops at its own scored end and holds its last frame; the
            # renders past a failure leave the recorded path and are not scored
            chains.append(
                f"[{i}:v]split[c{i}][m{i}];"
                f"[c{i}]{CAM_CROP},scale=800:410[cam{i}];"
                f"[m{i}]{MAP_CROP},negate,hue=h=180,scale=180:180[map{i}];"
                f"[cam{i}][map{i}]overlay=W-w-12:12,trim=end={end},setpts=PTS-STARTPTS,"
                f"tpad=stop_mode=clone:stop_duration={span - end + 0.01}[s{i}]")
        graph = ";".join(chains) + ";[s0][s1]hstack=inputs=2,framerate=fps=20[v]"
        run_ffmpeg(["-r", str(ROLLOUT_FPS), "-i", str(a), "-r", str(ROLLOUT_FPS), "-i", str(b),
                    "-filter_complex", graph, "-map", "[v]", "-t", str(span), "-crf", "24"], out)
        log(f"  pair {spec['short']}: {span:.1f} s -> {out.name}")
    cv_o, cv_n = per_clip(spec["ours_cv"]), per_clip(spec["nvidia_cv"])
    return {"short": spec["short"], "video": f"assets/media/pairs/{out.name}", "span_s": span,
            "ours": ours, "nvidia": nvidia,
            "cv_agree": (cv_o["outcome"] == cv_n["outcome"]) if (cv_o and cv_n) else None,
            "vavam_agree": ours["outcome"] == nvidia["outcome"]}


# ----------------------------------------------------------------------------- cosmos
def build_cosmos(variants: Path, force: bool) -> list[dict]:
    gate = json.loads((ROOT / "cosmos_augmentation" / "gate_report.json").read_text())
    manifest = {m["short"]: m for m in json.loads((ROOT / "cosmos_augmentation" / "batch_manifest.json").read_text())}
    items = []
    for g in gate:
        if not g.get("kept"):
            continue
        short, cond = g["clip"], g["cond"]
        src, aug = variants / f"{short}_day.mp4", variants / f"{short}_{cond}_aug.mp4"
        if not (src.exists() and aug.exists()):
            continue
        out = OUT / "cosmos" / f"{short}_{cond}.mp4"
        if not fresh(out, [src, aug], force):
            # both are the same 121-frame window (source 30 fps, generated 24 fps):
            # re-time both to 24 fps so frame n lines up with frame n
            graph = ("[0:v]setpts=N/24/TB,scale=800:450:flags=lanczos,setsar=1[a];"
                     "[1:v]setpts=N/24/TB,scale=800:450:flags=lanczos,setsar=1[b];"
                     "[a][b]hstack=inputs=2[v]")
            run_ffmpeg(["-i", str(src), "-i", str(aug), "-filter_complex", graph, "-map", "[v]",
                        "-r", "24", "-frames:v", "121", "-crf", "23"], out)
            log(f"  cosmos {short} {cond} -> {out.name}")
        m = manifest.get(short, {})
        items.append({"short": short, "cond": cond, "video": f"assets/media/cosmos/{out.name}",
                      "actors": m.get("window_agents"),
                      "det": [g.get("day_ndet"), g.get("aug_ndet")],
                      "conf": [g.get("day_conf"), g.get("aug_conf")]})
    return items


# ----------------------------------------------------------------------------- clip library
def annotate_clips() -> None:
    """Write each library clip's Gold difficulty into assets/clips/manifest.json."""
    scores_p = USER_DATA / "wall_scores.parquet"
    if not (scores_p.exists() and CLIPS_MANIFEST.exists()):
        log("clip library or user_data/wall_scores.parquet missing — clips not annotated")
        return
    import pyarrow.parquet as pq
    t = pq.read_table(scores_p).to_pydict()
    covered = sorted(d for d, c in zip(t["difficulty_camera"], t["sensor_covered"]) if c and d is not None and d >= 0)
    by_id = {cid: (d, c, cf, cm, g) for cid, d, c, cf, cm, g in
             zip(t["clip_id"], t["difficulty_camera"], t["sensor_covered"], t["conflict"], t["camera"], t["gold"])}
    m = json.loads(CLIPS_MANIFEST.read_text())
    n_scored = 0
    for clip in m.get("clips", []):
        clip.pop("score", None)          # June composite, refuted (OOD AUC 0.450)
        clip.pop("factor", None)
        rec = by_id.get(clip["id"])
        if not rec or not rec[1] or rec[0] is None:
            clip["difficulty"] = None
            continue
        d, _, conflict, camera, gold = rec
        clip["difficulty"] = round(d, 4)
        clip["conflict"] = round(conflict, 4) if conflict is not None else None
        clip["camera"] = round(camera, 4) if camera is not None else None
        clip["pct"] = round(100.0 * bisect.bisect_left(covered, d) / len(covered), 1)
        clip["gold"] = bool(gold)
        n_scored += 1
    m.pop("total_clips", None)           # stale June constants; js/data.js holds the totals
    m.pop("total_scored", None)
    m["annotated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = CLIPS_MANIFEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(m))
    tmp.replace(CLIPS_MANIFEST)
    log(f"clip library: {n_scored:,} of {len(m.get('clips', [])):,} clips annotated with Gold difficulty")


def previous_media() -> dict:
    """The current media.js, so a --skip'd section keeps what it had."""
    p = OUT / "media.js"
    try:
        s = p.read_text()
        return json.loads(s[s.index("=") + 1:].strip().rstrip(";"))
    except Exception:
        return {}


# ----------------------------------------------------------------------------- main
def main():
    global FFMPEG
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="re-encode videos that already exist")
    ap.add_argument("--variants", type=Path, default=VARIANTS_DEFAULT,
                    help="Cosmos batch videos (<clip>_day.mp4 + <clip>_<cond>_aug.mp4)")
    ap.add_argument("--skip", nargs="*", default=[], choices=["twins", "pairs", "cosmos", "clips"])
    a = ap.parse_args()
    FFMPEG = ffmpeg_bin()
    for sub in ("twins", "pairs", "cosmos"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)

    prev = previous_media()
    meta = load_collection()
    twins, pairs = [], []
    for spec in twin_specs():
        info = {"short": spec["short"], "clip_id": spec["clip_id"], **where_of(meta.get(spec["clip_id"]))}
        if "twins" not in a.skip and (t := build_twin(spec, a.force)):
            twins.append({**info, **t})
        if "pairs" not in a.skip and (p := build_pair(spec, a.force)):
            pairs.append({**info, **p})
    if "twins" in a.skip:
        twins = prev.get("twins", [])
    if "pairs" in a.skip:
        pairs = prev.get("pairs", [])
    log(f"twins: {len(twins)}  pairs: {len(pairs)}")

    cosmos = prev.get("cosmos", []) if "cosmos" in a.skip else []
    if "cosmos" not in a.skip:
        if a.variants.is_dir():
            cosmos = build_cosmos(a.variants, a.force)
        else:
            log(f"no Cosmos variants at {a.variants} — chapter falls back to text")
    log(f"cosmos pairs: {len(cosmos)}")

    if "clips" not in a.skip:
        annotate_clips()
    summary_p = USER_DATA / "wall_scores.json"
    scores = json.loads(summary_p.read_text()) if summary_p.exists() else prev.get("scores")
    triage_p = USER_DATA / "wall_triage.json"
    triage = json.loads(triage_p.read_text()) if triage_p.exists() else prev.get("triage")
    if triage is None:
        log("no user_data/wall_triage.json — run export_triage.py; Triage chapter shows the curve only")

    media = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "twins": twins, "pairs": pairs,
             "cosmos": cosmos, "scores": scores, "triage": triage}
    (OUT / "media.js").write_text("window.WALL_MEDIA = " + json.dumps(media, separators=(",", ":")) + ";\n")
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    log(f"wrote {OUT / 'media.js'} ({size:.0f} MB of media)")


if __name__ == "__main__":
    main()
