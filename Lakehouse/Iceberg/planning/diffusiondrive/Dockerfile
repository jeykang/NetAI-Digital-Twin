# Rung-1 (attempt 2): DiffusionDrive — NAVSIM/Transfuser lidar-BEV + front-cam
# planner with a diffusion head (multimodal trajectories). Chosen after
# SparseDrive failed to transfer (camera-appearance domain shift): this consumes
# a lidar BEV raster (domain-invariant geometry) + a stitched forward image, so
# it should transfer far better to PhysicalAI. See MEDALLION_PROGRESS.md §13.
#
# Cleaner stack than SparseDrive: torch 2.0.1, no mmcv/mmdet/flash-attn, no
# custom CUDA ops -> also runs on the RTX 6000 (no Ampere-only flash-attn).
#
# Build: docker build -t netai/diffusiondrive-runner:latest planning/diffusiondrive
FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-devel

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 \
    CUDA_HOME=/usr/local/cuda

RUN apt-get update && apt-get install -y --no-install-recommends \
        git wget ca-certificates build-essential \
        ffmpeg libsm6 libxext6 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
RUN git clone --depth 1 https://github.com/hustvl/DiffusionDrive.git /workspace/DiffusionDrive
WORKDIR /workspace/DiffusionDrive

# Install NAVSIM deps WITHOUT clobbering the base CUDA torch: drop torch/
# torchvision/triton pins from requirements (base image already has 2.0.1+cu117).
RUN grep -ivE '^torch==|^torchvision==|^triton' requirements.txt > /tmp/req.txt \
    && pip install --no-cache-dir -r /tmp/req.txt
RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir einops pyarrow==13.0.0 DracoPy==1.4.0

# Pretrained: the NAVSIM (lidar-BEV + front-cam) checkpoint — NOT the nusc one
# (that's the 6-camera VAD build with the same transfer problem we just hit).
RUN mkdir -p ckpt \
    && wget -q "https://huggingface.co/hustvl/DiffusionDrive/resolve/main/diffusiondrive_navsim_88p1_PDMS" \
         -O ckpt/diffusiondrive_navsim_88p1.pth

# nuplan-devkit / navsim drag in numpy 2.x; re-pin to the NAVSIM-tested 1.23.4.
RUN pip install --no-cache-dir --force-reinstall "numpy==1.23.4"

# diffusers (for the diffusion head) LAST, with a compatible huggingface_hub:
# newer diffusers reference torch.xpu (torch>=2.4); diffusers 0.27.2 imports
# `cached_download`, removed from huggingface_hub>=0.26 — so pin both.
RUN pip install --no-cache-dir "diffusers==0.27.2" "huggingface_hub==0.23.4"

COPY test_one_clip.py /workspace/DiffusionDrive/test_one_clip.py
COPY gate_test.py /workspace/DiffusionDrive/gate_test.py
COPY runner.py /workspace/DiffusionDrive/runner.py

ENV PYTHONPATH=/workspace/DiffusionDrive
CMD ["python", "-c", "import torch; print('diffusiondrive-runner', torch.__version__, torch.version.cuda)"]
