#!/usr/bin/env python3
"""extract_assets.py — build the real-clip library for the wall's Collect and Curate chapters.

Samples N random clips from the NFS Nvidia PhysicalAI subset that have BOTH a
front-wide camera mp4 and a LiDAR parquet, then for each clip:
  - extracts one representative camera frame  -> assets/clips/<id>.jpg
  - decodes one representative LiDAR spin     -> assets/clips/<id>.bin (Float32 xyz)
  - pulls real metadata (country / hour / month / season)
  - (optional) runs YOLOv8n for real 2D detections        [--yolo]
and writes assets/clips/manifest.json (this run's clips only). If
user_data/wall_scores.parquet exists (export_scores.py), candidates are limited to
clips with a Gold difficulty and the manifest is annotated with it afterwards
(build_media.annotate_clips). The wall cycles through the library, one clip per loop.

Core deps : opencv-python-headless  DracoPy  pyarrow  numpy
Optional  : ultralytics (--yolo)

Run inside a venv (see README). Example:
  python demo_wall/extract_assets.py --n 40 --yolo
"""
from __future__ import annotations
import argparse
import json
import os
import random
import struct
import sys
import time
from glob import glob
from pathlib import Path

import numpy as np

NFS_DEFAULT = "./netai-e2e/nvidia-physicalai-av-subset"
FRONT_CAM = "camera_front_wide_120fov"
SEASONS_N = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring",
             5: "spring", 6: "summer", 7: "summer", 8: "summer", 9: "autumn",
             10: "autumn", 11: "autumn"}


def log(*a):
    print("[extract]", *a, flush=True)


def find_candidates(nfs: str):
    cam_glob = f"{nfs}/camera/{FRONT_CAM}/*/*.{FRONT_CAM}.mp4"
    cams = {}
    for p in glob(cam_glob):
        cid = os.path.basename(p).split(".")[0]
        cams[cid] = p
    lidar_glob = f"{nfs}/lidar/lidar_top_360fov/*/*.lidar_top_360fov.parquet"
    lids = {}
    for p in glob(lidar_glob):
        cid = os.path.basename(p).split(".")[0]
        lids[cid] = p
    both = [(cid, cams[cid], lids[cid]) for cid in cams if cid in lids]
    return both


def load_metadata(nfs: str):
    """Best-effort per-clip metadata from data_collection.parquet."""
    meta = {}
    candidates = [
        f"{nfs}/metadata/data_collection.parquet",
        f"{nfs}/data_collection.parquet",
    ]
    path = next((c for c in candidates if os.path.exists(c)), None)
    if not path:
        log("no data_collection.parquet found — metadata will be sparse")
        return meta
    try:
        import pyarrow.parquet as pq
        t = pq.read_table(path)
        cols = {c.lower(): c for c in t.column_names}
        log("data_collection columns:", list(cols.keys())[:20])

        def col(*names):
            for n in names:
                if n in cols:
                    return t.column(cols[n]).to_pylist()
            return None

        ids = col("clip_id", "clip_uuid", "id")
        if ids is None:
            log("no clip_id column in data_collection")
            return meta
        country = col("country", "country_name", "region")
        hour = col("hour_of_day", "hour", "local_hour")
        month = col("month", "collection_month")
        for i, cid in enumerate(ids):
            meta[cid] = {
                "country": country[i] if country else None,
                "hour": hour[i] if hour else None,
                "month": month[i] if month else None,
            }
        log(f"loaded metadata for {len(meta):,} clips")
    except Exception as e:
        log("metadata load failed:", e)
    return meta


def load_scored_ids(path: Path) -> set:
    """Clip ids that carry a Gold difficulty (sensor-covered) in export_scores.py's snapshot."""
    if not path.exists():
        log(f"no {path} — run export_scores.py to show Gold difficulty; using all candidates")
        return set()
    import pyarrow.parquet as pq
    t = pq.read_table(path, columns=["clip_id", "sensor_covered", "difficulty_camera"]).to_pydict()
    ids = {c for c, cov, d in zip(t["clip_id"], t["sensor_covered"], t["difficulty_camera"]) if cov and d is not None}
    log(f"{len(ids):,} clips carry a Gold difficulty")
    return ids


def extract_frame(mp4: str, out_jpg: str, size):
    """Grab a representative frame ~40% into the clip, resize, save jpg.

    Returns an RGB ndarray (for optional YOLO) or None on failure.
    """
    import cv2
    cap = cv2.VideoCapture(mp4)
    if not cap.isOpened():
        return None
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    target = int(n * 0.4) if n else 60
    cap.set(cv2.CAP_PROP_POS_FRAMES, target)
    ok, bgr = cap.read()
    cap.release()
    if not ok or bgr is None:
        return None
    bgr = cv2.resize(bgr, size, interpolation=cv2.INTER_AREA)
    cv2.imwrite(out_jpg, bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)  # rgb ndarray for optional yolo


def decode_cloud(parquet: str, out_bin: str, max_points: int):
    """Decode one LiDAR spin (~40% in), subsample, write Float32 xyz."""
    import DracoPy
    import pyarrow.parquet as pq
    t = pq.read_table(parquet, columns=["draco_encoded_pointcloud"])
    blobs = t.column("draco_encoded_pointcloud").to_pylist()
    if not blobs:
        return 0
    idx = int(len(blobs) * 0.4)
    mesh = DracoPy.decode(blobs[idx])
    pts = np.asarray(mesh.points, dtype=np.float32)
    if pts.ndim != 2 or pts.shape[1] < 3:
        return 0
    pts = pts[:, :3]
    if len(pts) > max_points:
        sel = np.random.choice(len(pts), max_points, replace=False)
        pts = pts[sel]
    pts.astype("<f4").tofile(out_bin)
    return len(pts)


def run_yolo(model, rgb, size):
    """Return list of center-normalized detection dicts, or []."""
    try:
        res = model.predict(rgb, verbose=False, imgsz=640, conf=0.30)[0]
        H, W = rgb.shape[:2]
        names = res.names
        out = []
        for b in res.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            out.append({
                "x": round((x1 + x2) / 2 / W, 4), "y": round((y1 + y2) / 2 / H, 4),
                "w": round((x2 - x1) / W, 4), "h": round((y2 - y1) / H, 4),
                "label": names[int(b.cls[0])], "conf": round(float(b.conf[0]), 3),
            })
        return out[:8]
    except Exception as e:
        log("yolo predict failed:", e)
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--nfs", default=NFS_DEFAULT)
    ap.add_argument("--out", default="demo_wall/assets/clips")
    ap.add_argument("--frame-w", type=int, default=960)
    ap.add_argument("--frame-h", type=int, default=540)
    ap.add_argument("--cloud-points", type=int, default=12000)
    ap.add_argument("--yolo", action="store_true", help="run YOLOv8n for real detections")
    ap.add_argument("--scores", default="user_data/wall_scores.parquet",
                    help="export_scores.py output; limits candidates to clips with a Gold difficulty")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
        np.random.seed(args.seed)

    nfs = args.nfs.rstrip("/")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    size = (args.frame_w, args.frame_h)

    log("scanning NFS for candidate clips ...")
    cands = find_candidates(nfs)
    log(f"{len(cands):,} clips have both front-wide camera + LiDAR")
    if not cands:
        log("FATAL: no candidates — check --nfs path")
        sys.exit(1)

    meta = load_metadata(nfs)
    scored_ids = load_scored_ids(Path(args.scores))

    # Prefer clips with a Gold difficulty, so the Curate chapter can place every
    # displayed clip; fall back to the full pool if too few overlap.
    if scored_ids:
        scored = [c for c in cands if c[0] in scored_ids]
        log(f"{len(scored):,} of those carry a Gold difficulty")
        if len(scored) >= args.n:
            cands = scored
        else:
            log("intersection < --n; keeping full pool (some clips will lack a difficulty)")
    random.shuffle(cands)
    cands = cands[: args.n]

    model = None
    if args.yolo:
        try:
            from ultralytics import YOLO
            model = YOLO("yolov8n.pt")
            log("YOLOv8n loaded for real 2D detections")
        except Exception as e:
            log("ultralytics unavailable, continuing without detections:", e)

    clips = []
    t0 = time.time()
    for i, (cid, mp4, parquet) in enumerate(cands):
        jpg = out / f"{cid}.jpg"
        binf = out / f"{cid}.bin"
        try:
            rgb = extract_frame(mp4, str(jpg), size)
            if rgb is None:
                log(f"  skip {cid[:8]} (no frame)"); continue
            npts = decode_cloud(parquet, str(binf), args.cloud_points)
        except Exception as e:
            log(f"  skip {cid[:8]}: {e}"); continue

        m = meta.get(cid, {})
        month = m.get("month")
        season = SEASONS_N.get(int(month), None) if month not in (None, "") else None
        country = m.get("country")
        hour = m.get("hour")
        where_bits = [str(country) if country else None,
                      season,
                      (f"{int(hour):02d}:00" if hour not in (None, "") else None)]
        where = " · ".join(b for b in where_bits if b)
        dets = run_yolo(model, rgb, size) if model is not None else None

        clips.append({
            "id": cid,
            "img": f"assets/clips/{cid}.jpg",
            "cloud": f"assets/clips/{cid}.bin" if npts else None,
            "n_points": npts,
            "country": country, "season": season, "hour": hour,
            "where": where or "location withheld",
            "detections": dets,
        })
        if (i + 1) % 5 == 0 or i + 1 == len(cands):
            log(f"  [{i+1}/{len(cands)}] {time.time()-t0:.0f}s  last={cid[:8]} pts={npts}")

    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "NVIDIA PhysicalAI — Autonomous Vehicles (NFS subset)",
        "clips": clips,
    }
    (out / "manifest.json").write_text(json.dumps(manifest))
    log(f"DONE: {len(clips)} clips -> {out}/manifest.json  ({time.time()-t0:.0f}s)")
    try:                      # write each clip's Gold difficulty into the manifest
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import build_media
        build_media.annotate_clips()
    except Exception as e:
        log("difficulty annotation skipped:", e)


if __name__ == "__main__":
    main()
