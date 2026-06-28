#!/usr/bin/env bash
# Single-clip Cosmos-Transfer1 augmentation test: day->night, depth-controlled (geometry
# preserved). 4x A100-40GB context-parallel on pod09; text-encoder/guardrail offloaded
# to fit 40GB. Outputs to the /scratch bind (polled from login). Submit: sbatch this.
#SBATCH --job-name=cosmos-aug-test
#SBATCH --nodes=1
#SBATCH --gres=gpu:4
#SBATCH --nodelist=hpc-pr-a-pod09
#SBATCH --partition=jobs
#SBATCH --time=00:45:00
#SBATCH --output=/scratch/autodr_test/aug_test/slurm_%j.out
#SBATCH --error=/scratch/autodr_test/aug_test/slurm_%j.err
set -eo pipefail
H=/scratch/autodr_test
echo "[job] node=$(hostname)"; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1 || true
singularity exec --nv -B $H:$H \
  --env PYTHONPATH=$H/cosmos-transfer1,HF_HOME=$H/hf_cache \
  $H/cosmos_transfer1.sif \
  bash -c "cd $H/cosmos-transfer1 && torchrun --nproc_per_node=4 --nnodes=1 --node_rank=0 \
    cosmos_transfer1/diffusion/inference/transfer.py \
    --checkpoint_dir $H/cosmos-transfer1/checkpoints \
    --input_video_path $H/aug_test/inputs/02fd3a17.mp4 \
    --controlnet_specs $H/aug_test/night_depth_spec.json \
    --video_save_folder $H/aug_test/outputs \
    --num_gpus 4 \
    --offload_text_encoder_model --disable_guardrail"
echo ">>> COSMOS INFER DONE"
