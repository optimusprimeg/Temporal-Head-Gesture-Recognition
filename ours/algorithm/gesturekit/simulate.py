"""Synthetic collector-v3 sessions, for testing the whole pipeline before real data exists.

Motion snippets and quiet signal come from our old AirPods takes (one subject), placed on a continuous timeline
the way collector_v3 cues them: reaction delay after each cue, random gaps, idle cues, calibration, cued commands,
a no-gesture block. The files mimic the collector exactly, including Sensor Logger's batching (host_ns = arrival
of a 1 s batch), a phone/PC clock offset, and short dropouts. Returns the ground truth for checking.
Old takes are double gestures; here they stand in for the single motions (fine for testing the mechanics).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .io import load_old_takes
from .recording import CHANNELS as REC_CHANNELS

OLD_TO_NEW = {"tilt_2x_left": "tilt_left", "tilt_2x_right": "tilt_right", "nod_2x_front": "nod_down",
              "circle_cw": "circle_cw", "circle_ccw": "circle_ccw"}
COLLECTOR_CHANNELS = ["yaw", "pitch", "roll", "quatX", "quatY", "quatZ", "quatW", "rotX", "rotY", "rotZ",
                      "accX", "accY", "accZ", "gravX", "gravY", "gravZ"]


class SnippetLibrary:
    def __init__(self, subject=2, seed=0):
        self.rng = np.random.default_rng(seed)
        takes = load_old_takes(subject)
        self.motion = {}
        self.idle = []
        for r in takes:
            lab = r.meta["label"]
            if lab in OLD_TO_NEW:
                g = np.linalg.norm(r.rot, axis=1)
                idx = np.where(g > 0.25 * g.max())[0]
                a, b = max(0, idx[0] - 5), min(len(r), idx[-1] + 6)
                self.motion.setdefault(OLD_TO_NEW[lab], []).append(r.X[a:b])
            elif lab == "idle":
                self.idle.append(r.X)
        allq = np.concatenate(self.idle)
        thr = np.percentile(np.linalg.norm(allq[:, :3], axis=1), 25)  # one threshold for the whole subject
        self.quiet = []  # contiguous stretches (>= 0.2 s) of genuinely still signal from the idle takes
        for x in self.idle:
            still = np.r_[np.linalg.norm(x[:, :3], axis=1) < thr, False]
            start = None
            for i, s in enumerate(still):
                if s and start is None:
                    start = i
                elif not s and start is not None:
                    if i - start >= 10:
                        self.quiet.append(x[start:i])
                    start = None
        if not self.quiet:
            raise ValueError("no still stretches found in the idle takes")

    def quiet_signal(self, n):
        parts, total = [], 0
        while total < n:
            x = self.quiet[self.rng.integers(len(self.quiet))]
            parts.append(x)
            total += len(x)
        return _smooth_join(parts)[:n]

    def motion_signal(self, name):
        lib = self.motion[name]
        return lib[self.rng.integers(len(lib))]

    def idle_signal(self, n):
        out = np.concatenate([self.idle[self.rng.integers(len(self.idle))] for _ in range(n // 100 + 2)])
        return out[:n]


def _smooth_join(parts, n_fade=5):
    """Concatenate signal pieces, blending the first n_fade samples of each piece into the previous level."""
    out = [parts[0]]
    for p in parts[1:]:
        p = p.copy()
        prev = out[-1][-1]
        w = np.linspace(0, 1, min(n_fade, len(p)))[:, None]
        p[:len(w)] = (1 - w) * prev + w * p[:len(w)]
        out.append(p)
    return np.concatenate(out)


def simulate_session(folder, motions=("nod_down", "tilt_left", "tilt_right", "circle_cw", "circle_ccw"),
                     rounds=6, commands=None, fs=50, subject=2, seed=0, drop_rate=0.01, clock_offset_s=1.234,
                     batch_s=1.0):
    rng = np.random.default_rng(seed)
    lib = SnippetLibrary(subject, seed)
    parts, cues, truth = [], [], []
    t = [0]  # current length in samples (list so the closures can update it)

    def add(x):
        parts.append(x)
        t[0] += len(x)

    def cue(kind, motion, window, rnd=0, step=0, note="", trial=None):
        cues.append({"t_true": t[0] / fs, "kind": kind, "motion": motion, "window_s": window, "round": rnd,
                     "step": step, "note": note, "trial": trial if trial is not None else len(cues) + 1,
                     "condition": "sitting", "block": kind})

    def motion_at_cue(name, window):
        delay = int(rng.uniform(0.3, 0.8) * fs)
        add(lib.quiet_signal(delay))
        m = lib.motion_signal(name)
        truth.append((t[0] / fs, (t[0] + len(m)) / fs, name))
        add(m)
        rest = int(window * fs) - delay - len(m)
        if rest > 0:
            add(lib.quiet_signal(rest))

    add(lib.quiet_signal(int(2 * fs)))
    cue("calibration", "still", 4.0)  # calibration: still, 3 nods
    add(lib.quiet_signal(int(4.5 * fs)))
    for i in range(3):
        cue("calibration", "calib_nod", 2.0, step=i + 1)
        motion_at_cue("nod_down", 2.5)
    trial = 0
    for r in range(1, rounds + 1):  # shuffled rounds with idle cues
        seq = list(motions) + ["idle", "idle"]
        rng.shuffle(seq)
        for m in seq:
            trial += 1
            cue("rounds", m, 4.0, rnd=r, trial=trial)
            if m == "idle":
                add(lib.quiet_signal(int(4.0 * fs)))
            else:
                motion_at_cue(m, 4.0)
            add(lib.quiet_signal(int(rng.uniform(2.5, 5.0) * fs)))
    for i, ((a, b), msg) in enumerate(sorted((commands or {}).items())[:5], 1):  # cued commands
        cue("commands", f"{a}>{b}", 6.0, rnd=i, note=msg)
        delay = int(rng.uniform(0.3, 0.8) * fs)
        add(lib.quiet_signal(delay))
        for k, name in enumerate((a, b)):
            m = lib.motion_signal(name)
            truth.append((t[0] / fs, (t[0] + len(m)) / fs, name))
            add(m)
            add(lib.quiet_signal(int(rng.uniform(0.3, 0.8) * fs)))
        add(lib.quiet_signal(int(4 * fs)))
    cue("negatives", "none", 60.0, note="idle-like activity")  # no-gesture block from idle takes
    add(lib.idle_signal(int(60 * fs)))
    add(lib.quiet_signal(int(2 * fs)))

    X = _smooth_join(parts)  # in Recording order: rot, acc, grav, quat
    n = len(X)
    t_true = np.arange(n) / fs
    keep = np.ones(n, bool)  # dropouts: short bursts
    for s in rng.choice(n, int(drop_rate * n / 10), replace=False):
        keep[s:s + rng.integers(5, 20)] = False
    keep[:10] = True  # keep t = 0 aligned with the truth table
    sensor0 = 1_790_000_000_000_000_000
    sensor_ns = sensor0 + (t_true * 1e9).astype(np.int64)
    batch_end = (np.floor(t_true / batch_s) + 1) * batch_s
    host_ns = sensor0 + ((batch_end + clock_offset_s + rng.uniform(0.03, 0.15, n)) * 1e9).astype(np.int64)
    cols = dict(zip(REC_CHANNELS, X.T))
    df = pd.DataFrame({"sensor_ns": sensor_ns, "host_ns": host_ns,
                       **{c: cols.get(c, np.zeros(n)) for c in COLLECTOR_CHANNELS}})[keep]
    offset = int((df.host_ns - df.sensor_ns).min())

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    df.to_csv(folder / "stream.csv", index=False)
    cdf = pd.DataFrame(cues)
    cdf["host_ns"] = sensor0 + ((cdf.t_true + clock_offset_s) * 1e9).astype(np.int64)  # cue on the PC clock
    cdf["sensor_ns_est"] = cdf.host_ns - offset                                          # as the collector does
    cdf[["host_ns", "sensor_ns_est", "block", "kind", "round", "trial", "step", "motion", "condition", "window_s",
         "note"]].to_csv(folder / "cues.csv", index=False)
    meta = {"subject": f"sim_A{subject}", "device": "simulated (old AirPods takes)", "plan": "simulated",
            "seed": seed, "main_motions": list(motions),
            "commands": {f"{a}>{b}": m for (a, b), m in (commands or {}).items()}}
    (folder / "session.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    truth_df = pd.DataFrame(truth, columns=["t_start", "t_end", "label"])
    truth_df.to_csv(folder / "truth.csv", index=False)
    return truth_df, (offset - clock_offset_s * 1e9) / 1e9
