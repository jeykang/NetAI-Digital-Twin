# Cosmos / difficulty-augmentation — feasibility findings (2026-06-27)

Goal: use Gold difficulty scores to generate variants of *easy* clips matching
*hard* criteria (detachable augmentation module).

## Compute feasibility — Cosmos is cluster-only
- **No hosted generation API.** Key authenticates (200, 121 models) but only
  `cosmos-reason2-8b` (reasoning VLM) is served; `cosmos-transfer*/predict*` all
  404 on `integrate.api.nvidia.com`. build.nvidia.com offers Transfer as
  "Download and Post-Train" only — generation is download/self-host.
- **Local infeasible.** Cosmos-Transfer1-7B needs ~80 GB VRAM (~39 GB with
  aggressive offload) ≫ the 24 GB local cards. (x86 was a red herring — it's VRAM.)
- → Any Cosmos-Transfer generation requires the A100 cluster (SLURM + Singularity).

## Cheap prototype (validated the GENERATION side, no Cosmos/cluster)
`transforms.py` (classical night/rain/fog, same frames-in/out contract Cosmos would
have, geometry preserved) + `cheap_validate.py`. Produces measurable perceptual
degradation: night −85% brightness / −70% contrast; rain/fog −50% / −66%
contrast & edges. Composites at /tmp/aug_samples (crude but recognizable).

## The decisive negative finding — perceptual augmentation does NOT register
`bevfusion/augment_rescore_test.py`: ran BEVFusion on 6 clips, original camera vs
night-degraded camera, **lidar unchanged** (exactly what a Cosmos camera transform
does). Result: **5/6 clips Δconf ≈ 0** (−0.006..+0.003); mean +0.055 only because
one clip spuriously gained a detection. **Camera degradation does not lower the
fused BEVFusion confidence** — clean lidar dominates and masks it.

Implication: our perceptual difficulty axis (and a lidar-fused AV stack generally)
is **night/weather-robust because of lidar**. So generating night/rain/fog variants
of easy clips would NOT make them measurably harder for this scorer/stack — the
perceptual-augmentation premise breaks for the lidar-fused setting. (Behavioral
augmentation — inserting agents — was separately judged hard-to-synthesize +
label-generating, shelved.)

## When augmentation WOULD be worth it
If the downstream consumer is a **camera-only / camera-heavy** model, night/weather
genuinely degrades it → perceptual augmentation is valuable, paired with a
**camera-only difficulty axis** (not the fused one). Value is contingent on the
downstream model's modality, which isn't pinned down.

## Recommendation
Do NOT commit the Cosmos/cluster effort for the current lidar-fused setting; the
cheap probe shows the variants wouldn't be harder. Architecture is ready if revisited
(swap `transforms.py` → Cosmos backend behind the same interface; Cosmos-Evaluator as
realness gate; difficulty scorer as targeting/verification) — but only once there's a
camera-only downstream need to justify it.
