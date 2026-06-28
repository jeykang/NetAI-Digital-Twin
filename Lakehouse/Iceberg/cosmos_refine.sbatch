#!/usr/bin/env bash
# Refinement matrix: generate all refine_specs/*.json variants for one clip in a single
# node allocation (sequential), to compare control/condition before batch scaling.
# One node only (pod17 reserved for the other project).
#SBATCH --job-name=cosmos-refine
#SBATCH --nodes=1
#SBATCH --gres=gpu:4
#SBATCH --nodelist=hpc-pr-a-pod09
#SBATCH --partition=jobs
#SBATCH --time=02:00:00
#SBATCH --output=/scratch/autodr_test/aug_test/refine_%j.out
#SBATCH --error=/scratch/autodr_test/aug_test/refine_%j.err
set -eo pipefail
H=/scratch/autodr_test
echo "[job] node=$(hostname)"
for spec in $H/aug_test/refine_specs/*.json; do
  name=$(basename "$spec" .json)
  out=$H/aug_test/refine_out/$name; mkdir -p "$out"
  echo "=== GENERATING $name @ $(date +%H:%M:%S) ==="
  singularity exec --nv -B $H:$H \
    --env PYTHONPATH=$H/cosmos-transfer1,HF_HOME=$H/hf_cache,PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    $H/cosmos_transfer1.sif \
    bash -c "cd $H/cosmos-transfer1 && torchrun --nproc_per_node=4 --nnodes=1 --node_rank=0 \
      cosmos_transfer1/diffusion/inference/transfer.py \
      --checkpoint_dir $H/cosmos-transfer1/checkpoints \
      --input_video_path $H/aug_test/inputs/02fd3a17_121.mp4 \
      --controlnet_specs $spec \
      --video_save_folder $out \
      --num_gpus 4 \
      --offload_text_encoder_model --offload_diffusion_transformer --disable_guardrail" \
    && echo ">>> DONE $name" || echo ">>> FAILED $name"
done
echo ">>> COSMOS REFINE ALL DONE"
