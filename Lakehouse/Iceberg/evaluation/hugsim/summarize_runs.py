"""summarize_runs.py — one row per HUGSIM closed-loop episode.

  docker run --rm -v $H:$H -w $H/repo hugsim-dev:cu118 pixi run python $H/summarize_runs.py runs/pai_vavam_s*_ltf/*

For each episode dir (closed_loop.py output): steps, simulated seconds, distance driven, the
largest gap to the recorded front-camera path (HUGSIM ends an episode at > 10 m), how it ended,
and the HD-Score terms from eval.json.
"""
import glob
import json
import os
import pickle
import sys

import numpy as np

H = os.path.dirname(os.path.abspath(__file__))
dirs = [d for a in sys.argv[1:] for d in sorted(glob.glob(a if os.path.isabs(a) else os.path.join(H, a)))]
print(f"{'episode':52s} {'steps':>5s} {'sim s':>5s} {'dist m':>6s} {'max gap':>7s} {'end':10s}"
      f" {'NC':>5s} {'DAC':>5s} {'TTC':>5s} {'C':>4s} {'Rc':>5s} {'HD':>6s}")
for d in dirs:
    if not os.path.exists(os.path.join(d, "eval.json")):
        print(f"{os.path.relpath(d, H):52s} (no eval.json)")
        continue
    ev = json.load(open(os.path.join(d, "eval.json")))
    infos = pickle.load(open(os.path.join(d, "infos.pkl"), "rb"))
    # the scene's recorded front-camera path, as the simulator loaded it (model_base/<scene>)
    scene = os.path.basename(d).rsplit("_", 2)[0]
    gp = None
    for root in ("data/scenes/pai", "data/scenes/nuscenes"):
        p = os.path.join(H, root, scene, "ground_param.pkl")
        if os.path.exists(p):
            gp = pickle.load(open(p, "rb"))[0]
            break
    # infos.pkl stops one step short (the terminating step's info is not appended); data.pkl
    # has every step, with ego_box in HUGSIM's IMU frame (x = world z, y = -world x)
    frames = pickle.load(open(os.path.join(d, "data.pkl"), "rb"))[0]["frames"]
    xz = np.array([[infos[0]["ego_pos"][0], infos[0]["ego_pos"][2]]]
                  + [[-f["ego_box"][1], f["ego_box"][0]] for f in frames])
    dist = float(np.sum(np.linalg.norm(np.diff(xz, axis=0), axis=1)))
    gap = float("nan")
    if gp is not None:
        ref = np.asarray(gp)[:, [0, 2], 3]
        gap = float(max(np.min(np.linalg.norm(ref - p, axis=1)) for p in xz))
    last = frames[-1]
    if last["collision"]:
        end = "collision"
    elif last["rc"] >= 1:
        end = "complete"
    elif gap > 10:
        end = "off path"
    else:
        end = "step cap"
    print(f"{os.path.relpath(d, H):52s} {len(frames):5d} {last['time_stamp']:5.2f} {dist:6.1f} {gap:7.1f} {end:10s}"
          f" {ev['nc']:5.2f} {ev['dac']:5.2f} {ev['ttc']:5.2f} {ev['c']:4.1f} {ev['rc']:5.2f} {ev['hdscore']:6.3f}")
