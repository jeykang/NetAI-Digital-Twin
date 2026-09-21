#!/usr/bin/env bash
# Fetch the evaluation slice straight from HuggingFace onto /scratch — SLURM +
# Singularity, no login-node work, and NO dependency on the local NFS mount.
#
# The dataset is published as one ZIP per (sensor, chunk). This pulls only the
# chunks named in slice_manifest.json and unpacks them into the on-disk layout the
# adapter expects, so AV_ROOT points at it and nothing downstream changes:
#   camera/<cam>/<cam>.chunk_XXXX/<clip>.<cam>.mp4|.timestamps.parquet
#   labels/egomotion/egomotion.chunk_XXXX/<clip>.egomotion.parquet
#   labels/obstacle.offline/obstacle.offline.chunk_XXXX.zip   (left zipped — the
#                                                              adapter reads it so)
#   calibration/vehicle_dimensions/vehicle_dimensions.chunk_XXXX.parquet
#
#   sbatch fetch_slice.sbatch
#SBATCH --job-name=alpamayo-slice
#SBATCH --nodes=1
#SBATCH --gres=gpu:1
#SBATCH --partition=jobs
#SBATCH --nodelist=hpc-pr-a-pod12
#SBATCH --time=06:00:00
#SBATCH --output=/scratch/autodr_test/alpamayo_eval/slice_%j.out
#SBATCH --error=/scratch/autodr_test/alpamayo_eval/slice_%j.err
set -eo pipefail

# --- assigned-node guard -------------------------------------------------------
# ASSIGNMENT: pod12 + pod15, BOTH in partition `jobs`, until 2026-08-24 00:00 KST.
# Verified schedulable 2026-08-20. Anything landing elsewhere is a mistake, so this
# refuses rather than quietly borrowing another group's node.
ALLOWED_NODES="hpc-pr-a-pod12 hpc-pr-a-pod15"
THIS_NODE=$(hostname)
case " $ALLOWED_NODES " in
  *" $THIS_NODE "*) : ;;
  *) echo "REFUSING: landed on $THIS_NODE, which is not in assigned set ($ALLOWED_NODES)"; exit 3 ;;
esac


H=/scratch/autodr_test
E=$H/alpamayo_eval

# --- singularity user resolution -----------------------------------------------
# pod12/pod15 cannot resolve uid 1064 at all ("id: cannot find name for user ID
# 1064"), so Singularity aborts with
#   FATAL: Couldn't determine user account information: user: unknown userid 1064
# pod09 could resolve it; this is a node-level nsswitch/passwd difference, nothing
# to do with the job. Bind a synthetic passwd/group holding just this user. Values
# are literal because `id -un` also fails on these nodes.
PW=$E/.sing_passwd
GR=$E/.sing_group
echo 'autodr_test:x:1064:1065::/scratch/autodr_test:/bin/bash' > $PW
echo 'autodr_test:x:1065:' > $GR
SING_USER_BIND="-B $PW:/etc/passwd -B $GR:/etc/group"
mkdir -p $E/av_root $E/hf_cache

singularity exec $SING_USER_BIND -B $H:$H --env HF_HOME=$E/hf_cache $E/alpamayo_eval.sif python - <<'PY'
import json, os, shutil, zipfile
from huggingface_hub import hf_hub_download

E = "/scratch/autodr_test/alpamayo_eval"
ROOT = f"{E}/av_root"
REPO = "nvidia/PhysicalAI-Autonomous-Vehicles"
import os as _os
MANIFEST = _os.environ.get("SLICE_MANIFEST", f"{E}/slice_manifest.json")
ROOT = _os.environ.get("SLICE_ROOT", ROOT)
man = json.load(open(MANIFEST))
cams, chunks = man["cameras"], man["chunks"]
print(f"[slice] {len(man['clips'])} clips / {len(chunks)} chunks / {len(cams)} cameras",
      flush=True)
# Pass the token EXPLICITLY. Neither --env propagation nor $HF_HOME/token resolved
# inside the container, and the dataset is gated (the model repos were not).
TOKEN = open(f"{E}/.hf_token").read().strip()
from huggingface_hub import HfApi
print(f"[slice] authenticated as {HfApi().whoami(token=TOKEN).get('name', '?')}", flush=True)


def grab(path):
    return hf_hub_download(REPO, path, repo_type="dataset", token=TOKEN)


def unpack(zpath, dest, keep):
    """Extract only the selected clips' files into dest."""
    os.makedirs(dest, exist_ok=True)
    n = 0
    with zipfile.ZipFile(zpath) as z:
        for nm in z.namelist():
            base = os.path.basename(nm)
            if not base or not any(base.startswith(c) for c in keep):
                continue
            with z.open(nm) as src, open(os.path.join(dest, base), "wb") as dst:
                shutil.copyfileobj(src, dst)
            n += 1
    return n


for ch in chunks:
    keep = man["clips_by_chunk"][ch]
    for cam in cams:
        p = grab(f"camera/{cam}/{cam}.chunk_{ch}.zip")
        n = unpack(p, f"{ROOT}/camera/{cam}/{cam}.chunk_{ch}", keep)
        print(f"  chunk {ch} {cam}: {n} files", flush=True)
    p = grab(f"labels/egomotion/egomotion.chunk_{ch}.zip")
    n = unpack(p, f"{ROOT}/labels/egomotion/egomotion.chunk_{ch}", keep)
    print(f"  chunk {ch} egomotion: {n} files", flush=True)

    # obstacle labels stay zipped; the adapter opens the chunk zip directly. Rebuild
    # it with only this slice's clips so av_root stays small.
    src = grab(f"labels/obstacle.offline/obstacle.offline.chunk_{ch}.zip")
    dstdir = f"{ROOT}/labels/obstacle.offline"; os.makedirs(dstdir, exist_ok=True)
    kept = 0
    with zipfile.ZipFile(src) as zin, \
         zipfile.ZipFile(f"{dstdir}/obstacle.offline.chunk_{ch}.zip", "w",
                         zipfile.ZIP_DEFLATED) as zout:
        for nm in zin.namelist():
            if any(os.path.basename(nm).startswith(c) for c in keep):
                zout.writestr(os.path.basename(nm), zin.read(nm)); kept += 1
    print(f"  chunk {ch} obstacle: {kept} records", flush=True)

    try:
        p = grab(f"calibration/vehicle_dimensions/vehicle_dimensions.chunk_{ch}.parquet")
        d = f"{ROOT}/calibration/vehicle_dimensions"; os.makedirs(d, exist_ok=True)
        shutil.copyfile(p, f"{d}/vehicle_dimensions.chunk_{ch}.parquet")
    except Exception as ex:
        print(f"  chunk {ch} vehicle_dimensions unavailable ({str(ex)[:60]}) "
              "- adapter falls back to default footprint", flush=True)

# the harness's clip-list cache, so it never globs this tree
json.dump(sorted(man["clips"]), open(_os.environ.get("SLICE_CLIPS", f"{E}/evaluation/.clip_list.json"), "w"))
print(">>> SLICE READY", flush=True)
PY
du -sh $E/av_root
echo ">>> FETCH DONE"
