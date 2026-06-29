"""Select easy daytime clips to augment (the batch targets) + write per-clip depth
specs with rotated conditions (night/rain/fog).

Easy daytime target = low behavioral_score (easy interactions) + high cam_max_conf
(clear, confident daytime detections) + agents present (cam_ndet>=2, so there's
something for the augmentation to make harder). Writes batch_specs/<short>_<cond>.json
+ batch_manifest.json. See cosmos_augmentation/FINDINGS.md (recipe: depth + mix).
"""
import glob, json, os, sys
import pyarrow.parquet as pq
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_refine_specs import PROMPTS

ROOT = "netai-e2e/nvidia-physicalai-av-subset"
HERE = os.path.dirname(os.path.abspath(__file__))
N = int(sys.argv[1]) if len(sys.argv) > 1 else 9
CONDS = ["night", "rain", "fog"]

beh = pq.read_table(f"{ROOT}/.behavioral/behavioral_shard_00_of_01.parquet").to_pydict()
cam = pq.read_table(f"{ROOT}/.camera_perception/camera_perception.parquet").to_pydict()
B = {c: beh["behavioral_score"][i] for i, c in enumerate(beh["clip_id"])}
C = {c: (cam["cam_max_conf"][i], cam["cam_ndet"][i]) for i, c in enumerate(cam["clip_id"])}

cands = []
for c in B:
    if c in C and B[c] < 0.30 and C[c][0] > 0.60 and C[c][1] >= 2:
        m = glob.glob(f"{ROOT}/camera/camera_front_wide_120fov/*/{c}.camera_front_wide_120fov.mp4")
        if m:
            cands.append((c, B[c], C[c][0], m[0]))
cands.sort(key=lambda x: (x[1], -x[2]))          # easiest + clearest first
sel = cands[:N]

os.makedirs(f"{HERE}/batch_specs", exist_ok=True)
for f in glob.glob(f"{HERE}/batch_specs/*.json"):
    os.remove(f)
manifest = []
for i, (c, b, cf, mp4) in enumerate(sel):
    cond = CONDS[i % len(CONDS)]; short = c[:8]
    spec = {"prompt": PROMPTS[cond],
            "input_video_path": f"/scratch/autodr_test/aug_test/batch_inputs/{short}_121.mp4",
            "depth": {"control_weight": 1.0}}
    json.dump(spec, open(f"{HERE}/batch_specs/{short}_{cond}.json", "w"), indent=2)
    manifest.append({"clip": c, "short": short, "cond": cond, "local_mp4": mp4,
                     "behavioral": round(b, 3), "cam_conf": round(cf, 3)})
json.dump(manifest, open(f"{HERE}/batch_manifest.json", "w"), indent=2)
print(f"selected {len(sel)} easy daytime clips:")
for m in manifest:
    print(f"  {m['short']}  beh={m['behavioral']}  camconf={m['cam_conf']}  -> {m['cond']}")
