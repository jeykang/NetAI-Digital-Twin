"""cv_client.py — constant-velocity policy for HUGSIM, speaking its named-pipe protocol.

HUGSIM's closed_loop.py writes pickle((obs, info)) to <output>/obs_pipe and reads a plan
from <output>/plan_pipe: an (N, 2) array of waypoints in its ego frame (x right, y forward),
0.5 s apart; 'Done' ends the episode. This client keeps the current speed straight ahead —
the same reference policy as `constant_velocity` in our AlpaSim runs, so the two simulators
can be compared on it, and a template for bridging our other evaluator policies.
"""
import os
import pickle
import sys

import numpy as np

out = sys.argv[1]
obs_pipe, plan_pipe = os.path.join(out, "obs_pipe"), os.path.join(out, "plan_pipe")
for p in (obs_pipe, plan_pipe):
    if not os.path.exists(p):
        os.mkfifo(p)
print("cv client ready", flush=True)
n = 0
while True:
    with open(obs_pipe, "rb") as f:
        data = pickle.loads(f.read())
    if isinstance(data, str) and data == "Done":
        break
    obs, info = data
    v = float(info.get("ego_velo", 1.0))
    plan = np.array([[0.0, v * 0.5 * (k + 1)] for k in range(8)], dtype=np.float64)
    with open(plan_pipe, "wb") as f:
        f.write(pickle.dumps(plan))
    n += 1
print(f"cv client done after {n} steps", flush=True)
