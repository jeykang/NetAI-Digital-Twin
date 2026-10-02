# EAD proving ground — hallway wall display

A full-screen, unattended loop for the hallway monitor: how the lab's autonomous-driving
proving ground (검증장) turns real drives into validated verdicts on a driving policy.
Six chapters, about 75 s per loop; every loop follows a different real clip, digital twin,
closed-loop rollout and Cosmos window, so the screen rarely repeats.

| # | Chapter | On screen | Comes from |
|---|---|---|---|
| 01 | Collect 수집 | a real front-camera frame with camera-only detections, and that clip's LiDAR sweep | `assets/clips/` (`extract_assets.py`, NFS sample) |
| 02 | Curate 큐레이션 | the medallion funnel, and where this clip's difficulty lands (traffic conflict, camera perception, percentile, Gold or not) | `nvidia_gold.clip_scores` via `export_scores.py` |
| 03 | Serve 진열 | a recorded window beside its Cosmos-Transfer variant; episodes per scenario class and serving mode | `cosmos_augmentation/gate_report.json` (kept variants only), `nvidia_gold.scenario` |
| 04 | Reconstruct 재구성 | real camera wiped against the NuRec twin render, then against the twin's depth; the twin's build timeline | `evaluation/nurec/out/<clip>_a10_prod/val`, `<clip>.twin.json` |
| 05 | Validate 검증 | VaVAM driving our twin and NVIDIA's reconstruction of the same clip, each stopped at its scored end with the outcome | `evaluation/alpasim/runs/<clip>_{ours_map,nvidia}_vavam` |
| 06 | Triage 선별 | the 80 closed-loop scenes in the screen's order, the 50 % budget filling in, recall vs budget | `evaluation/skip.py` via `export_triage.py` |

Chapters 04 and 05 show the same twin, so a viewer sees a clip reconstructed and then driven.

**Every number on screen is in `js/data.js`**, next to the doc or Iceberg table it comes
from (`evaluation/nurec/README.md`, `SKIP.md`, `ALPASIM.md`, `MEDALLION_PROGRESS.md`,
`nvidia_gold.*` snapshot metadata). Change a number there and in its source doc together.
Wording follows `../TERMINOLOGY.md`. Some care taken so the screen does not overclaim:

- closed-loop videos stop at the span AlpaSim scores (first collision or off-road, or ≥ 4 m
  off the recorded path); past it the renders leave the reconstructed area and fall apart;
- the twin's validation frames are also training views, so the wall says "same viewpoint as
  the real camera", not "held-out view";
- only Cosmos variants the hallucination gate kept (43 of 50) are shown;
- the Gold count shown is the documented 3,176; the live camera-axis cut used for the
  per-clip badge gives 3,174–3,177 depending on tie handling;
- twins show country and season, not day/night: `hour_of_day` disagrees with the frames for
  some clips (ba91fe2c is tagged 02:00 and filmed in daylight).

## Serve it

nginx serves this folder. The `demo-wall` service lives in the gitignored
`docker-compose.override.yml`; to recreate it:

```yaml
services:
  demo-wall:
    image: nginx:alpine
    container_name: demo-wall
    restart: unless-stopped
    ports: ["8090:80"]
    volumes: ["./demo_wall:/usr/share/nginx/html:ro"]
```

```bash
docker compose up -d demo-wall          # from Lakehouse/Iceberg
chromium --kiosk --noerrdialogs --disable-infobars --incognito http://<server-ip>:8090
```

The page reloads itself once a day to pick up rebuilt media. A browser that still runs the
pre-October page needs one manual reload (F5). Turn off the demo PC's screen blanking
(`xset s off -dpms`).

## Refresh the data

Run from `Lakehouse/Iceberg`. Steps 1–2 export data from environments the wall venv does not
have; step 4 builds the videos (only missing or stale ones) and `assets/media/media.js`.

```bash
# 0. once: the wall venv
python3 -m venv demo_wall/.venv && demo_wall/.venv/bin/pip install -r demo_wall/requirements.txt

# 1. Gold difficulty snapshot (inside the Spark container; reads Iceberg, not NFS)
docker cp demo_wall/export_scores.py spark-iceberg:/tmp/export_scores.py
docker exec -w /opt/spark spark-iceberg /opt/spark/bin/spark-submit /tmp/export_scores.py
#    -> user_data/wall_scores.{parquet,json}

# 2. rollout-triage ranking (refuses to write if it no longer reproduces SKIP.md)
evaluation/.skip_venv/bin/python demo_wall/export_triage.py      # -> user_data/wall_triage.json

# 3. optional: a fresh real-clip library (needs NFS; --yolo adds detections)
demo_wall/.venv/bin/python demo_wall/extract_assets.py --n 2000 --yolo

# 4. media: twins, closed-loop pairs, Cosmos pairs, clip annotation
demo_wall/.venv/bin/python demo_wall/build_media.py              # --force re-encodes everything
```

New twins (`evaluation/nurec/twin_pipeline.sh`) appear on the wall after step 4: the builder
finds every `nurec/out/<clip>.twin.json` with validation frames and VaVAM runs. The Cosmos
variants are read from the PDSW'26 data bundle (`--variants`, default
`~/jeykang/pdsw26-artifact-data/variants`). Generated files (`assets/clips/`,
`assets/media/`) are gitignored.

`extract_assets.py` writes a manifest of the clips it extracted in that run only; the
library on the server (16,568 clips) came from one large run.

## Portable / USB copy

```bash
demo_wall/.venv/bin/python demo_wall/build_portable.py --no-extract            # 500 clips, ~210 MB
demo_wall/.venv/bin/python demo_wall/build_portable.py --all --out /media/usb/wall
```

Double-click `index.html` in the copy (or `run_windows.bat` / `run_linux.sh` for kiosk
mode). Clouds and the manifest are `<script>` files, so it runs from `file://` with no
server. Each clip adds ~0.25 MB and one loop; the media library adds a fixed ~90 MB. The
default output, `../demo_wall_portable/`, is replaced on every build.

## Preview and test

| URL | Effect |
|---|---|
| `?ch=validate&hold=1` | open on one chapter and stay there |
| `?speed=5` | run the loop five times faster (soak tests) |

Without `assets/media/media.js` or the clip library the wall still runs: chapters fall back
to the three baked frames and the numbers in `data.js`.

## Files

| File | Role |
|---|---|
| `index.html` | page skeleton: header, chapter rail, six chapters, footer |
| `css/style.css` | layout and type; one unit (`--u`), so 1080p and 4K look the same |
| `js/data.js` | every number and sentence on screen, with sources; chapter durations |
| `js/app.js` | loop, per-loop samples, video players, wipe canvas, fallbacks |
| `js/charts.js` | funnel, difficulty meter, scenario table, build bar, waffle, recall chart |
| `js/lidar.js` | dependency-free Canvas point-cloud renderer |
| `export_scores.py` | Gold difficulty snapshot from Iceberg (runs in spark-iceberg) |
| `export_triage.py` | per-clip triage scores via `evaluation/skip.py` |
| `extract_assets.py` | real-clip library: frames, LiDAR sweeps, detections |
| `build_media.py` | twin / closed-loop / Cosmos videos, `media.js`, clip annotation |
| `build_portable.py` | self-contained offline copy |
| `assets/cam1–3.jpg`, `assets/gist_logo.png` | baked fallback frames, logo |
