#!/usr/bin/env bash
# VaVAM (valeoai VideoActionModel) assets + dependency probe. SLURM + Singularity.
#
# Point of this model: it is an OUT-OF-LAB, out-of-architecture policy (autoregressive
# video GPT + diffusion action expert, trained on OpenDV/nuPlan/nuScenes). Running it
# proves the harness's Policy contract is transferable, independently of what it
# scores — a domain gap makes the number hard to read but does not weaken that claim.
#
#   sbatch fetch_vavam.sbatch
#SBATCH --job-name=vavam-fetch
#SBATCH --nodes=1
#SBATCH --gres=gpu:1
#SBATCH --partition=jobs
#SBATCH --nodelist=hpc-pr-a-pod12
#SBATCH --time=01:00:00
#SBATCH --output=/scratch/autodr_test/alpamayo_eval/vavam_%j.out
#SBATCH --error=/scratch/autodr_test/alpamayo_eval/vavam_%j.err
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
V=$E/vavam
REL=https://github.com/valeoai/VideoActionModel/releases/download/v1.0.0
mkdir -p $V/ckpt $E/pyuser

# assets: action model (1.75 GB) + the VQ image tokeniser (0.12 GB). The action model
# consumes VQ token indices, not pixels, so the encoder is mandatory.
[ -s $V/ckpt/VAM_width_1024_pretrained_139k.pt ] || \
  curl -fL --retry 3 -o $V/ckpt/VAM_width_1024_pretrained_139k.pt $REL/VAM_width_1024_pretrained_139k.pt
[ -s $V/ckpt/VQ_ds16_16384_llamagen_encoder.jit ] || \
  curl -fL --retry 3 -o $V/ckpt/VQ_ds16_16384_llamagen_encoder.jit $REL/VQ_ds16_16384_llamagen_encoder.jit
ls -la $V/ckpt

[ -d $V/repo ] || git clone --depth 1 https://github.com/valeoai/VideoActionModel.git $V/repo

# The SIF is read-only, so extra deps go to a writable --user prefix on /scratch.
# Only what load_inference_VAM needs; the project's full dependency list (lightning,
# hydra, hyperqueue, jupyter, torchdata nightly...) is for TRAINING.
# NOTE the SIF sets PYTHONNOUSERSITE=1 (my own doing, in alpamayo.def), which makes
# `pip install --user` impossible. A venv with --system-site-packages is the correct
# way to layer packages onto a read-only container: it inherits the image's torch and
# adds only what VaVAM needs, on /scratch.
singularity exec --nv $SING_USER_BIND -B $H:$H $E/alpamayo_eval.sif bash -c "
  [ -x $V/venv/bin/python ] || python -m venv --system-site-packages $V/venv
  export PYTHONPATH=$V/repo
  $V/venv/bin/pip install --no-cache-dir 'git+https://github.com/microsoft/mup.git' \
      lightning==2.4.0 rich hydra-core omegaconf torchmetrics colorlog pyquaternion \
      prettytable 2>&1 | tail -3
  $V/venv/bin/python -c '
import torch
from vam.action_expert import load_inference_VAM
print(\"vam import OK\")
enc = torch.jit.load(\"$V/ckpt/VQ_ds16_16384_llamagen_encoder.jit\").to(\"cuda\").eval()
x = torch.randn(1,3,288,512, device=\"cuda\")
with torch.no_grad():
    tok = enc(x)
print(\"tokeniser OK, token shape\", tuple(tok.shape), tok.dtype)
'
"
echo ">>> VAVAM SETUP DONE"
