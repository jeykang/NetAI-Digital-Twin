# datax-l40-gpu acceptance test

Run the evaluation harness across all 8 L40s on the new box, in the pod shape the
`partridge` tenant will be held to, so the workload transplants unchanged at handover.

There is no local kubeconfig — `kctl.py` runs kubectl on the control plane over SSH
using `.secrets/datax-controlplane.env` (gitignored, `DATAX_ID` / `DATAX_PW`).

```bash
python deploy/k8s/kctl.py get nodes
```

## Verified cluster facts (2026-08-26)

| | |
|---|---|
| Node | `datax-l40-gpu`, 9d old, `Ready`, **idle** (0 GPU requests, DaemonSets only) |
| GPUs | 8 × NVIDIA-L40, **46068 MiB each**, ada-lovelace, ESC8000A-E12 |
| Host | 96 CPU, 377 GiB RAM, driver 580.126.20, CUDA runtime 13.0 |
| Taints | `nvidia.com/gpu=true:NoSchedule` — **the only one**; `dedicated-nodes=partridge` is a label, not a taint |
| Admission | `enforce-partridge-l40-gpu-jobs` + `deny-partridge-direct-node-binding` are **live and Ready** |
| Registries | docker.io, ghcr.io, nvcr.io, quay.io, registry.k8s.io all pull — no Harbor in this cluster |
| Storage | `dx-ceph-standard-filesystem` (RWX CephFS); `dx-ceph-standard-block` is the default class |

## ⚠ Cluster storage is frozen

`deny-new-e3s-recovery-storage-consumers` blocks **every** PVC and ObjectBucketClaim on
all seven Ceph StorageClasses, cluster-wide, `Enforce` + `failurePolicy: Fail`, with —
in its own words — *"intentionally no rule-level exclusions"*. So `20-storage.yaml` and
`30-prep.yaml`/`40-eval.yaml` cannot run until that lifts. **Use `41-eval-nodisk.yaml`.**

The deny keys on `spec.storageClassName`, so a static PV with `storageClassName: ""`
would evade it. Don't: that circumvents a protective control during a declared storage
recovery.

## Run order (no-Ceph path)

```bash
K="python deploy/k8s/kctl.py"

# 1. namespace, self-imposed quota, LimitRange
$K apply -f - < deploy/k8s/00-namespace.yaml

# 2. hf-token Secret + eval-harness ConfigMap. kubectl runs on the control plane but
#    the harness files are local, so --from-file cannot see them: this builds the
#    ConfigMap locally and pipes it to a remote apply. Idempotent.
python deploy/k8s/bootstrap.py

# 3. smoke test FIRST — proves pull + GPU + admission in ~10 s
$K apply -f - < deploy/k8s/10-gpu-smoke.yaml
$K logs -n netai-l40-test job/l40-gpu-smoke

# 4. the run (4 × 1 GPU, self-staging, ~20-30 min of setup per pod)
$K apply -f - < deploy/k8s/41-eval-nodisk.yaml
python deploy/k8s/watch.py l40-eval-r1-nodisk 40
```

`watch.py` holds one SSH session open — `kctl.py` opens a fresh one per call (~10-20 s),
which is too slow to poll a Job with.

Once the freeze lifts, `20-storage.yaml` + `30-prep.yaml` + `40-eval.yaml` are the better
path: one shared RWX copy of the weights instead of one per pod, which is what allows all
8 GPUs instead of 4.

## Resource arithmetic

8 pods × (6 CPU, 24Gi) requested = 48 CPU / 192Gi, against a 96 CPU / 377Gi node and a
self-imposed quota of 64 CPU / 200Gi requests. Limits total 80 CPU / 256Gi against
88 / 300Gi. It fits, with the memory request the tightest line.

## Run length comes from replay, not from data

The pool has 121 TiB free, but it is **shared and not ours to fill**, so footprint is
minimised and the burn-in is extended by replaying a tiny slice.

Storage floor is the model, not the data:

| | |
|---|---|
| Alpamayo-R1 weights | ~21 GiB — unavoidable |
| venv | ~8 GiB |
| `av_root` (16 clips) | ~1.1 GiB |
| transient chunk ZIPs | ~5.5 GiB **peak, not cumulative** — `--prune-cache` drops each one right after extraction |
| results | ~16 KiB/shard |

~36 GiB in flight against a 60Gi PVC. Raising `PASSES` lengthens the run at **zero**
extra storage.

`select_clips()` does not dedupe, so passes 2..N run as a single invocation over the
shard repeated N-1 times — the model loads once, not once per pass.

**Pass 1 is the only comparable throughput number.** The slice is ~1 GiB against 377 GiB
of node RAM, so everything after pass 1 is served from page cache. The run is partly I/O
and CoC-generation bound — exactly why the A100 showed less speedup than its compute
ratio implied — so warm passes report an inflated s/clip. The Job prints the two segments
separately for this reason: quote pass 1 against the 22–24 s/clip A100 / 26.9 s/clip A10
ladder, and treat the rest as thermal/power/ECC/driver-stability evidence only.

## Caveats

- **The node is the rsync runner** for the suspended netai-e2e Performance→Standard
  migration. It is free now; if that copy resumes, this run contends with its pinned
  200 MiB/s stream on the same NIC and CPU.
- **Alpamayo2-Super cannot run here** — ~68 GB across ≥2 GPUs versus a hard one-GPU-per-pod
  admission cap on 46 GB cards. It stays on the A100 cluster.
- **Alpamayo-1.5 additionally pulls the gated `nvidia/Cosmos-Reason2-8B`** at load time.
  Only R1 is wired into `40-eval.yaml`; add 1.5 only after confirming that base downloads.
- `partridge` is live (17 pods, 76.5Gi of its 100Gi memory limit). Nothing here touches it.
