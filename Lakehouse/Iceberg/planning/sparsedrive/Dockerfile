# Rung-1 driving-difficulty: SparseDrive end-to-end planner.
#
# Separate (older) image from bevfusion — SparseDrive pins py3.8 / torch1.13+cu116
# / mmcv-full 1.7.1 / mmdet 2.28.2, incompatible with the BEVFusion stack
# (torch2.1/mmcv2.1). Kept under planning/ so the whole driving-difficulty
# module stays detachable (MEDALLION_PROGRESS.md §13).
#
# Build:  docker build -t netai/sparsedrive-runner:latest planning/sparsedrive
FROM pytorch/pytorch:1.13.0-cuda11.6-cudnn8-devel

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    TORCH_CUDA_ARCH_LIST="7.5;8.6" \
    CUDA_HOME=/usr/local/cuda \
    FORCE_CUDA=1
# 7.5 = Quadro RTX 6000 (Turing); 8.6 = A10 (Ampere).

RUN apt-get update && apt-get install -y --no-install-recommends \
        git wget ca-certificates build-essential ninja-build \
        ffmpeg libsm6 libxext6 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
RUN git clone --depth 1 https://github.com/swc-17/SparseDrive.git /workspace/SparseDrive
WORKDIR /workspace/SparseDrive

# numpy first (pinned ABI), then the OpenMMLab stack from the cu116/torch1.13 wheels.
RUN pip install --no-cache-dir numpy==1.23.5
RUN pip install --no-cache-dir mmcv-full==1.7.1 \
        -f https://download.openmmlab.com/mmcv/dist/cu116/torch1.13/index.html \
    && pip install --no-cache-dir mmdet==2.28.2

# Project deps (requirement.txt minus torch/mmcv/mmdet which are handled above),
# plus pyarrow/DracoPy for reading PhysicalAI parquet/lidar in the inference adapter.
RUN pip install --no-cache-dir \
        pyquaternion==0.9.9 nuscenes-devkit==1.1.10 yapf==0.33.0 \
        motmetrics==1.1.3 pandas==1.1.5 opencv-python==4.8.1.78 \
        prettytable==3.7.0 scikit-learn==1.3.0 urllib3==1.26.16 \
        tensorboard==2.14.0 pyarrow==13.0.0 DracoPy==1.4.0

# flash-attn: heavy source build; cap parallel jobs so nvcc doesn't OOM the host.
RUN MAX_JOBS=4 pip install --no-cache-dir flash-attn==2.3.2 \
    || (echo 'WARNING: flash-attn build failed — model load may need a fallback' && true)

# Custom CUDA ops (deformable aggregation). FORCE_CUDA=1 (no GPU at build time).
RUN cd projects/mmdet3d_plugin/ops && python setup.py develop

# Pretrained: ResNet50 img-backbone init + SparseDrive stage-2 (full planning) checkpoint.
RUN mkdir -p ckpt \
    && wget -q https://download.pytorch.org/models/resnet50-19c8e357.pth \
         -O ckpt/resnet50-19c8e357.pth \
    && wget -q https://github.com/swc-17/SparseDrive/releases/download/v1.0/sparsedrive_stage2.pth \
         -O ckpt/sparsedrive_stage2.pth

# Re-pin numpy LAST: flash-attn / later deps drag in numpy 2.x, which breaks the
# numpy-1.x C-extensions in cv2 / mmcv ("numpy.core.multiarray failed to import").
# The compiled torch ops + flash-attn don't link numpy, so downgrading after the
# fact is safe (same pattern as the BEVFusion image).
RUN pip install --no-cache-dir --force-reinstall "numpy==1.23.5"

# The config loads data/kmeans/*.npy anchors at build time (normally generated
# from nuScenes). Dump them from the checkpoint buffers instead — no nuScenes.
COPY extract_anchors.py /workspace/SparseDrive/extract_anchors.py
RUN python extract_anchors.py

ENV PYTHONPATH=/workspace/SparseDrive
CMD ["python", "-c", "import torch; print('sparsedrive-runner', torch.__version__, torch.version.cuda)"]
