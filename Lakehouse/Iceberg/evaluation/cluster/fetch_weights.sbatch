#!/usr/bin/env bash
# Model-weight download as a SLURM job inside the SIF — not on the login node.
# No GPU needed, but it still goes through the scheduler and stays inside $H.
#   sbatch --export=ALL,MODELS="nvidia/Alpamayo-R1-10B" fetch_weights.sbatch
#SBATCH --job-name=alpamayo-weights
#SBATCH --nodes=1
#SBATCH --gres=gpu:1
#SBATCH --partition=jobs
#SBATCH --nodelist=hpc-pr-a-pod12
#SBATCH --time=03:00:00
#SBATCH --output=/scratch/autodr_test/alpamayo_eval/weights_%j.out
#SBATCH --error=/scratch/autodr_test/alpamayo_eval/weights_%j.err
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
MODELS=${MODELS:-"nvidia/Alpamayo-R1-10B"}
mkdir -p $E/hf_cache $E/src

singularity exec $SING_USER_BIND -B $H:$H --env HF_HOME=$E/hf_cache $E/alpamayo_eval.sif bash -c "
  set -e
  for M in $MODELS; do
    echo \"[weights] \$M\"
    python -c \"
from huggingface_hub import snapshot_download
import sys; print('  ->', snapshot_download(sys.argv[1], max_workers=8))
\" \$M
  done
  # model sources (git is inside the image; the login node never pulls)
  [ -d $E/src/alpamayo_r1 ] || git clone --depth 1 https://github.com/NVlabs/alpamayo.git $E/src/alpamayo_r1
  [ -d $E/src/alpamayo2 ]   || git clone --depth 1 https://github.com/NVlabs/alpamayo2.git $E/src/alpamayo2 || true
"
echo ">>> WEIGHTS DONE"
