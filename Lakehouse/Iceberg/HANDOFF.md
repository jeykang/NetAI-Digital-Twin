# HANDOFF — read this first, update it last

**Owner:** jeykang · **Last session:** 2026-09-21 · **Scope:** `Lakehouse/Iceberg` (the AV
data lakehouse + validation ground). A future session should be able to continue from
here without re-reading the repo. Rules: (1) read §1–§4 before touching anything;
(2) at the end of every session, update §3 (workstream state), §5 (running jobs) and
append a dated entry to §9; (3) numbers go in §6 only once they are in a repo doc.

Vocabulary is fixed by `TERMINOLOGY.md` (evaluator, not harness; driving policy and actors, not agent; rollout triage; serving mode) — follow it in every edit.

Companion documents, in reading order: this file → the plan
([Lakehouse Direction & Development Plan](https://claude.ai/code/artifact/37c9ee55-5bba-4884-a7b6-4fe398bc2fd8),
the professor's direction and the 7 workstreams) → `evaluation/FEASIBILITY.md`,
`evaluation/ALPASIM.md`, `evaluation/SKIP.md`, `evaluation/ncore/README.md`,
`nvidia_ingestion/STORAGE_SIZING.md` (results) → `ARCHITECTURE_2026-06.md`,
`nvidia_ingestion/MEDALLION_PROGRESS.md`, `PAPER_REFERENCE_SC26.md` (the lakehouse and
the curation work up to June; not repeated here). `nvidia_ingestion/HANDOFF.md` is the
older April handoff for the Cosmos pipeline only.

---

## 1. What this project is, in one paragraph

A medallion lakehouse (Iceberg + Polaris + MinIO + Spark) over a 13.5 TB on-disk slice
(32,651 clips) of NVIDIA PhysicalAI-AV, whose Gold tier is a validated edge-case
selection (3,176 clips; `nvidia_ingestion/`), plus a **validation ground** on top of it
(`evaluation/`): an open-loop evaluator (MF-PDMS, any dataset with tracks + ego poses),
a closed-loop layer (AlpaSim over NuRec scenes), and — since 2026-09-21 — a
budget-screen (`skip.py`), an explicit scenario × episode space (Iceberg tables), a
storage-sizing model, and a serving layer that materialises Gold in a validator's
format (`materialize.py`: open-loop list, NuRec directory, NCore v4).

**The professor's direction (Aug–Sep 2026 calls, see memory `professor-direction-
validation-ground`):** we run the 검증장 — validate faster, cheaper, more selectively —
not model-hunting; move toward closed-loop / the OpenUSD twin; curate in
serving modes (호환 모드); tool-ify the skip logic (rollout triage); size 축적 (accumulation) vs 진열
(serving) storage separately. Journal submission of the SC26 workshop paper by
2026-12-31. Paper-level fixes (self-critique, positioning, terminology, figure) are
listed in the plan doc and were **out of scope** for the 09-21 session.

## 2. Environment (verify with the commands, do not assume)

| item | state at handoff | how to check / restore |
|---|---|---|
| host GPUs | **A10 23 GB** (Ampere, sm_86; the only BF16/NuRec-capable card; nvidia-smi index 1) and **Quadro RTX 6000 24 GB** (Turing; fine for NVDEC decode and YOLO, not for BF16 models). torch may order them differently from nvidia-smi | `nvidia-smi`; AlpaSim pins GPU 1 in `evaluation/alpasim/run_scene.sh`; NCore conversion uses `CUDA_VISIBLE_DEVICES=0` |
| disk | root volume 437 GB, ~50 GB free. Big reclaimables: `evaluation/alpasim/repo/data/nre-artifacts` **128 GB** (81 NuRec scenes, re-downloadable in minutes), `evaluation/ncore/{reference,out}` 6.3 GB | `df -h /`; `du -sh` those dirs. Never delete `runs/` (results) |
| NFS data | `10.38.36.222:/exports/test/shared/netai-e2e` mounted at `/mnt/netai-e2e` and bind-mounted onto `./netai-e2e`; needs group GID 1007 (`netaie2e`); **drops on reboot** | `./mount_netai_e2e.sh --status` / `./mount_netai_e2e.sh`. The old `.221` server is dead. Score shards live under `netai-e2e/nvidia-physicalai-av-subset/.<name>/` |
| docker stack | `polaris`, `polaris_postgres`, `minio`, `spark-iceberg`, `superset*`, `demo-wall` up for months; **trino not running**; `spark-iceberg` holds a **stale NFS handle** (restart it before any job that reads `/mnt/netai-e2e` inside the container; the episode job reads `/user_data` only) | `docker ps`; `docker restart spark-iceberg` |
| Spark jobs | run inside the container: `docker exec -w /opt/spark spark-iceberg /opt/spark/bin/spark-submit nvidia_ingestion/<script>.py` (repo dirs `nvidia_ingestion`, `kaist_ingestion`, `cosmos_augmentation`, `user_data` are bind-mounted; `evaluation/` is **not**) | catalog `iceberg`, namespaces `nvidia_bronze/silver/gold`; config from container env |
| **DGX Spark** (`10.32.229.127`, ssh creds in `.secrets/spark.env` as `SPARK_SSH_ID/PW`; helper pattern: `sshpass -e ssh`) | aarch64 Ubuntu 24.04, GB10 (sm_12.1), 121 GB unified memory, NVMe 3.6 TB (~300 GB free), driver 580, CUDA 13, Docker + CDI, `nvcr.io` login present, user in groups 1007/1010, `nfs-common` installed, NFS server and this host reachable over TCP. **It is the user's desktop** (LM Studio, browser, `dockge`) — ask before sudo, big pulls or long GPU runs. Set up under `~/netai-lakehouse/`: `.venv` (torch cu130 + NCore converter deps), `ncore/`, `cosmos-transfer2.5/` (build in progress), `x86_reference/`. x86-only and therefore *not* offloadable: `nre-ga`, `nre-tools-ga`, the AlpaSim stack. Offloadable: NCore conversion (verified identical), curation axes, open-loop evaluation incl. the large VLA policies, Cosmos-Transfer**2.5** (official ARM+Blackwell support; Transfer1 is x86-only) | `evaluation/ncore/README.md` |
| GPU clusters | A100 SLURM cluster **revoked 2026-09-11**; lab has two L40S (one on a project, one due back, date unknown); data-bahn L40 node reachable via K8s (`deploy/k8s/40-eval.yaml`, namespace `netai-l40-test`, 1 GPU/pod) | memory `a100-cluster-access`, `datax-partridge-l40-contract` |
| HuggingFace | token at `~/.cache/huggingface/token`; access to `nvidia/PhysicalAI-Autonomous-Vehicles` (main), `-NuRec` (gated) and, since 2026-09-21, `-NCore` (gated) | `huggingface_hub.HfApi(token).list_repo_files(...)` |
| python envs | host `python3` = miniconda 3.13 **without pandas**. `evaluation/.skip_venv` (numpy/pandas/scipy/sklearn/matplotlib/pyarrow), `evaluation/ncore/.venv` (NVIDIA converter deps, `zarr<3`), `evaluation/alpasim/repo/.venv` (uv: polars, pandas, scipy, huggingface_hub), `planning/cosmos3_reason/c3_venv` (ultralytics + torch 2.13 cu130), `planning/alpamayo/alpamayo1.5/a1_5_venv` (Alpamayo + ultralytics) | all gitignored; recreate with `uv` (`~/.local/bin/uv`) |
| session gotchas | the Bash tool's cwd moves to wherever the last command ended → **use absolute paths**; `pkill -f <pattern>` kills your own shell if the pattern is in the command line → build the pattern from a split string (`"episo""des.py"`); LOO fits in `skip.py` take minutes → run in background | — |

## 3. Workstream state (plan doc numbering)

| WS | state | evidence | next action |
|---|---|---|---|
| WS0 self-critique & positioning | **not started** (paper work, out of scope 09-21) | plan doc §3 | the August homework; prerequisite for the journal draft |
| WS1 local USDZ loading | **closed** — `LOCAL_USDZ_DIR=` reproduces catalog-path metrics identically on all 16 columns | `evaluation/FEASIBILITY.md` risk 1, `evaluation/alpasim/README.md`, `runs/ws1-local-cv` | none |
| WS2 rollout triage (가성비) | tool built; n=80 closed-loop VaVAM; ladder-only screen AUC 0.657, recall 0.66 @50% budget | `evaluation/SKIP.md`, `skip.py`, `.skip_features.parquet`, `.cl_vavam_perclip.parquet`, `ALPASIM.md` batch 3 | batch 4 (63 unlabelled clips; `.skip_next_rollouts.txt` = the dial's 32) — mind disk; per-decision features; a second policy (Alpamayo-1.5 closed-loop needs an L40S) |
| WS3 scenario × episode | **landed for the whole on-disk set**: `nvidia_gold.episode` 189,626 rows (187,212 decision windows over 31,202 clips, 2,364 NuRec scenes, 50 Cosmos windows), `nvidia_gold.scenario` 16 rows (3 recorded conditions × 3 serving modes + 9 augmentation classes); slice run superseded | `evaluation/episodes.py`, `nvidia_ingestion/build_episode_tables.py`, `user_data/episodes_{ondisk,nurec_slice}.parquet` | key `eval.policy_runs` rows by episode_id; a figure of the combination space; rename `validator_mode` → `serving_mode` at the next rebuild |
| WS4 storage sizing | model + report written; both placeholder constants now have a measurement: NuRec reconstruction 2 h 05 m per scene on the A10 (v3), a 4 s single-camera Cosmos-Transfer2.5 window 4.0 MB / 90 GB10-min on the Spark | `nvidia_ingestion/storage_sizing.py` → `STORAGE_SIZING.md` ("Measured constants" section) | L40S timing when a cluster returns; six-camera full-clip variant size if the Spark ever renders one (~7.5 h per condition) |
| WS5 serving modes | **closed-loop twin works**: v3 (prod config + aux store, 30k steps on the A10, PSNR 29.53 dB) **drives in AlpaSim** once re-based with `evaluation/nurec/alpasim_bundle.sh` (our export is clip-relative; AlpaSim needs an absolute axis with ≥ 0.5 s of history before the scene start and uint64 track times — JSON/USDA/metadata *and* four checkpoint fields move together, nothing dropped); `v3_ours_map` (our scene + NVIDIA's map layers) matches the NVIDIA reference to the step under the constant-velocity policy, traffic light turns green at the same step; map-less `v3_ours` **drives** with `route_generator_type=RECORDED` (39 steps rendered, same collision) but cannot be scored — off-road/lane metrics need the map, scene score refused; `materialize.py` (openloop / nurec / ncore) working; NCore conversion identical to NVIDIA's release | `evaluation/nurec/README.md` ("time base" + results), `nurec/alpasim_bundle.sh`, `nurec/shift_checkpoint.py`, `nurec/usdz_tools.py`, `evaluation/ncore/README.md` | v2b (no-aux) A/B from orchestrator 6; fold `alpasim_bundle.sh` into `materialize.py nurec` for our own scenes; the map-layer gap (PAI ships no map labels → no `map.xodr`, so off-road / lane metrics need NVIDIA's layers or a map source of our own) is the blocker for non-NVIDIA clips |
| WS6 figure & journal draft | not started (paper work) | plan doc | needs the professor's figure source and reference doc (open questions, §7) |

## 4. Map of the repo (only what a session needs to navigate)

| path | what | notes |
|---|---|---|
| `evaluation/harness.py, scenario.py, adapters.py, metrics.py, policies.py, run_eval.py` | open-loop evaluator (MF-PDMS), dataset adapter contract, reference ladder | `adapters.NvidiaAdapter.list_clips()` caches `.clip_list.json` — delete it if the dataset changes; it once held a stale 12-clip list |
| `evaluation/policy_*.py` | Alpamayo / VaVAM / DiffusionDrive through the `Policy` contract | Alpamayo needs 23 GB VRAM, workers=1 |
| `evaluation/alpasim/` | closed-loop layer: `run_scene.sh` (catalog ids or `LOCAL_USDZ_DIR`), policy bridge (`driver=harness`), `per_clip.py`, `runs/` | `repo/` is an unmodified AlpaSim checkout; scene cache in `repo/data/nre-artifacts` |
| `evaluation/skip.py` | budget screen: `features` / `fit` / `select` | `.skip_venv` |
| `evaluation/episodes.py` | scenario × episode rows → `user_data/` | slice roots need `--clips-file` |
| `evaluation/materialize.py` | serve a Gold selection in a mode | writes `manifest.json` |
| `evaluation/ncore/` | NCore v4 mode: `stage_pai_clip.py`, `validate_ncore.py`, `compare_ncore.py`, vendored `repo/` (NVIDIA/ncore, Apache-2.0) | run the converter with `PYTHONPATH=repo .venv/bin/python -m tools.data_converter.pai.converter` |
| `evaluation/.av_slice_nurec/` | the 143-clip NuRec slice (labels + front camera) **plus its own `.conflict/ .behavioral/ .camera_perception/` scores** | these clips are *not* in the on-disk subset; runners scored them with `NFS_ROOT=` |
| `planning/` | curation-axis runners (conflict, behavioral, camera-perception; `NFS_ROOT` override), shelved planners, cosmos3 (closed, not adopted) | |
| `nvidia_ingestion/` | medallion pipeline, Gold scorer, validity battery, scalability reports, `storage_sizing.py`, `build_episode_tables.py` | June state documented in `MEDALLION_PROGRESS.md` |
| `cosmos_augmentation/` | Cosmos-Transfer augmentation (A100-only), `batch_manifest.json` = the 50 augmented windows | cluster revoked |
| `deploy/` | Helm chart, K8s manifests incl. the L40 eval job | |
| `user_data/` | gitignored exchange dir, mounted in the Spark container at `/user_data` | episode parquet files live here |

## 5. Background jobs at handoff (check before starting new GPU/NFS work)

| job | how to check | if dead |
|---|---|---|
| ~~NuRec reconstruction v2~~ | finished training 07:04 but crashed in the final checkpoint hook (ground-mesh export without aux road labels); no checkpoint — see `evaluation/nurec/README.md` | superseded by v3 and v2b in orchestrator 2 |
| ~~NuRec aux data~~ | finished; `evaluation/nurec/aux_ac73935a…/*.aux.*.zarr.itar` (a copy sits beside `ncore/out/pai_<clip>/`), consumed by v3 | relaunch per README (six `--camera-id`, `--segmentation-backend=mask2former`) |
| ~~orchestrator 6~~ — finished 13:23 UTC: v3 and v2b A/Bs done (`alpasim/runs/{v3,v2b}_{ours,ours_map,nvidia}`) | — | — |
| ~~step 1 / 1b~~ (`orchestrate7.sh`, `orchestrate7b.sh`) — done 15:02 UTC: VaVAM with map routes fails on all three bundles incl. NVIDIA's (route fold-back); with `route_generator_type=RECORDED` both twins run (`runs/v3_{ours_map,nvidia}_vavam_rec`); `eval.scene_score.enabled=false` scores a map-less twin (`runs/v3_ours_noscore`) | — | — |
| **step 2: twin queue** (`orchestrate8c.sh`, relaunched 15:2x UTC after the first pass failed at conversion — the empty `camera_rear_tele_30fov` copies had to be marked absent in the staged `feature_presence.parquet`, now done by `stage_pai_clip.py --allow-empty`; runs `evaluation/nurec/twin_pipeline.sh <clip>` for the 8 clips in the session scratch `twin_queue.txt`: bb4394e7 ba91fe2c a07e81de 0ec48454 a2bd8a78 abd45a30 44c3b4d5 e848c843 — on-disk ∩ HF NuRec 26.04 with all six cameras intact, 4 day / 4 night, chosen by NVIDIA's `clip_ratings_26.04.csv`; ~4.7 h each on the A10, so ~38 h for the queue) | `ps -eo args \| grep orchestrate8c`; log `orchestrate8c.log` in the scratch dir; `nurec/out/<short>.twin.json` (per-step timings/status), `nurec/out/<short>_a10_prod.log`, `alpasim/runs/<short>_{ours_map,nvidia}_{cv,vavam}/per_clip.parquet` | `twin_pipeline.sh <clip>` is idempotent per step — rerun it for the clip; disk: ~5 GB kept per twin after cleanup, 79 GB were free at launch; **bb4394e7 done 20:42 UTC** (PSNR 32.57, cv A/B agrees; its VaVAM launches failed on Docker network-pool exhaustion → `docker network prune` added to `run_scene.sh`, and `orchestrate9.sh` re-runs the now-idempotent pipeline per clip after `QUEUE DONE` to fill missing rollouts); **ba91fe2c aborted 23:36 UTC** after its aux step — not the pipeline's fault: `twin_pipeline.sh` was patched in place while that instance was running (bash reads incrementally); its aux store was recovered beside the NCore store, Instant PLY intact, so the fill pass (`orchestrate9.sh`) resumes it at training. Rule: never edit a running script in place (patch to a temp file and `mv`) |

| ~~DGX Spark: Cosmos-Transfer2.5~~ — **done**: smoke test passed (49 min) and our night clip rendered (90 min wall on the GB10; hallucination gate passed at the tolerance edge, not "harder" — `cosmos_augmentation/FINDINGS.md`); outputs in `~/netai-lakehouse/aug/out_2daf9698_night/` on the Spark, copies in the session scratch `gate/` | ssh: `ls ~/netai-lakehouse/aug/out_2daf9698_night` | nothing running; `cosmos_ours.sh` pattern for another spec (`aug/<clip>_<cond>_spec.json`) |

The episode pass and Spark landing finished 02:48–02:49 (§3 WS3). ("Spark" in that sentence is Apache Spark.)

Scratch logs from the 09-21 session live under `/tmp/claude-1000/-home-netai-jeykang-NetAI-Digital-Twin-Lakehouse-Iceberg/86cc6ea0-506f-4559-bacb-865d51bb358d/scratchpad/` and may be gone; everything that matters is in the repo docs.

## 6. Numbers already established (do not recompute; cite the file)

| fact | value | file |
|---|---|---|
| closed-loop VaVAM, n=80 NuRec scenes | offroad_or_collision 0.625, at-fault 0.513, offroad 0.325, progress_rel 0.911; ~38 s/scene locally | `evaluation/ALPASIM.md` |
| skip screen, at-fault target, n=80 | ladder-only AUC 0.657 [0.53–0.78], recall 0.27/0.66/0.90 at 20/50/80% budget; all-features 0.628; axes-only 0.486; MF-PDMS alone 0.460; conflict load 0.371 (anti) | `evaluation/SKIP.md` |
| n=40 screen (superseded) | 0.785–0.801 — small-sample inflation | `evaluation/SKIP.md` |
| per-clip MF-PDMS vs closed-loop | no significant correlation at n=40; competence-class screen only | `evaluation/ALPASIM.md` |
| offline features on HF | 298,326 / 306,152 corpus clips; 31,861 / 32,651 on-disk; Gold top-300: 290 | `evaluation/ncore/README.md` |
| NCore conversion vs NVIDIA release (clip ac73935a) | identical: 599 frames × 6 cams, 199 lidar frames, returns to 0.0, poses, 1,186 cuboids; pixels mean diff 1–2/255; sizes within 0.2% | `evaluation/ncore/README.md` |
| NCore conversion cost here | ~2.5 min and ~3 GB per 7-camera clip (NVDEC on the RTX 6000) | same |
| NuRec v3 twin in AlpaSim (clip ac73935a, constant velocity, one rollout each) | ours_map vs nvidia: collision_rear 1 / 1 (both at 8 s), offroad 0 / 0, duration_frac 0.40 / 0.40, dist_traveled 0.062 / 0.094 m, dist_to_gt_trajectory 0.0044 / 0.0083, lane-boundary 0.389 / 0.387, img_is_black 0 / 0; 19.54 sim-s in 97 s wall; v3 PSNR 29.53 dB, 2 h 05 m training on the A10 | `evaluation/nurec/README.md` results table; `alpasim/runs/v3_*/per_clip.parquet` |
| NuRec v2b (no-aux) in AlpaSim | trains 1 h 17 m (6.9 it/s), no PSNR (validation asserts without aux), no ground mesh (0 ground points without road labels); `v2b_ours_map` numbers identical to v3's; map-less+mesh-less variant fails in physics (`mesh_ground.ply` required); renders visibly softer, passing car smeared | `evaluation/nurec/README.md` v2b section; `nurec/out/figures/` |
| VaVAM on our twin vs NVIDIA's (clip ac73935a, recorded routes) | same behaviour (drives off, no collision, leaves the road), ours 60 m / off-road 8.5 s vs NVIDIA 38 m / 6 s; dist_to_gt_trajectory 1.53 / 1.56; map-route generator fails on all three bundles with VaVAM | `evaluation/nurec/README.md` VaVAM section; `runs/v3_*_vavam_rec/per_clip.parquet` |
| twin queue, per clip (A10) | bb4394e7: convert 2 min, aux 2 h 48 m, train 2 h 19 m (5.5 it/s), ground mesh 10 min, 4 rollouts 8 min → 5 h 28 m end to end; PSNR 32.57 dB | `evaluation/nurec/README.md` fidelity table; `nurec/out/bb4394e7.twin.json` |
| AlpaSim time-base requirement | scene start ≥ 0.5 s above zero (`force_gt_duration_us`), all track timestamps ≥ 0 (uint64 loader); the checkpoint carries four absolute-time fields (`timestamps_us_min/max`, two `timestamps_us_ranges`) that must move with the JSON; renderer rebuilds the model from `datasource_summary.json`, so its track sample count is fixed | `evaluation/nurec/README.md` "time base" |
| NuRec catalog | 26.04: 1,607 scenes, all in clip_index; 26.01: 916, only 198 in clip_index; ~1.6–1.79 GB/scene | `evaluation/FEASIBILITY.md`, `episodes.py` output |
| storage model | twin 5.55 TB for 3,176 Gold; store-vs-regenerate break-even ~700 years (store); regeneration ~19.5 A100-h per clip-condition | `nvidia_ingestion/STORAGE_SIZING.md` |
| raw media per full-sensor clip | camera 235 MB (6 cams), lidar 356 MB, radar 8 MB, labels 0.4 MB | same |
| actors at the decision time, by condition | day 37.6, dawn/dusk 32.3, night 25.6 mean actors at t0 (from `nvidia_gold.scenario`) | Spark output 2026-09-21; not yet in a doc |
| Cosmos-Transfer2.5 on the Spark | official 121-frame 640x480 example: 49 min; our 4 s 1080p single-camera window (720p generation, 35 steps, 2 chunks): **90 min wall**, 4.0 MB output; gate: added 0.33 ≤ 0.34 → passed, not harder (day trim has no agents) → ~22 GB10-min per second of video per condition, ~10× a 4×A100 node's wall time | `cosmos_augmentation/FINDINGS.md` |
| 0-byte camera files on NFS | all 7 on-disk∩NCore∩NuRec clips have 1–2 empty cameras (April extraction bug; NVIDIA's copies are intact) | `evaluation/ncore/README.md` |

## 7. Open questions for the professor (unchanged from the plan doc)

Formal-validation reference doc (promised Aug 21); source of the main figure he edited;
L40S return date / can the data-bahn L40 tenant host AlpaSim's compose; input formats of
the non-NVIDIA serving modes (서울대 E2E, 라이드플러스); where a serving-tier scene
store lives (1.8 TB per 1,000 scenes); journal venue and author list; whether VaVAM is
an acceptable closed-loop policy for the journal if no GPU window opens.

## 8. Command cheat-sheet (absolute paths; `$I` = repo root `Lakehouse/Iceberg`)

```bash
# data
$I/mount_netai_e2e.sh                       # after a reboot
# open-loop ladder on a curated slice
cd $I/evaluation && python run_eval.py --policy constant_velocity --workers 8 --clips-file <list>
# closed-loop (catalog scenes / local USDZ dir)
DRIVER=vavam $I/evaluation/alpasim/run_scene.sh vavam clipgt-<id> ...
LOCAL_USDZ_DIR=<dir> $I/evaluation/alpasim/run_scene.sh constant_velocity
$I/evaluation/alpasim/repo/.venv/bin/python $I/evaluation/alpasim/per_clip.py <run_dir> -o <run_dir>/per_clip.parquet
# curation axes on a slice
NFS_ROOT=$I/evaluation/.av_slice_nurec python3 $I/planning/conflict_runner.py   # behavioral_runner.py likewise
NFS_ROOT=... $I/planning/cosmos3_reason/c3_venv/bin/python $I/planning/camera_perception_runner.py  (then write_camera_gated.py)
# skip policy
$I/evaluation/.skip_venv/bin/python $I/evaluation/skip.py features --closed-loop vavam $I/evaluation/.cl_vavam_perclip.parquet
$I/evaluation/.skip_venv/bin/python $I/evaluation/skip.py fit --feature-set openloop
$I/evaluation/.skip_venv/bin/python $I/evaluation/skip.py select --feature-set openloop --budget 0.5 --exclude-labelled --scene-ids --out next.txt
# episodes -> Iceberg
cd $I/evaluation && python3 episodes.py --workers 16 --out ../user_data/episodes_ondisk.parquet --scenarios-out ../user_data/scenarios_ondisk.parquet
docker exec -w /opt/spark spark-iceberg /opt/spark/bin/spark-submit nvidia_ingestion/build_episode_tables.py --inputs "/user_data/episodes_*.parquet"
# serving modes
python3 $I/evaluation/materialize.py nurec --clips-from-parquet <scores.parquet> --rank-col conflict_score --top-frac 0.1 --out <dir> [--download]
python3 $I/evaluation/materialize.py ncore --clips-file <list> --out <dir>
# NCore by hand
$I/evaluation/ncore/.venv/bin/python $I/evaluation/ncore/stage_pai_clip.py --clip <id> --out $I/evaluation/ncore/staged [--allow-empty]
cd $I/evaluation/ncore/repo && CUDA_VISIBLE_DEVICES=0 PYTHONPATH=$PWD ../.venv/bin/python -m tools.data_converter.pai.converter --root-dir ../staged --output-dir ../out [--camera-id ...] pai-v4 --clip-id <id>
PYTHONPATH=$I/evaluation/ncore/repo $I/evaluation/ncore/.venv/bin/python $I/evaluation/ncore/compare_ncore.py <ours.json> <nvidia.json>
# storage model
python3 $I/nvidia_ingestion/storage_sizing.py --gold-sizes 500,3176 --variants 3
```

## 9. Session log (append; newest last)

- **2026-09-21** — Direction extracted from the Aug 21 / Sep 4 / Sep 16 calls into the plan
  doc. NFS migrated to `.222` and remounted; mount script rewritten. WS1 closed (local
  USDZ identical). Curation axes scored on the NuRec slice; 40 more VaVAM closed-loop
  scenes (n=80); `skip.py` built, SKIP.md written (ladder-only screen 0.657). `episodes.py`
  + `build_episode_tables.py`: slice tables landed, full pass launched and chained.
  `storage_sizing.py` → STORAGE_SIZING.md. `materialize.py` with three modes; NVIDIA/ncore
  vendored, one clip converted and diffed **identical** against the NCore release
  (access granted mid-session). Found: offline features exist for 97% of the corpus;
  0-byte camera files on NFS. Committed as `2681931`, `aa689f4`. Paper work (WS0/WS6)
  untouched.
- **2026-09-21 (later)** — Terminology convention adopted and documented in `TERMINOLOGY.md`
  (evaluator / driving policy / actors / policy bridge / traffic conflict / rollout triage /
  serving mode); applied to all evaluation docs, PAPER_REFERENCE_SC26.md, MEDALLION_PROGRESS.md,
  the plan doc and the tool docstrings. Code identifiers unchanged (list in TERMINOLOGY.md).
  NCore reference diff against NVIDIA's release: identical (`evaluation/ncore/README.md`).
- **2026-09-21 (evening)** — The closed-loop question answered: our PAI → NCore → NuRec twin
  (v3) **drives in AlpaSim**. As exported it could not load (clip-relative time base: uint64
  overflow in the track loader, then AlpaSim's 0.5 s force-GT history before t=0); fixed by
  re-basing JSON/USDA/metadata **and the checkpoint's four time-range fields** onto NVIDIA's
  absolute axis (`nurec/alpasim_bundle.sh` = `usdz_tools.py shift-time` + `shift_checkpoint.py`
  + `add`; nothing dropped — dropping samples breaks the checkpoint ↔ `datasource_summary.json`
  correspondence). `v3_ours_map` vs `v3_nvidia` agree to the step under constant velocity;
  the traffic light turns green at the same step in both, so the shifted time embedding is
  coherent. Map-less `v3_ours` drives with `route_generator_type=RECORDED` (`run_scene.sh` gained
  `EXTRA_ARGS`) but the evaluator refuses to score it without a map (`offroad` missing). Orchestrator 6 continues with v2b (no-aux) training and its A/B. Spark:
  Cosmos-Transfer2.5 night clip rendered (90 min on the GB10), hallucination gate passed at
  the tolerance edge, not "harder" (no agents in the window); both WS4 placeholder constants
  now measured (`STORAGE_SIZING.md`). v2b (no-aux) then trained (1 h 17 m), no PSNR (validation
  asserts without aux) and no ground mesh; its `ours_map` drives with numbers identical to v3's,
  its map-less/mesh-less variant fails in physics (`mesh_ground.ply` required); renders are
  visibly softer than v3 (`nurec/out/figures/`). Reference rollout repeated bit-identically.
  Nothing running at handoff. Docs: `nurec/README.md` (time base + results + v2b),
  `cosmos_augmentation/FINDINGS.md`, `STORAGE_SIZING.md`, `alpasim/README.md`, this file.
