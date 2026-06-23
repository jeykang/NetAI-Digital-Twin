#!/usr/bin/env python3
"""build_portable.py — emit a self-contained, USB-transferable copy of the wall.

The served demo loads the clip manifest + LiDAR clouds via fetch(), which
browsers block under file://. This builder produces `demo_wall_portable/` where
the manifest and every point cloud are INLINED as JavaScript, so the folder runs
by simply double-clicking index.html — no web server, no Chrome flags, offline.

  python demo_wall/build_portable.py                 # package whatever is extracted
  python demo_wall/build_portable.py --size 500       # ~500 MB of real clips
  python demo_wall/build_portable.py --clips 800      # exactly ~800 clips

--size / --clips drive how MANY distinct real clips the portable build holds: a
longer non-repeating loop for a wall that runs for days/weeks. To reach the
target the builder tops up the clip library by invoking extract_assets.py (needs
the server-side venv + NFS); pass --no-extract to package only what already
exists. Each clip ≈ 0.25 MB portable and ≈ 33 s of loop time.
"""
from __future__ import annotations
import argparse
import base64
import json
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent          # .../demo_wall
REPO = SRC.parent                              # .../Iceberg
OUT = REPO / "demo_wall_portable"
CLIPS = SRC / "assets" / "clips"
STATIC_OVERHEAD_MB = 0.6                        # html/css/js + 3 baked frames
LOOP_SECONDS_PER_CLIP = 32.8                    # 4 stages × STAGE_MS (8.2 s)
DEFAULT_CAP = 500                              # safe default if the library is huge


def log(*a):
    print("[portable]", *a, flush=True)


def read_manifest():
    p = CLIPS / "manifest.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def per_clip_mb(manifest):
    """Average portable cost of a clip (frame jpg + base64-inflated cloud)."""
    samples = []
    for c in manifest.get("clips", [])[:40]:
        cid = c["id"]
        jpg = CLIPS / f"{cid}.jpg"
        binf = CLIPS / f"{cid}.bin"
        b = (jpg.stat().st_size if jpg.exists() else 0)
        b += int((binf.stat().st_size if binf.exists() else 0) * 4 / 3)
        if b:
            samples.append(b)
    if not samples:
        return 0.25
    return (sum(samples) / len(samples)) / 1e6


def extract_more(target, extract_args, python):
    """Top up the clip library to `target` distinct clips via extract_assets.py."""
    script = SRC / "extract_assets.py"
    py = python or (SRC / ".venv" / "bin" / "python")
    if not Path(py).exists():
        log(f"!! extractor python not found at {py}")
        log("   install deps (see README) or pass --python; packaging existing clips only.")
        return False
    cmd = [str(py), str(script), "--n", str(target)] + extract_args
    log("extracting:", " ".join(cmd))
    log(f"   (~{target} clips; first run can take a while — frames + LiDAR decode)")
    try:
        subprocess.run(cmd, cwd=str(REPO), check=True)
        return True
    except subprocess.CalledProcessError as e:
        log("!! extraction failed:", e, "— packaging existing clips only.")
        return False


def build(clips_subset, manifest_meta):
    """Lazy-cloud portable build: tiny manifest.js + one small per-clip cloud
    script each (loaded on demand via <script> injection, file://-safe). Scales
    from dozens to thousands of clips without one giant inlined file."""
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "css").mkdir(parents=True)
    (OUT / "js").mkdir(parents=True)
    (OUT / "assets" / "clips").mkdir(parents=True)

    for rel in ["css/style.css", "js/data.js", "js/lidar.js", "js/app.js"]:
        shutil.copy2(SRC / rel, OUT / rel)
    for cam in sorted((SRC / "assets").glob("cam*.jpg")):
        shutil.copy2(cam, OUT / "assets" / cam.name)

    total_cloud = 0
    packed = []
    for clip in clips_subset:
        clip = dict(clip)
        cid = clip["id"]
        jpg = CLIPS / f"{cid}.jpg"
        if jpg.exists():
            shutil.copy2(jpg, OUT / "assets" / "clips" / jpg.name)
        binf = CLIPS / f"{cid}.bin"
        if binf.exists():
            b64 = base64.b64encode(binf.read_bytes()).decode("ascii")
            total_cloud += binf.stat().st_size
            # per-clip cloud script: (window.__C=window.__C||{})["id"]="<b64>";
            (OUT / "assets" / "clips" / f"{cid}.cloud.js").write_text(
                f'(window.__C=window.__C||{{}})["{cid}"]="{b64}";\n')
            clip["cloud_js"] = f"assets/clips/{cid}.cloud.js"
        clip.pop("cloud", None)
        clip.pop("cloud_b64", None)
        packed.append(clip)

    out_manifest = dict(manifest_meta)
    out_manifest["clips"] = packed
    (OUT / "assets" / "clips" / "manifest.js").write_text(
        "window.DEMO_MANIFEST = " + json.dumps(out_manifest) + ";\n")

    html = (SRC / "index.html").read_text()
    inject = ('  <script src="assets/clips/manifest.js"></script>\n'
              '  <script src="js/data.js"></script>')
    html = html.replace('  <script src="js/data.js"></script>', inject, 1)
    (OUT / "index.html").write_text(html)

    (OUT / "run_linux.sh").write_text(
        '#!/bin/sh\n'
        '# Full-screen kiosk on Linux. Needs google-chrome or chromium installed.\n'
        'DIR="$(cd "$(dirname "$0")" && pwd)"\n'
        'BIN="$(command -v google-chrome || command -v chromium || command -v chromium-browser)"\n'
        '"$BIN" --kiosk --noerrdialogs --disable-infobars --incognito "file://$DIR/index.html"\n')
    (OUT / "run_linux.sh").chmod(0o755)
    (OUT / "run_windows.bat").write_text(
        "@echo off\r\n"
        "rem Full-screen kiosk on Windows (uses default Chrome install).\r\n"
        'start chrome --kiosk --noerrdialogs --disable-infobars --incognito "file://%~dp0index.html"\r\n')
    (OUT / "README_PORTABLE.txt").write_text(
        "EAD-Data Lakehouse — portable wall display\n"
        "==========================================\n\n"
        "Self-contained. No server, no internet, no install needed.\n\n"
        "TO RUN:\n"
        "  * Easiest: double-click index.html (opens in your default browser).\n"
        "      Then press F11 for full screen.\n"
        "  * Kiosk (auto full-screen, Chrome):\n"
        "      Windows: double-click run_windows.bat\n"
        "      Linux:   ./run_linux.sh\n\n"
        "It loops a set of real autonomous-driving clips through the lakehouse\n"
        "pipeline (Ingest -> Curate -> GPU Perception -> Serve). Everything is\n"
        "baked into this folder; just copy the whole folder to the demo PC.\n\n"
        "To exit kiosk mode: Alt+F4 (Windows) or Ctrl+W.\n")
    return len(packed), total_cloud


def main():
    ap = argparse.ArgumentParser(description="Build the self-contained portable wall display.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--size", type=float, help="target portable size in MB (drives clip count)")
    g.add_argument("--clips", type=int, help="target number of distinct clips")
    g.add_argument("--all", action="store_true", help="package the ENTIRE extracted library")
    ap.add_argument("--no-extract", action="store_true",
                    help="never run the extractor; package only already-extracted clips")
    ap.add_argument("--python", help="python used for extraction (default demo_wall/.venv/bin/python)")
    ap.add_argument("--extract-args", default="--yolo --trino",
                    help='args passed to extract_assets.py (default "--yolo --trino")')
    args = ap.parse_args()

    manifest = read_manifest()
    if manifest is None:
        raise SystemExit(
            "no clip library yet — run extract_assets.py first, e.g.\n"
            "  demo_wall/.venv/bin/python demo_wall/extract_assets.py --n 40 --yolo --trino")

    current = len(manifest.get("clips", []))
    pcm = per_clip_mb(manifest)
    log(f"current library: {current} clips  (~{pcm:.2f} MB/clip portable)")

    # resolve target clip count
    if args.all:
        target = current
    elif args.clips:
        target = args.clips
    elif args.size:
        budget = max(args.size - STATIC_OVERHEAD_MB, pcm)
        target = max(1, int(budget / pcm))
        log(f"size budget {args.size:.0f} MB → ~{target} clips")
    else:
        # no explicit target: package everything, but cap a huge library so we
        # never accidentally emit a multi-GB folder. Use --all / --size / --clips
        # to go bigger.
        target = min(current, DEFAULT_CAP)
        if current > DEFAULT_CAP:
            log(f"library has {current} clips; packaging {DEFAULT_CAP} by default "
                f"(~{DEFAULT_CAP * LOOP_SECONDS_PER_CLIP / 3600:.1f} h loop). "
                f"Use --all / --size / --clips for more.")

    if target > current and not args.no_extract:
        if extract_more(target, args.extract_args.split(), args.python):
            manifest = read_manifest() or manifest
            current = len(manifest.get("clips", []))
            log(f"library now: {current} clips")
    elif target > current:
        log(f"--no-extract set; packaging {current} existing clips (asked for {target}).")

    clips = manifest.get("clips", [])
    if target < len(clips):
        clips = clips[:target]          # honor a smaller size cap

    n, cloud_bytes = build(clips, {k: v for k, v in manifest.items() if k != "clips"})

    files = sum(1 for _ in OUT.rglob('*') if _.is_file())
    folder_mb = sum(f.stat().st_size for f in OUT.rglob('*') if f.is_file()) / 1e6
    loop_h = n * LOOP_SECONDS_PER_CLIP / 3600
    log(f"wrote {OUT}")
    log(f"{n} clips packaged (lazy per-clip cloud scripts, ~{cloud_bytes*4/3/1e6:.0f} MB clouds)")
    log(f"total folder size: {folder_mb:.0f} MB across {files:,} files")
    log(f"non-repeating loop length: ~{loop_h:.1f} h ({loop_h/24:.1f} days) before clips repeat")
    log(f"copy the whole '{OUT.name}' folder to USB; double-click index.html to run.")


if __name__ == "__main__":
    main()
