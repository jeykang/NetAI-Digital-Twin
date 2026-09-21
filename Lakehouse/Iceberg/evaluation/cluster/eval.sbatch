#!/usr/bin/env bash
# Alpamayo evaluation — SLURM + Singularity, the required way to use this cluster.
# Nothing runs on the login node and nothing is written outside $CLUSTER_HOME.
#
# Assigned nodes ONLY: hpc-pr-a-pod09 and hpc-pr-a-pod17. Both are now free (the
# CARLA project that held pod17 has concluded). One node per job: a two-node
# --nodelist means "allocate BOTH" and SLURM rejects it against --nodes=1
# ("invalid number of nodes (-N 2-1)"). To use the second node, override at submit:
#     sbatch --nodelist=hpc-pr-a-pod17 ...
# which is also how to evaluate two models concurrently, one per node.
# Never target any other node.
#
# Submit (from the login node, sbatch only):
#   sbatch --export=ALL,MODEL=r1,LIMIT=60 eval.sbatch
#   sbatch --export=ALL,MODEL=alpamayo2,LIMIT=60 --gres=gpu:4 eval.sbatch
#
# Sizing on A100-SXM4-40GB (confirmed on pod09):
#   alpamayo_1_5 / alpamayo_r1   ~21-22 GB weights -> 1 GPU
#   alpamayo2-super              ~68 GB weights / 72 GB peak -> >=2, use 4
#SBATCH --job-name=alpamayo-eval
#SBATCH --nodes=1
#SBATCH --gres=gpu:1
#SBATCH --partition=jobs
#SBATCH --nodelist=hpc-pr-a-pod12
#SBATCH --time=04:00:00
#SBATCH --output=/scratch/autodr_test/alpamayo_eval/slurm_%j.out
#SBATCH --error=/scratch/autodr_test/alpamayo_eval/slurm_%j.err
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
MODEL=${MODEL:-r1}
LIMIT=${LIMIT:-60}
# TAG keeps runs at different horizons from clobbering each other's parquet
TAG=${TAG:-}

echo "[job] node=$(hostname) model=$MODEL limit=$LIMIT"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

case "$MODEL" in
  r1)        POLICY=policy_alpamayo:AlpamayoR1Policy ;;
  v15)       POLICY=policy_alpamayo:AlpamayoPolicy ;;
  alpamayo2) POLICY=policy_alpamayo:Alpamayo2Policy ;;
  vavam)     POLICY=policy_vavam:VaVAMPolicy ;;
  # reference ladder — track-only, no model weights, seconds per run
  replay_human|stationary|constant_velocity|constant_turn_rate|reactive_idm)
             POLICY=$MODEL ;;
  *) echo "unknown MODEL=$MODEL"; exit 2 ;;
esac

# Bind only $H — never bare /scratch, which is shared with other users.
#
# Env vars are exported INSIDE the container rather than passed with --env:
# --env silently failed to propagate here (it cost us both the HF token and this
# PYTHONPATH). Exporting in the bash -c is unambiguous.
# Alpamayo 1.5 pulls a GATED base repo (nvidia/Cosmos-Reason2-8B) at load time, so
# the token must be present for evaluation too, not just for the data fetch.
[ -s $E/.hf_token ] || { echo "missing $E/.hf_token"; exit 3; }
HFTOK=$(cat $E/.hf_token)

singularity exec --nv $SING_USER_BIND -B $H:$H $E/alpamayo_eval.sif bash -c "
  export HF_HOME=$E/hf_cache
  export HF_TOKEN=$HFTOK
  export HUGGING_FACE_HUB_TOKEN=$HFTOK
  export AV_ROOT=${AV_ROOT_OVERRIDE:-$E/av_root}
  export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
  export PYTHONPATH=$E/evaluation:$E/src/alpamayo_r1/src:$E/src/alpamayo1_5/src:$E/src/alpamayo2/src
  export ALPAMAYO_R1_SRC=$E/src/alpamayo_r1/src
  export ALPAMAYO2_SRC=$E/src/alpamayo2/src
  export VAM_REPO=$E/vavam/repo
  # bitsandbytes (for A2_QUANT=int8) lives in the same layered venv as VaVAM's deps
  [ -z "$A2_QUANT" ] || $E/vavam/venv/bin/pip install --no-cache-dir -q bitsandbytes 2>&1 | tail -1
  # VaVAM's extra deps live in a venv layered on the read-only SIF
  export PYTHONPATH=\$PYTHONPATH:$E/vavam/repo:$E/vavam/venv/lib/python3.12/site-packages
  python -c 'import importlib; m={\"r1\":\"alpamayo_r1\",\"v15\":\"alpamayo1_5\",\"alpamayo2\":\"alpamayo2_super\",\"vavam\":\"vam.action_expert\"}.get(\"'$MODEL'\"); m and importlib.import_module(m); print(m or \"builtin policy\", \"import OK\")' || exit 4
  cd $E/evaluation && python run_eval.py --policy $POLICY \
      ${CLIPS_FILE:+--clips-file $CLIPS_FILE} ${CLIPS_FILE:---limit $LIMIT} --workers 1 --require-sensors \
      --out $E/results_${MODEL}${TAG}.parquet
"
echo ">>> EVAL DONE ($MODEL)"
