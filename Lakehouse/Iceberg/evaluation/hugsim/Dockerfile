# Build/run image for the HUGSIM test (see README.md).
# HUGSIM pins PyTorch 2.4.1+cu118 and compiles CUDA extensions (gsplat, tiny-cuda-nn,
# pytorch3d, simple-knn) against it, which needs nvcc 11.x and GCC <= 11. The host has
# neither (Ubuntu 24.04, GCC 12/13, no CUDA toolkit), so both the build and the runs happen
# here. The pixi environments live in the mounted evaluation/hugsim/ tree, mounted at the
# same absolute path so their baked-in prefixes stay valid.
FROM nvidia/cuda:11.8.0-devel-ubuntu22.04

ARG UID=1000
ARG GID=1000
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        git git-lfs zsh curl ca-certificates wget unzip build-essential ninja-build \
        libgl1 libglib2.0-0 libgomp1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://pixi.sh/install.sh | PIXI_HOME=/opt/pixi PIXI_NO_PATH_UPDATE=1 sh \
    && ln -s /opt/pixi/bin/pixi /usr/local/bin/pixi
RUN groupadd -g ${GID} netai && useradd -m -u ${UID} -g ${GID} -s /bin/zsh netai

# the A10 (sm_86) is the only card HUGSIM runs on here
ENV CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST="8.6" TCNN_CUDA_ARCHITECTURES=86 MAX_JOBS=8
USER netai
