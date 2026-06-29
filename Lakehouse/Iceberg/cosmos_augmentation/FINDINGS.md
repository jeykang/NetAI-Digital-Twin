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

## Camera-only perceptual axis — built + analyzed (2026-06-27)
`planning/camera_perception_runner.py` (YOLO-2D front-cam, 33,767 clips) →
`.camera_perception/camera_perception.parquet`. `analyze_camera_perception.py`:
- vs lidar-fused (3,338 overlap): Spearman **0.739** (agree on real clips — clutter is
  hard for both), divergence (camera-hard/fused-easy) only **2.2%** → the real data is
  overwhelmingly **camera-easy**. That is the strongest case FOR augmentation: the
  camera-adverse cases the camera-only endgame needs barely exist → must be generated.
- Coverage: camera 33,767 vs fused 3,338 (10×).
- **Empty-scene confound:** 25% of clips have 0 camera detections; these have low agent
  load (conflict_rank 0.21 vs 0.59) → EMPTY, not hard. Raw `camera_low_conf` over-flags
  them. **Fix = agent-gating** (count camera difficulty only where obstacle.offline says
  agents are present): camera-hard 27.6%→**11.1%**, conflict_rank 0.22→0.35, OOD
  0.43→0.58, removes 5,218 false positives. This gated axis is the one to integrate.

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

## C VALIDATED END-TO-END (2026-06-28) — Cosmos augmentation works
Built Cosmos-Transfer1 SIF locally (apptainer fakeroot) → transferred to the A100
cluster (login node can't compile/pull images) → weights (113GB+gated 7B) → ran
depth-controlled day→night on an easy daytime clip (4× A100-40GB, pod09, guardrail
disabled, DiT offloaded, 121-frame segment, expandable_segments).
Result (cosmos_augmentation/cosmos_infer.sbatch + night_depth_spec.json):
- Photorealistic night render (streetlights, signals, headlights, wet-road reflections).
- Geometry + agent positions PRESERVED (depth control) → obstacle.offline labels + ego
  stay valid → labels transfer for free.
- HARDER for camera-only perception: YOLO day→night mean Δconf -0.22, Δndet -1.67
  (frame 90: 3 detections → 0). Confirms the augmented clip is genuinely harder for the
  camera-only endgame — the whole pipeline goal.
Pipeline: cluster.py (SSH/SFTP), cosmos_transfer1.def, cluster_download_weights.sh,
patch_transfer_guardrail.py, cosmos_infer.sbatch, night_depth_spec.json. Cluster: 1 node
at a time (pod09; pod17 reserved for user's other project). Per-clip ~7min on 4 GPUs.
Next: batch over easy Gold-adjacent clips (single node, sequential).

## C refinement (2026-06-28) — recipe chosen
Control x condition matrix on one clip (cosmos_refine.sbatch, single node). YOLO
difficulty vs day (frames 30/60/90):
  night_depth  Δconf -0.375  Δndet -0.67   (biggest confidence collapse)
  night_edge   Δconf -0.246  Δndet +0.33   (edge retains daytime -> weakest; magenta cast)
  rain_depth   Δconf -0.260  Δndet -1.33
  fog_depth    Δconf -0.183  Δndet -1.67   (most agents vanish)
  night_multi  FAILED (OOM — 3 controlnets on 40GB)
Verdict: **depth control** (lighting-invariant -> full relight + best geometry
preservation; edge clings to daytime + odd color). **Mix night/rain/fog** — different
failure modes (night=low conf, fog/rain=agents disappear) -> diverse hard augmentations.
Drop edge + multi. Open refinement: chunk full-length clips (only 121-frame tested);
optional prompt-upsampler. Recipe ready for batch (depth + mixed conditions, 1 node).

## Dual Gold scores (2026-06-29) — camera-only + lidar-fused, per user request
Rather than camera replacing fused, clip_scores now emits BOTH:
- difficulty_camera (this consumer's camera-only endgame) — materializes Gold views (default)
- difficulty_lidar (general-purpose lidar-fused stack) — derivable from clip_scores
Each = behavioral noisy-OR its modality's rank-normed perceptual axis; behavioral shared.
Full re-score (top 10% of 31,737): camera Gold 3,174 / lidar Gold 3,176; overlap 2,830,
~374 unique to EACH tier (Jaccard 0.79) — both add real value. `--gold-axis camera|lidar`
picks which materializes views. (Spark driver OOM on the dual write -> use --driver-memory 12g.)
