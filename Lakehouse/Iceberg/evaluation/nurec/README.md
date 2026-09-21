# nurec/ — NuRec reconstruction: NCore store → USDZ twin (the second hop)

Answers the professor's question from the Sep 16 call: can an existing dataset be
converted through NuRec into an AlpaSim-usable USD scene? Findings of 2026-09-21.

## What the pipeline is, verified against NVIDIA's own scene bundles

A NuRec USDZ's `data_info.json` names an **NCore `.zarr.itar` shard** as its input and its
`parsed_config.yaml` is the trainer config (`train_config_name:
configs/apps/prod/Hyperion-8.1/car2sim_6cam.yaml`, 6 cameras + 1 lidar, 40k steps). The
trainer is the same container AlpaSim already uses as its renderer —
`nvcr.io/nvidia/nre/nre-ga:26.04`, whose default command `main` is "Neural Reconstruction
Engine training, validation and testing", with `export-usdz-artifact` for the bundle.
NVIDIA documents the workflow at docs.nvidia.com/nurec (Prepare Data → Reconstruct an AV
Scene → Run Validation). So the chain is:

    on-disk clip → NCore v4 (ncore/, verified identical to NVIDIA's) → [nre-tools aux data]
        → nre-ga train → checkpoint → export-usdz-artifact → USDZ → AlpaSim LOCAL_USDZ_DIR

Two inputs beyond the NCore store:

| input | what | availability here |
|---|---|---|
| **Instant NuRec** initialisation (recommended by the docs) | github.com/NVIDIA/instant-nurec, Apache-2.0, native Python, weights auto-fetched from HF (`nvidia/instant-nurec`); feed-forward: our 6-camera clip → merged 144 MB PLY in minutes | **works here** (`instant_nurec/`, A10) |
| **NuRec auxiliary data** (`nre-tools-ga:26.04`) | semantic segmentation per camera (conditionally required), lidar segmentation + visibility (recommended), depth / DINOv2 (optional), metadata (required); written as `<store>.aux.<signal>.zarr.itar` | **blocked**: the container is on NGC and needs an `NGC_API_KEY` (free NGC account) to pull; not present on this host |

The production config's base (`_base_3dgut_dynamic_road_semantic`) asserts on the aux store
(`NCOREDataSource: aux data was not loaded`), which is exactly how attempt v1 failed.
Attempt v2 replaces the base with the plain `_base_3dgut_dynamic` (the same way the
codebase's own COLMAP path runs without aux) — `configs/car2sim_6cam_noaux.yaml`, bind-mounted
into the image's config tree — and trains.

## Hardware

Docs: >24 GB VRAM required, >48 GB recommended, A10 listed as supported. Ours is an A10
with 22.5 GiB usable; the Quadro RTX 6000 (Turing) cannot run the NuRec kernels. v2 runs
6 cameras + lidar at the prod settings (2 M Gaussians, fp32, batch sampler 4).

## Runs

| run | config | status |
|---|---|---|
| v1 `ac73935a_a10_instant_v1` | prod `car2sim_6cam.yaml`, `dataset.aux_data=false` | failed at data load: aux store required by the road-semantic base |
| v2 `ac73935a_a10_noaux_v2` | `configs/car2sim_6cam_noaux.yaml`, Instant NuRec init, `mode=trainval` | **trained 30k steps in 2 h 22 m (7.5 it/s alone, ~2.6 while sharing the A10 with the aux job), then crashed in the final checkpoint hook**: the ground-mesh export found 0 "ground-compatible" lidar points in every frame without the aux road labels and raised `ValueError` splitting road from non-road; no checkpoint was written. Lesson: `checkpoint.every_n_train_steps=10000` and `checkpoint.artifact.mesh.ground.enabled=false` on any run without aux (mesh post hoc with `export-ground-mesh`, or borrowed from NVIDIA's bundle in the hybrid) |
| aux `aux_<clip>/` | `nre-tools-ga:26.04 ncore-aux-data --segmentation-backend=mask2former --no-seg-logits --lidar-seg-camvis --store-meta`, six cameras + lidar | running on the A10 — the Turing card lacks the deformable-attention kernels (`no kernel image`) |
| v3 `ac73935a_a10_prod_v3` | prod `car2sim_6cam.yaml` with the aux store, Instant init, `checkpoint.artifact.nrend.enabled=true`, checkpoint every 10k steps, in-checkpoint mesh export off | queued behind aux (orchestrator 2), followed by v2b = the no-aux config with the same safety flags |

The NGC key that unlocked `nre-tools-ga` is the `COSMOS_API_KEY` in `.secrets/cosmos.env`
(an NGC personal key; `docker login nvcr.io -u '$oauthtoken'`). Two docs-vs-tool
mismatches found: the thread flag is `--num-threads`, and `--segmentation-backend`
takes `none|mask2former`, not `0|1`.

## The A/B, and the map-layer gap

Our export cannot contain `map.xodr` or `clipgt/*` (lane, road boundary, traffic
lights…): PAI ships no map labels; NVIDIA's bundles carry them from their own map
pipeline, and AlpaSim's off-road / lane metrics read them. `usdz_tools.py inject` copies
those members from NVIDIA's bundle of the same clip into ours, so the comparison is run
three ways per reconstruction (`alpasim/local_scenes_<v>_{ours,ours_map,nvidia}`):

| variant | neural scene | map layers | isolates |
|---|---|---|---|
| ours | ours | none | does AlpaSim load and drive a map-less twin at all |
| ours_map | ours | NVIDIA's | reconstruction quality, map held equal |
| nvidia | NVIDIA's | NVIDIA's | the reference |

Reference for the A/B: NVIDIA's own NuRec scene of the same clip,
`alpasim/local_scenes_ref_ac73935a…/fb47eeef….usdz` (26.04), fetched with
`materialize.py nurec --download`. The test that answers the question: run AlpaSim on our
USDZ through `LOCAL_USDZ_DIR` with the same policy as on NVIDIA's, compare per-clip
metrics; plus `metrics.yaml` `test/psnr` from the validation pass.

## Commands

```bash
# Instant NuRec (once): ./instant_nurec/setup.sh; then
CUDA_VISIBLE_DEVICES=1 instant_nurec/.venv/bin/python instant_nurec/run_inference.py \
    --ncore-path ../ncore/out/pai_<clip>/pai_<clip>.json --output-dir out/instant_<clip> --merge

# NRE training, no-aux variant (see scratch nre_train_v2.sh for the full invocation)
docker run --rm --gpus '"device=1"' --shm-size=64g \
  -v $PWD/../ncore/out/pai_<clip>:/workdir/dataset:ro -v $PWD/out:/workdir/output \
  -v <instant ply dir>:/workdir/instant_nurec:ro \
  -v $PWD/configs/car2sim_6cam_noaux.yaml:/app/internal/scripts/pycena/runtime/pycena_nrm_full.runfiles/_main/configs/apps/prod/Hyperion-8.1/car2sim_6cam_noaux.yaml:ro \
  nvcr.io/nvidia/nre/nre-ga:26.04 mode=trainval out_dir=/workdir/output \
  --config-name=configs/apps/prod/Hyperion-8.1/car2sim_6cam_noaux.yaml \
  dataset.path=/workdir/dataset/pai_<clip>.json dataset.lidar_ids=[lidar_top_360fov] \
  model/gaussians/initialization@model.layers.background.initialization=nrm_ply \
  model.layers.background.initialization.path=/workdir/instant_nurec/<clip>.ply \
  model.layers.background.initialization.num_point_cloud_points=2000000

# with an NGC key (full-quality path): docker pull nvcr.io/nvidia/nre/nre-tools-ga:26.04, generate
# the aux store per docs.nvidia.com/nurec/nurec/nurec-aux-data.html, then use car2sim_6cam.yaml
```

Gitignored: `instant_nurec/`, `out*/`.
