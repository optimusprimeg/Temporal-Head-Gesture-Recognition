"""Loaders: every source becomes a Recording (see recording.py for units and channel order).

    load_session(folder)        collector v3 session (stream.csv + cues.csv + session.json), or a Mac app CSV
    load_earset(pid, activity)  public EarSet in-ear IMU (custom earbud, ~104 Hz, raw acc + gyro)
    load_old_takes(subject)     our old AirPods takes (prior_work/gesture_lab/data/raw), one Recording per cued take
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt

from .recording import ACC, CHANNELS, G, GRAV, QUAT, ROT, Recording, to_grid

OURS = Path(__file__).resolve().parents[2]
EARSET = OURS / "data" / "external" / "earset" / "Dataset"
OLD_RAW = OURS.parent / "prior_work" / "gesture_lab" / "data" / "raw"


def _estimate_fs(t_s):
    step = np.median(np.diff(t_s))
    return 100.0 if step < 0.015 else (50.0 if step < 0.03 else 25.0)   # some AirPods models stream at 25 Hz


# ----------------------------------------------------------------- collector v3 -----------------------------------
SWITCH_MIN_GAP_S = 0.5      # Apple pauses about 1 s when the streaming bud is taken out (Mac test: 1.07 s)
SWITCH_MIN_ANGLE_DEG = 10.0  # the other bud sits at a different angle: gravity direction jumps across the gap


def find_earbud_switches(df, t):
    """Times (s) where the stream moved to the other earbud. After a switch the orientation reference resets and the
    sensor sits at a different angle, so the calibration (head frame) from before no longer applies.
    Uses the sensor_location column when present (Mac app CSV); otherwise (collector stream, which has no location)
    a gap of >= SWITCH_MIN_GAP_S, after which yaw restarts near 0 (new reference), with a gravity-direction jump
    of >= SWITCH_MIN_ANGLE_DEG across it. The yaw condition keeps ordinary dropouts during a motion from counting."""
    out = []
    if "sensor_location" in df and df.sensor_location.notna().any():
        loc = df.sensor_location.astype(str).to_numpy()
        for i in np.where(loc[1:] != loc[:-1])[0] + 1:
            out.append({"t_s": float(t[i]), "from": loc[i - 1], "to": loc[i], "how": "sensor_location"})
        return out
    g = df[["gravX", "gravY", "gravZ"]].to_numpy(float)
    g = g / np.linalg.norm(g, axis=1, keepdims=True)
    for i in np.where(np.diff(t) >= SWITCH_MIN_GAP_S)[0]:
        a, b = g[max(0, i - 4):i + 1].mean(0), g[i + 1:i + 6].mean(0)
        ang = np.degrees(np.arccos(np.clip(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)), -1, 1)))
        yaw_restart = "yaw" not in df or abs(float(df.yaw.iloc[i + 1])) < 0.05
        if ang >= SWITCH_MIN_ANGLE_DEG and yaw_restart:
            out.append({"t_s": float(t[i + 1]), "from": "?", "to": "?",
                        "how": f"gap {t[i + 1] - t[i]:.2f} s + gravity jump {ang:.0f} deg"})
    return out


def load_session(path, fs=None):
    """A collector v3 session folder, or a single stream CSV from the Mac app (no cues)."""
    path = Path(path)
    if path.is_dir() and not (path / "stream.csv").exists():
        # Gesture Collector app v2: one stream_NNN.csv per segment (a new segment after every resume)
        parts = sorted(path.glob("stream_*.csv"))
        if not parts:
            raise FileNotFoundError(f"no stream.csv or stream_*.csv in {path}")
        df = pd.concat([pd.read_csv(p) for p in parts], ignore_index=True)
    else:
        df = pd.read_csv(path / "stream.csv" if path.is_dir() else path)
    df = df.sort_values("sensor_ns").drop_duplicates("sensor_ns")
    t0 = int(df.sensor_ns.iloc[0])
    t = (df.sensor_ns.to_numpy(np.int64) - t0) / 1e9
    fs = fs or _estimate_fs(t)
    grid, X, valid = to_grid(t, df[CHANNELS].to_numpy(float), fs)
    source = "mac_app_csv" if not path.is_dir() else ("collector_v3" if (path / "stream.csv").exists()
                                                      else "gesture_collector_app")
    meta = {"source": source, "path": str(path)}
    if "sensor_location" in df:
        meta["sensor_location"] = df.sensor_location.value_counts().to_dict()
    meta["earbud_switches"] = find_earbud_switches(df, t)
    cues = None
    if path.is_dir():
        if (path / "session.json").exists():
            meta.update(json.loads((path / "session.json").read_text(encoding="utf-8")))
        if (path / "cues.csv").exists():
            cues = pd.read_csv(path / "cues.csv")
            if cues.get("sensor_ns_est") is None or cues.sensor_ns_est.isna().all():
                offset = int((df.host_ns - df.sensor_ns).min())
                cues["sensor_ns_est"] = cues.host_ns - offset
            cues["t_s"] = (cues.sensor_ns_est - t0) / 1e9
            if "shown_sensor_ns" in cues:   # app v2.1: when the cue was announced (people start from there)
                cues["shown_t_s"] = (cues.shown_sensor_ns - t0) / 1e9
        for name in ("activities", "gaps"):
            if (path / f"{name}.csv").exists():
                meta[name] = pd.read_csv(path / f"{name}.csv")
    return Recording(grid, X, fs, valid, meta, cues, t0)


# ----------------------------------------------------------------- EarSet -----------------------------------------
def earset_people():
    return sorted((p.name for p in EARSET.glob("P*") if p.is_dir()), key=lambda s: int(s[1:]))


def load_earset(pid, activity, ear="left", fs=50.0):
    """EarSet file -> Recording. Raw acc includes gravity; gravity is estimated with a 0.3 Hz low-pass
    (offline, zero-phase) and removed. No orientation channels (quat = NaN). Uses the longest contiguous chunk.
    Sign: a standard accelerometer at rest reads +1 g pointing UP (reaction force); Apple's Core Motion reports
    gravity pointing DOWN. We negate EarSet's acceleration so both sources share Apple's convention.
    Returns None if the file does not exist."""
    f = EARSET / pid / "EARBUDS" / f"{pid[1:]}-{activity}-imu-{ear}.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f, comment="#").dropna().sort_values("timestamp").drop_duplicates("timestamp")
    t = (df.timestamp.to_numpy(float) - df.timestamp.iloc[0]) / 1000
    cuts = np.r_[0, np.where(np.diff(t) > 0.5)[0] + 1, len(t)]
    a, b = max(zip(cuts[:-1], cuts[1:]), key=lambda ab: ab[1] - ab[0])
    t = t[a:b] - t[a]
    acc_total = -df[["ax", "ay", "az"]].to_numpy(float)[a:b] * 0.061e-3 * G    # m/s^2, Apple convention
    gyro = np.deg2rad(df[["gx", "gy", "gz"]].to_numpy(float)[a:b] * 17.5e-3)    # rad/s
    grid, raw, valid = to_grid(t, np.hstack([acc_total, gyro]), fs)
    bb, aa = butter(2, 0.3 / (fs / 2))
    grav = filtfilt(bb, aa, raw[:, :3], axis=0)
    X = np.hstack([raw[:, 3:], raw[:, :3] - grav, grav, np.full((len(grid), 4), np.nan)])
    meta = {"source": "earset", "subject": pid, "activity": activity, "ear": ear, "device": "EarSet prototype"}
    return Recording(grid, X, fs, valid, meta)


# ----------------------------------------------------------------- old AirPods takes ------------------------------
def load_old_takes(subject):
    """Our old AirPods Pro 2 data (Sensor Logger, 50 Hz, acc and gravity in m/s^2) -> list of Recordings, one per
    cued 2.5 s take, in recording order, meta['label'] = gesture. Subjects 1 and 4 have Excel-damaged timestamps,
    so a uniform 50 Hz is assumed for all."""
    df = pd.read_csv(OLD_RAW / f"subject{subject}.csv")
    df["start_ms"] = df.session_id.astype(str).str.extract(r"_(\d{13})$")[0].astype("int64")
    cols = ROT + ACC + GRAV + QUAT
    out = []
    for sid, g in sorted(df.groupby("session_id", sort=False), key=lambda kv: kv[1].start_ms.iloc[0]):
        X = g[cols].to_numpy(float)
        t = np.arange(len(X)) / 50.0
        out.append(Recording(t, X, 50.0, np.ones(len(X), bool),
                             {"source": "old_airpods", "subject": f"A{subject}", "label": g.label.iloc[0],
                              "take": sid, "device": "AirPods Pro 2"}))
    return out
