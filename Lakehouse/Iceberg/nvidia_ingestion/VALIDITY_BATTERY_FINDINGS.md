# Validity Battery on Existing Gold Sub-scores — Findings (2026-06-23)

Ran the same battery that refuted `mode_spread` against the dimensions already in
production (`nvidia_ingestion/validity_battery.py`, over all 305,724 scored clips
in `iceberg.nvidia_gold.clip_scores`, vs the 1,740 human-flagged hard clips in
`ood_reasoning`; 1,737 overlap). **It turned up a significant problem.**

## External-label OOD AUC (per sub-score)
| dimension | AUC | n_ood | verdict |
|---|---|---|---|
| time_of_day | 0.477 | 1737 | weak / slightly anti |
| season_geography | 0.507 | 1737 | no signal |
| **sensor_coverage** | **0.432** | 1737 | **ANTI-aligned** |
| ego_dynamics | 0.498 | 1737 | no signal |
| perception | 0.564 | 29 | modest (low power, n=29) |
| **conflict** | **0.651** | 200 | **GOOD** (the just-shipped signal) |
| **difficulty_score (composite)** | **0.450** | 1737 | **ANTI-aligned** |

## Convergent / discriminant (Spearman)
- composite ρ: **time_of_day 0.797** (dominates), sensor_coverage 0.598,
  perception 0.461, conflict 0.397, ego_dynamics 0.129, season_geography −0.055.
- `season_geography ~ ego_dynamics = −0.844` — suspiciously strong; likely a
  degeneracy (one near-constant/bimodal) worth a closer look.

## What this means
1. **The production composite does NOT surface the human-hard clips — it is
   slightly anti-aligned (0.450).** It is dominated by `time_of_day` (ρ=0.797):
   Gold is effectively selecting *dark* clips, not *hard-to-drive* clips.
2. **The four metadata dimensions individually carry ~no signal vs human
   difficulty** (AUC 0.43–0.51); `sensor_coverage` is actively anti-aligned (the
   human-hard clips tend to have *good* sensor coverage — they're hard for scene
   reasons, not sensor reasons).
3. **Only `conflict` (0.651) and weakly `perception` (0.564, n=29) track human
   difficulty** — i.e. the agent/scene-interaction signals, not the
   environmental/operational metadata.
4. This **retroactively explains the ego-kinematics planning failures**:
   `ego_dynamics` itself (0.498) doesn't track difficulty, so signals that
   correlated with it (rung-0 CV, open-loop L2) couldn't either.
5. **Coverage gap**: `conflict` exists only for the 31,812 lidar-covered clips
   and `perception` for 3,338 — so for ~274k clips the composite is *metadata
   only*, i.e. anti-aligned.

## Important caveat (what's being measured)
`ood_reasoning` labels driving-**event/agent** hardness (work zones, pedestrian
density, cut-ins…). The metadata dims measure **operational-domain** hardness
(night, winter, sparse sensors) — a *legitimate but different* axis. So "metadata
is anti-aligned" means "it measures a different thing than the human hard-event
labels," not "it is meaningless." The problem is one of **intent + weighting**:
if Gold's purpose is "hardest-to-drive edge cases" (the project's stated goal,
and the whole point of the driving-difficulty effort), then event/agent hardness
is the target and the current metadata-dominated weighting is misaligned.

## Recommended modifications (for decision)
1. **Re-weight** the composite to center the validated signals — `conflict`
   primary, `perception` secondary — and demote the metadata dims to a small
   secondary contribution (or split Gold into an "event-hard" tier and a separate
   "operational-domain" tier).
2. **Close the coverage gap** so the good signal applies broadly: either restrict
   the event-hard tier to lidar-covered clips, or run the BEVFusion *camera*
   detector path for non-lidar clips (label-free, ~0.63).
3. **Drop/repair `sensor_coverage`** (anti-aligned) and investigate the
   `season_geography ~ ego_dynamics` −0.844 degeneracy.
4. **Re-validate** the new composite against `ood_reasoning` (target AUC > 0.6).

Regenerate the OOD id list with:
`python3 -c "import pyarrow.parquet as pq; open('nvidia_ingestion/_ood_clips.txt','w').write('\n'.join(pq.read_table('<ood_reasoning.parquet>',columns=['clip_id']).column('clip_id').to_pylist()))"`
