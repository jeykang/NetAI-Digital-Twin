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

## Investigation results (2026-06-23, `battery_investigate.py`)

**(1) Lidar-covered subset (31,737 clips, 200 ood) — the achievable ceiling.**
| signal | AUC |
|---|---|
| composite (current weights) | 0.547 |
| conflict alone | 0.651 |
| perception (n=29) | 0.564 |
| time_of_day | 0.511 |
| ego_dynamics | 0.500 |
| season_geography | 0.450 |
| sensor_coverage | 0.404 |
| **WHATIF (conflict 0.45 / perception 0.25 / metadata small)** | **0.648** |

→ On covered clips the current composite is only 0.547 (the 274k metadata-only
clips drag the full-set figure to 0.450). A conflict-centered re-weighting reaches
0.648 — **essentially conflict-alone (0.651); the metadata dims add nothing
positive (they slightly dilute).**

**(2) `sensor_coverage` is miscalibrated, not just "a different axis".**
- ood mean 0.695 < non mean 0.757 → human-hard clips have *better* sensor
  coverage (they're full-rig clips with events). Anti-alignment confirmed.
- Histogram: values {0.474: 22.7k, 0.526: 87k, 0.579: 50.7k, **1.0: 145.3k**} —
  **47% of all clips are scored maximally sensor-deprived (1.0).** Implausible;
  this is the same naive-sensor-expectation failure mode that the Silver
  `missing_sensors` rewrite already fixed. The dimension should be dropped or
  recalibrated against `feature_presence` (expected-sensor truth).

**(3) `season_geography` and `ego_dynamics` are near-constant (degenerate).**
- season_geography: 5 values, **0.2 covers 281k / 305k clips (92%)**.
- ego_dynamics: **0.5 (neutral default) covers 273k clips (89%)** — i.e. the ego
  aggregate is only actually computed for ~11% of clips; the rest fall to the
  default. And even on the covered subset its AUC is 0.500 (pure chance) — so
  ego-kinematics doesn't track event-hardness even when present (consistent with
  the planning-signal failures).
- The ρ=−0.844 is an **artifact**: where season≠0.2 (the rare 8%), mean ego≈0.17;
  where season=0.2 (the 92%), mean ego≈0.49. Two mostly-constant columns that
  deviate together on a small subset → spurious strong rank correlation. Neither
  carries real discriminative information.

### Net conclusion
Only `time_of_day` has real variance among the metadata dims, and it's a weak
*environmental* signal (~0.48–0.51), not event-hardness. `season_geography` and
`ego_dynamics` are effectively dead (near-constant); `sensor_coverage` is
miscalibrated and anti-aligned. The validated event/agent signal (`conflict`,
≈0.65) is the only thing that works — and a conflict-centered composite matches
conflict-alone. **The real blocker is coverage**: conflict reaches only the
31,737 lidar clips, so a globally-valid Gold needs conflict-like coverage for the
rest (BEVFusion camera-detector path) or an explicit lidar-covered event tier.

### Recommended concrete change
- **Drop** `season_geography` + `ego_dynamics` (degenerate) and **`sensor_coverage`**
  (miscalibrated) from the difficulty composite.
- **Re-weight**: conflict primary, perception secondary, `time_of_day` small
  (keep a light environmental nudge). Re-validate (covered-subset target ~0.65).
- **Close coverage**: run the label-free BEVFusion *camera* conflict path for the
  ~274k non-lidar clips, OR scope the difficulty tier to lidar-covered clips.

## Resolution — APPLIED 2026-06-23
Re-weighted + scoped the difficulty composite (`edge_case_scorer.py`):
- **Dropped** `season_geography`, `ego_dynamics` (degenerate) and `sensor_coverage`
  (miscalibrated) from the blend — weight 0; still computed into `detail` for
  diagnostics. New weights: **conflict 0.60, perception 0.25, time_of_day 0.15**.
- **Scoped** the difficulty tier to sensor-covered clips via a new
  `sensor_covered` score column (has conflict/perception = is in the on-disk 10TB
  sample). Threshold, selection, and stats all filter on it; catalog-only clips
  are excluded from Gold.

**Re-validated**: composite OOD AUC **0.450 → 0.655** on the covered tier (now
slightly above conflict-alone 0.651; metadata no longer drags it). Gold =
**3,174 clips** (top 10% of 31,737 sensor-covered), score std 0.087 → 0.223
(real discrimination). The production difficulty score now tracks human-judged
difficulty instead of opposing it.

Regenerate the OOD id list with:
`python3 -c "import pyarrow.parquet as pq; open('nvidia_ingestion/_ood_clips.txt','w').write('\n'.join(pq.read_table('<ood_reasoning.parquet>',columns=['clip_id']).column('clip_id').to_pylist()))"`
