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
| WS3 scenario × episode | slice tables landed (`nvidia_gold.episode` 822 rows, `nvidia_gold.scenario` 3); **full 32,651-clip pass was running at handoff** with the Spark landing job chained | `evaluation/episodes.py`, `nvidia_ingestion/build_episode_tables.py`, `user_data/episodes_*.parquet` | verify §5 finished; if not, rerun the pass and the Spark job (commands in §8). Then: key `eval.policy_runs` rows by episode_id; a figure of the combination space |
| WS4 storage sizing | model + report written | `nvidia_ingestion/storage_sizing.py` → `STORAGE_SIZING.md` | two missing constants: NuRec reconstruction time per scene (L40S), size of one Cosmos variant (next A100 window) |
| WS5 serving modes | `materialize.py` (openloop / nurec / ncore) working; NCore conversion of one Gold-eligible clip **identical to NVIDIA's release** on every structured quantity | `evaluation/ncore/README.md` (incl. reference diff), `compare_ncore.py`, `out/pai_ac73935a…`, `reference/clips/ac73935a…` | NuRec reconstruction of that store (NGC container, ≥24 GB VRAM Ampere → L40S / data-bahn L40); then `LOCAL_USDZ_DIR` run and closed-loop diff vs NVIDIA's NuRec artifact of the same clip; bulk Gold conversion on the storage cluster (~3 GB, ~2.5 min per clip) |
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
| full on-disk episode pass (`episodes.py --workers 16`, ~4.8 clips/s, 32,651 clips, started 01:15) | `pgrep -f "episo""des.py"`; `user_data/episodes_ondisk.parquet` mtime and row count (expect ~190k rows, ~6 per clip) | rerun: `cd evaluation && python3 episodes.py --workers 16 --out ../user_data/episodes_ondisk.parquet --scenarios-out ../user_data/scenarios_ondisk.parquet` |
| chained Spark landing (`/tmp/claude-1000/.../scratchpad/land_episodes.sh`, waits for the pass, then `build_episode_tables.py --inputs "/user_data/episodes_*.parquet"`) | `nvidia_gold.scenario` should show `openloop-mfpdms`, `augmented-openloop`, `closedloop-nurec` rows with tens of thousands of decision windows | run the Spark command in §8 by hand |
| nothing on the GPUs | `nvidia-smi` | — |

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
| NuRec catalog | 26.04: 1,607 scenes, all in clip_index; 26.01: 916, only 198 in clip_index; ~1.6–1.79 GB/scene | `evaluation/FEASIBILITY.md`, `episodes.py` output |
| storage model | twin 5.55 TB for 3,176 Gold; store-vs-regenerate break-even ~700 years (store); regeneration ~19.5 A100-h per clip-condition | `nvidia_ingestion/STORAGE_SIZING.md` |
| raw media per full-sensor clip | camera 235 MB (6 cams), lidar 356 MB, radar 8 MB, labels 0.4 MB | same |
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
