#!/usr/bin/env python3
"""usdz_tools.py — inspect a NuRec USDZ bundle, or build a hybrid from two bundles.

    usdz_tools.py inspect <bundle.usdz>
    usdz_tools.py inject <ours.usdz> <reference.usdz> <out.usdz> [--members map.xodr clipgt/ ...]
    usdz_tools.py fix-meta <bundle.usdz> --scene-id clipgt-<clip> [--uuid <uuid>]

`inject` copies members that our export cannot produce (PAI has no map labels, so no
`map.xodr` / `clipgt/*`) from NVIDIA's bundle of the same clip into ours, leaving our
neural scene, trajectories, tracks and meshes untouched. That isolates reconstruction
quality from map availability in an AlpaSim A/B. Entries are written uncompressed, as
USDZ expects.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import uuid as uuidlib
import zipfile

import yaml

# map layers PAI lacks, plus the ground mesh in case our export produced none (only
# members missing from our bundle are ever copied)
DEFAULT_INJECT = ["map.xodr", "clipgt/", "mesh_ground.ply", "mesh_ground.usd"]


def inspect(path: str):
    z = zipfile.ZipFile(path)
    names = z.namelist()
    tot = sum(z.getinfo(n).file_size for n in names)
    print(f"{path}: {len(names)} members, {tot/1e9:.2f} GB")
    for n in names:
        if not n.startswith("clipgt/") and not n.startswith("frames/"):
            print(f"  {z.getinfo(n).file_size/1e6:9.1f} MB  {n}")
    print(f"  clipgt/ members: {sum(n.startswith('clipgt/') for n in names)}; frames/: {sum(n.startswith('frames/') for n in names)}")
    if "metadata.yaml" in names:
        m = yaml.safe_load(z.read("metadata.yaml"))
        print("  metadata:", {k: m.get(k) for k in ("uuid", "scene_id", "version_string", "time_range")},
              "cameras:", len((m.get("sensors") or {}).get("camera_ids") or []))


def _copy(zin: zipfile.ZipFile, zout: zipfile.ZipFile, name: str):
    info = zin.getinfo(name)
    zout.writestr(zipfile.ZipInfo(name, date_time=info.date_time), zin.read(name), compress_type=zipfile.ZIP_STORED)


def inject(ours: str, ref: str, out: str, members: list[str]):
    zo, zr = zipfile.ZipFile(ours), zipfile.ZipFile(ref)
    have = set(zo.namelist())
    want = [n for n in zr.namelist() if any(n == m or (m.endswith("/") and n.startswith(m)) for m in members)]
    added = [n for n in want if n not in have]
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as zw:
        for n in zo.namelist():
            _copy(zo, zw, n)
        for n in added:
            _copy(zr, zw, n)
    print(f"{out}: {len(zo.namelist())} own members + {len(added)} injected from reference: "
          f"{[n for n in added if not n.startswith('clipgt/')]} + {sum(n.startswith('clipgt/') for n in added)} clipgt files")


def fix_meta(path: str, scene_id: str | None, uid: str | None):
    z = zipfile.ZipFile(path)
    m = yaml.safe_load(z.read("metadata.yaml")) if "metadata.yaml" in z.namelist() else {}
    changed = False
    if scene_id and m.get("scene_id") != scene_id:
        m["scene_id"] = scene_id; changed = True
    if uid or not m.get("uuid"):
        m["uuid"] = uid or str(uuidlib.uuid4()); changed = True
    if not changed:
        print("metadata unchanged:", {k: m.get(k) for k in ("uuid", "scene_id")}); return
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as zw:
        for n in z.namelist():
            if n == "metadata.yaml":
                zw.writestr("metadata.yaml", yaml.safe_dump(m, sort_keys=False))
            else:
                _copy(z, zw, n)
    z.close(); os.replace(tmp, path)
    print("metadata updated:", {k: m.get(k) for k in ("uuid", "scene_id")})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("inspect"); s.add_argument("bundle")
    s = sub.add_parser("inject"); s.add_argument("ours"); s.add_argument("reference"); s.add_argument("out")
    s.add_argument("--members", nargs="+", default=DEFAULT_INJECT)
    s = sub.add_parser("fix-meta"); s.add_argument("bundle"); s.add_argument("--scene-id"); s.add_argument("--uuid")
    a = ap.parse_args()
    if a.cmd == "inspect":
        inspect(a.bundle)
    elif a.cmd == "inject":
        inject(a.ours, a.reference, a.out, a.members)
    else:
        fix_meta(a.bundle, a.scene_id, a.uuid)


if __name__ == "__main__":
    main()
