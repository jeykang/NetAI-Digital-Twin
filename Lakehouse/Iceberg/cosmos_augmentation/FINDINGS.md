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

## Modality decides everything — measured both ways
Same night transform, two perception yardsticks:

| condition | lidar-fused BEVFusion Δconf | camera-only YOLO Δconf | cam-only Δndet |
|-----------|----------------------------|------------------------|----------------|
| night     | ≈0 (+0.001, 5/6 clips ~0)  | **−0.427**             | −2.12          |
| rain      | —                          | **−0.218**             | −1.00          |
| fog       | —                          | −0.046                 | −0.62          |

- `bevfusion/augment_rescore_test.py` (fused): camera degradation does NOT lower
  confidence — **clean lidar masks it**; a lidar-fused stack is night/weather-robust.
  (Suppressing lidar doesn't make BEVFusion a camera-only proxy — it collapses to 0
  detections; it's intrinsically fused.)
- `cosmos_augmentation/camera_only_probe.py` (YOLO, camera-only): night **collapses**
  perception (most clips lose all detections, conf→0); rain strong, fog mild.

## Consumer is camera-only → augmentation is RESCUED
Confirmed (2026-06-27): the downstream consumer's stack is currently lidar-assisted
but its **final product is camera-only** (for scalability). So:
1. **Perceptual augmentation is valuable** — night/rain variants of easy clips are
   genuinely much harder for the camera-only model (−0.43 conf on night). Cosmos
   camera transforms target exactly this.
2. **The difficulty scorer's perceptual axis must be camera-only**, not lidar-fused.
   The current fused axis is *blind* to the difficulty the final product will face —
   it under-rates the very clips that matter. Re-point it to a camera-only detector
   (YOLO-2D now; camera-3D — fcos3d/pgd, in the image — for closer 3D alignment).

## Recommendation (updated)
PURSUE it. Next steps:
1. Re-point the perceptual difficulty axis to **camera-only** perception — run a
   camera detector on the cohort → `camera_low_conf` axis → fold into the union
   (behavioral axis is modality-agnostic, stays).
2. With a camera-only difficulty signal, the augmentation loop is coherent
   (Cosmos camera transform → camera-only re-score confirms harder → keep) and the
   A100-cluster Cosmos effort is justified for the camera-only endgame.
3. Architecture unchanged: swap `transforms.py` → Cosmos backend behind the same
   interface; Cosmos-Evaluator as realness gate; difficulty scorer as targeting.
