# Alpamayo-1.5 VLM difficulty scorer — SHELVED (2026-06-26)

**Idea**: have a reasoning VLM (`nvidia/Alpamayo-1.5-10B`, Apache-2.0, built on the
Cosmos-Reason2 backbone) *judge* per-clip driving difficulty directly, instead of
running a planner. This sidesteps the planner-**transfer** failure that sank
SparseDrive/DiffusionDrive (no driving — just judging), and Alpamayo is native to
the NVIDIA PhysicalAI dataset family.

**Verdict: SHELVED.** It works and the reasoning is genuinely good, but the
difficulty *signal* does not beat the existing `conflict` axis, is only weakly
scene-grounded, and is wildly impractical on this hardware. Production stays the
validated **conflict + darkness** noisy-OR union (see `nvidia_ingestion/VALIDITY_BATTERY_FINDINGS.md`).

## Setup (reproducible)
- Vendored repo `NVlabs/alpamayo1.5` + `uv` venv `a1_5_venv` (Python 3.12, torch
  2.8+cu128, transformers 4.57, **SDPA** — no `nvcc` on this host), both gitignored.
- Weights pulled from HF (`nvidia/Alpamayo-1.5-10B`, ~20 GB) via the existing
  `jeykang-gist` login (model not gated; dataset access granted).
- Frames streamed by `physical_ai_av` by `clip_id` (same dataset as our subset).
- Run on RTX 6000 (`CUDA_VISIBLE_DEVICES=1`, `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`).

## What was tried, vs the production baseline
Gate = the 452-clip OOD-labelled set (`/tmp/conf/clips.txt`); circularity caveat:
`ood_reasoning` is Alpamayo-lineage, so AUC here is generous, not independent.

| Approach | OOD AUC | ρ vs conflict | neg-control | throughput |
|---|---|---|---|---|
| cold VQA digit (logit-EV) | 0.437 | −0.158 | +0.10 | 6.6 s/clip |
| reasoned VQA (free reason → score) | 0.565 | +0.04 | +0.21 | ~8 s/clip |
| **native CoC rollout** (best) | **0.604** | +0.15 | **+0.03** | **66.5 s/clip** |
| minADE (trajectory prediction error) | 0.350 | — | — | — |
| **conflict (production)** | **0.651** | — | 0.10→0.003 | GPU-free |

## Key findings
1. **Output-format problem solved** — reading the next-token distribution over
   digits 0–9 (logit expected-value) gives a continuous, 100%-parseable,
   *deterministic* score (single forward, no sampling). This is the reusable bit.
2. **The model sees scenes well** — free descriptions are accurate ("stopped truck
   blocking the lane", "construction cones blocking the center", "cut-in vehicle
   merging"). The CoC reasoning is high quality.
3. **But the difficulty scalar is weak**: best (CoC) AUC 0.604 < conflict 0.651,
   and the cold snap-judgment is *anti-aligned* (0.437) because it defaults to a
   "dark = hard" prior. Reasoning helps (0.437→0.565→0.604) but never clears conflict.
4. **Grounding weakens with reasoning**: CoC neg-control is only **+0.03** — the
   model hallucinates a plausible chain-of-causation even on blanked frames, so the
   score is substantially prior-driven. Real validity red flag.
5. **`minADE` (planning error) is anti-aligned (0.350)** — re-confirms prediction
   error tracks ego-kinematics, not difficulty (same lesson as rung-0/DiffusionDrive).
6. **Infeasible on 24 GB**: the 10B model is 22 GB resident; the CoC rollout
   (diffusion expert + generation) only fits at a degraded **1-frame / 64-token**
   config (~23 GB peak), and runs at **66.5 s/clip → ~610 h for the 33k sample**.

## If revisited (≥40 GB GPU)
The CoC reasoning quality justifies a retry on bigger hardware (H100/A100):
full-config rollout (4 frames, 256-token reasoning, batched), stronger negative
control (shuffled-frame, not just blank), and an independent validation anchor
(not `ood_reasoning`). Even then it must beat conflict's 0.651 to earn a place.

## Files
- `difficulty_qa.py` — model load + logit-EV scorer (VQA path).
- `gate_runner.py` — VQA gate (cold logit-EV).
- `reasoned_gate.py` — reason-then-extract (VQA) gate.
- `coc_gate.py` — native CoC-rollout gate (+ minADE).
- Env/weights/vendored repo are gitignored (`alpamayo1.5/`, `*venv*`).
