#!/usr/bin/env bash
# Batch augmentation: generate every batch_specs/*.json variant (easy clip x assigned
# condition, depth control) in ONE node allocation, sequentially. Resumable (skips
# existing outputs), failure-tolerant (one bad clip won't kill the batch).
# ONE node only (pod17 reserved for the other project).
#SBATCH --job-name=cosmos-batch
#SBATCH --nodes=1
#SBATCH --gres=gpu:4
#SBATCH --nodelist=hpc-pr-a-pod09
#SBATCH --partition=jobs
#SBATCH --time=12:00:00
#SBATCH --output=/scratch/autodr_test/aug_test/batch_%j.out
#SBATCH --error=/scratch/autodr_test/aug_test/batch_%j.err
set -eo pipefail
H=/scratch/autodr_test
echo "[job] node=$(hostname) start=$(date +%H:%M:%S)"
for spec in $H/aug_test/batch_specs/*.json; do
  name=$(basename "$spec" .json)          # <short>_<cond>
  short=${name%_*}
  out=$H/aug_test/batch_out/$name; mkdir -p "$out"
  if [ -f "$out/output.mp4" ]; then echo "=== SKIP $name (exists) ==="; continue; fi
  echo "=== GEN $name @ $(date +%H:%M:%S) ==="
  singularity exec --nv -B $H:$H \
    --env PYTHONPATH=$H/cosmos-transfer1,HF_HOME=$H/hf_cache,PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    $H/cosmos_transfer1.sif \
    bash -c "cd $H/cosmos-transfer1 && torchrun --nproc_per_node=4 --nnodes=1 --node_rank=0 \
      cosmos_transfer1/diffusion/inference/transfer.py \
      --checkpoint_dir $H/cosmos-transfer1/checkpoints \
      --input_video_path $H/aug_test/batch_inputs/${short}_121.mp4 \
      --controlnet_specs $spec \
      --video_save_folder $out \
      --num_gpus 4 \
      --offload_text_encoder_model --offload_diffusion_transformer --disable_guardrail" \
    && echo ">>> DONE $name" || echo ">>> FAILED $name"
done
echo ">>> COSMOS BATCH ALL DONE @ $(date +%H:%M:%S)"
