"""Load EarSet in-ear IMU files into clean 50 Hz arrays in SI-like units.

Raw units: acc * 0.061 -> milli-g, gyro * 17.5 -> milli-degrees/s (EarSet README).
We return acc in g and gyro in rad/s, sorted by time, resampled to FS on a uniform grid.
See ../data/external/EARSET_NOTES.md for the caveats handled here.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EARSET = ROOT / "data" / "external" / "earset" / "Dataset"
FS = 50

HEAD = ["nod", "shake", "tilt"]
FACE = ["brow-raiser", "brow-lowerer", "wink-l", "wink-r", "eyes-lr", "eyes-ud",
        "lip-puller", "chin-raiser", "mouth-stretch"]
NEGATIVE = ["still", "speaking", "chewing", "swallowing", "walking", "running"]


def participants():
    return sorted((p.name for p in EARSET.glob("P*") if p.is_dir()), key=lambda s: int(s[1:]))


def imu_path(pid, activity, ear="left"):
    """The plain file (no '(1)' or '-1' duplicates). None if missing."""
    p = EARSET / pid / "EARBUDS" / f"{pid[1:]}-{activity}-imu-{ear}.csv"
    return p if p.exists() else None


MAX_GAP_S = 0.5   # nearly every file is two contiguous chunks stored out of order with a gap between them
MIN_CHUNK_S = 5.0


def load(pid, activity, ear="left", fs=FS):
    """-> list of X (T, 6) chunks = [ax ay az] in g, [gx gy gz] in rad/s, each contiguous and resampled to fs.

    Never interpolates across a time gap. None if the file is missing.
    """
    path = imu_path(pid, activity, ear)
    if path is None:
        return None
    df = pd.read_csv(path, comment="#")
    df = df.dropna().sort_values("timestamp").drop_duplicates("timestamp")
    t = (df["timestamp"].to_numpy(float) - df["timestamp"].iloc[0]) / 1000.0
    acc = df[["ax", "ay", "az"]].to_numpy(float) * 0.061 / 1000.0
    gyro = np.deg2rad(df[["gx", "gy", "gz"]].to_numpy(float) * 17.5 / 1000.0)
    raw = np.hstack([acc, gyro])
    cuts = np.where(np.diff(t) > MAX_GAP_S)[0] + 1
    chunks = []
    for a, b in zip(np.r_[0, cuts], np.r_[cuts, len(t)]):
        tc = t[a:b]
        if tc[-1] - tc[0] < MIN_CHUNK_S:
            continue
        grid = np.arange(tc[0], tc[-1], 1.0 / fs)
        chunks.append(np.stack([np.interp(grid, tc, raw[a:b, j]) for j in range(6)], axis=1))
    return chunks
