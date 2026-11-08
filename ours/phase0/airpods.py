"""Our old AirPods Pro 2 data (4 people, cued 2.5 s takes) -> same bout features as EarSet -> results/airpods_bouts.csv

Source: ../../prior_work/gesture_lab/data/raw/subject1..4.csv (read only; subject 4's circle labels already corrected there).
Sensor Logger gives user acceleration (gravity removed) and gravity separately, both in m/s^2 (checked in
../sensor/check_fields.py). We add them back together and convert to g so the same frame code as EarSet works: the quiet just before a bout gives the gravity direction.
The sign convention of gravity does not matter, all features are unsigned.
Calibration: like EarSet, each person's first 3 nod takes give the head frame and are dropped.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import uniform_filter1d

from features import NAMES, bout_features
from frames import heading_from_nods, to_frame

RAW = Path(__file__).resolve().parents[2] / "prior_work" / "gesture_lab" / "data" / "raw"
OUT = Path(__file__).resolve().parent / "results"
N_CALIB = 3
FS = 50
ACTIVITY = {"nod_2x_front": "nod", "tilt_2x_left": "tilt", "tilt_2x_right": "tilt"}  # EarSet names


def takes(subject):
    df = pd.read_csv(RAW / f"subject{subject}.csv")
    df["start_ms"] = df.session_id.astype(str).str.extract(r"_(\d{13})$")[0].astype("int64")
    for sid, g in sorted(df.groupby("session_id", sort=False), key=lambda kv: kv[1].start_ms.iloc[0]):
        if len(g) < 40:
            continue
        acc = (g[["accX", "accY", "accZ"]].to_numpy(float) + g[["gravX", "gravY", "gravZ"]].to_numpy(float)) / 9.81
        yield g.label.iloc[0], np.hstack([acc, g[["rotX", "rotY", "rotZ"]].to_numpy(float)])


def active(X, frac=0.25, pad=10):
    """Bout inside a take: from first to last sample whose rotation speed passes frac x the take's peak."""
    m = uniform_filter1d(np.linalg.norm(X[:, 3:], axis=1), 5)
    idx = np.where(m > frac * m.max())[0]
    return max(0, idx[0] - pad), min(len(X), idx[-1] + pad + 1)


def main():
    rows = []
    for s in (1, 2, 3, 4):
        tk = list(takes(s))
        nods = [X for lab, X in tk if lab == "nod_2x_front"]
        heading = heading_from_nods([to_frame(X, *active(X), "R1")[1] for X in nods[:N_CALIB]])
        n_nod = 0
        for i, (lab, X) in enumerate(tk):
            if lab == "nod_2x_front":
                n_nod += 1
                if n_nod <= N_CALIB:
                    continue
            a, b = active(X)
            row = {"person": f"A{s}", "label": lab, "activity": ACTIVITY.get(lab, lab), "take": i}
            for fr in ("R0", "R1", "R2"):
                acc, gyro = to_frame(X, a, b, fr, heading)
                row.update({f"{fr}_{n}": v for n, v in zip(NAMES, bout_features(acc, gyro))})
            rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "airpods_bouts.csv", index=False)
    print(df.groupby(["person", "activity"]).size().unstack(0).to_string())


if __name__ == "__main__":
    main()
