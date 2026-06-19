# BEVFusion multimodal perception scorer — separate container so the
# heavy ML stack stays out of spark-iceberg.
#
# Pretrained checkpoint expected at /workspace/checkpoints/bevfusion_lidar_voxel0075.pth
# (mounted from host or downloaded by entrypoint on first run).
#
# Communicates with the rest of the pipeline by writing per-clip perception
# scores to <NFS>/.perception/bevfusion_shard_NN.parquet — same convention as
# the existing camera_perception_scorer.py.
FROM pytorch/pytorch:2.1.2-cuda12.1-cudnn8-devel

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    TORCH_CUDA_ARCH_LIST="7.5;8.6" \
    CUDA_HOME=/usr/local/cuda

# 7.5 = Quadro RTX 6000 (Turing); 8.6 = A10 (Ampere). Restricting arches
# saves >30 min on mmcv compile vs the all-arch default.

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libsm6 libxext6 libgl1 libglib2.0-0 \
        git wget ca-certificates build-essential ninja-build \
        cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# OpenMMLab toolchain compatible with mmdet3d 1.4.x + BEVFusion config.
# Pin versions: mismatches between mmcv / mmdet / mmdet3d are the most
# common install failure mode.
RUN pip install --no-cache-dir \
        openmim==0.3.9 \
    && mim install --no-cache-dir \
        "mmengine==0.10.4" \
        "mmcv==2.1.0" \
        "mmdet==3.2.0" \
        "mmsegmentation==1.2.2" \
        "mmdet3d==1.4.0"

# Project deps for the scorer
RUN pip install --no-cache-dir \
        DracoPy==1.4.0 \
        pyarrow==15.0.2 \
        pandas==2.2.2 \
        opencv-python-headless==4.10.0.84 \
        scipy==1.13.1 \
        tqdm==4.66.4

# BEVFusion lives in projects/BEVFusion/ inside the mmdetection3d *source*
# repo, not in the pip-installed package. Clone the source at the matching
# version tag and add projects/ to PYTHONPATH so configs resolve.
RUN git clone --depth 1 --branch v1.4.0 \
        https://github.com/open-mmlab/mmdetection3d.git /workspace/mmdetection3d \
    && cd /workspace/mmdetection3d \
    && pip install --no-cache-dir -v -e . \
        || (echo 'editable install failed; runner can still import from projects path' && true)

# mmdet3d's editable install pulls numpy 2.x via setup.py; re-pin to 1.26.x
# because mmcv 2.1.0 / matplotlib / pyarrow prebuilt wheels target numpy 1.x ABI.
# numpy 2.x triggers `_ARRAY_API not found` at matplotlib import.
RUN pip install --no-cache-dir --force-reinstall "numpy==1.26.4"

# Compile BEVFusion's custom CUDA ops (bev_pool, voxelization). Runs nvcc
# at build time. No GPU needed for compile, only at runtime. setup.py uses
# paths relative to the mmdet3d repo root, so cwd must be the repo root,
# not the projects/BEVFusion subdir.
#
# CUDA_HOME must be set inline because the ENV-level value isn't reliably
# picked up by torch.utils.cpp_extension when invoked through setup.py.
# Also export CPATH so g++ finds cuda_runtime_api.h during the .cpp pass
# (nvcc's automatic include resolution doesn't propagate to gcc).
#
# FORCE_CUDA=1 is REQUIRED: projects/BEVFusion/setup.py gates CUDAExtension on
# `torch.cuda.is_available() or FORCE_CUDA==1`. There is no GPU during `docker
# build`, so without FORCE_CUDA the ops compile as CPU-only CppExtensions and
# voxelization raises "Not compiled with GPU support" at inference time.
RUN export CUDA_HOME=/usr/local/cuda \
    && export PATH=$CUDA_HOME/bin:$PATH \
    && export LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH \
    && export CPATH=$CUDA_HOME/include:$CPATH \
    && export FORCE_CUDA=1 \
    && cd /workspace/mmdetection3d \
    && python projects/BEVFusion/setup.py develop

ENV PYTHONPATH=/workspace/mmdetection3d:/workspace/mmdetection3d/projects/BEVFusion

COPY bevfusion_infer.py /workspace/bevfusion_infer.py
COPY runner.py /workspace/runner.py
COPY test_one_clip.py /workspace/test_one_clip.py
COPY validate_sampling.py /workspace/validate_sampling.py

# Default invocation: print help so a misconfigured run fails loud
CMD ["python", "/workspace/runner.py", "--help"]
