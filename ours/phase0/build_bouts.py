"""EarSet -> one row per detected bout, features in three frames -> results/bouts.csv

The first N_CALIB nod bouts of each person are used only to find their head frame (R2) and are dropped.
The quiet level for cutting bouts comes from the person's own `still` recording (like our calibration still pose),
so continuous motion (walking, chewing) is detected instead of hidden. Also writes results/recordings.csv: minutes
of every recording that was loaded, the exposure for false alarms per hour. Left ear only. Run: python build_bouts.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

from earset import FACE, HEAD, NEGATIVE, load, participants
from features import NAMES, bout_features
from frames import heading_from_nods, to_frame
from segment import bouts, quiet_reference

N_CALIB = 3
OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(exist_ok=True)

rows, recs = [], []
for p in participants():
    data = {a: load(p, a) for a in HEAD + FACE + NEGATIVE}
    data = {a: c[0] for a, c in data.items() if c}  # one 120 s chunk per file after gap handling
    if "nod" not in data or "still" not in data:
        continue
    ref = quiet_reference(data["still"])
    recs += [{"person": p, "activity": a, "minutes": len(X) / 50 / 60} for a, X in data.items()]
    nod_b = bouts(data["nod"], ref=ref)
    calib = nod_b[:N_CALIB]
    heading = heading_from_nods([to_frame(data["nod"], s, e, "R1")[1] for s, e in calib])
    for act, X in data.items():
        for i, (s, e) in enumerate(bouts(X, ref=ref)):
            if act == "nod" and i < N_CALIB:
                continue
            row = {"person": p, "activity": act, "bout": i, "start_s": s / 50}
            for fr in ("R0", "R1", "R2"):
                acc, gyro = to_frame(X, s, e, fr, heading)
                row.update({f"{fr}_{n}": v for n, v in zip(NAMES, bout_features(acc, gyro))})
            rows.append(row)
    print(p, end=" ", flush=True)

df = pd.DataFrame(rows)
df.to_csv(OUT / "bouts.csv", index=False)
pd.DataFrame(recs).to_csv(OUT / "recordings.csv", index=False)
print(f"\n{len(df)} bouts -> {OUT / 'bouts.csv'}")
print(df.groupby("activity").size().to_string())
