#!/usr/bin/env bash
# build_env.sh — create the two pixi environments inside the hugsim-dev:cu118 container.
#
#   docker run --rm -v $H:$H -w $H -e FORCE_CUDA=1 hugsim-dev:cu118 bash build_env.sh
#
# HUGSIM's README installs in two passes: first everything except the packages under
# "# install from source code" (they build CUDA extensions with --no-build-isolation and
# need torch already present), then the full manifest. apex (only used by InverseForm, the
# data-prep segmenter) is left out; `pixi run install-apex` adds it when preprocessing is needed.
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd)

cd "$H/repo"
[ -f pixi.toml.orig ] || cp pixi.toml pixi.toml.orig
awk '/# install from source code/{f=1; print; next} f && NF {print "# " $0; next} {print}' pixi.toml.orig > pixi.toml
echo "[hugsim] pass 1: binary dependencies"; pixi install
cp pixi.toml.orig pixi.toml
echo "[hugsim] pass 2: source-built CUDA packages (gsplat, simple-knn, tiny-cuda-nn, pytorch3d, ...)"; pixi install
# tinycudann asks the GPU for its compute capability at import, so it is checked at run time
# (with --gpus), not here
pixi run python -c "import torch, gsplat, pytorch3d, simple_knn; print('hugsim env OK:', torch.__version__, torch.version.cuda)"

cd "$H/NAVSIM"
echo "[navsim] LTF client environment"; pixi install
pixi run python -c "import torch, navsim; print('navsim env OK:', torch.__version__)"
echo "BUILD DONE"
