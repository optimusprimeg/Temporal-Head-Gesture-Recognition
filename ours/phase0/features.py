"""Physically meaningful features of one bout (acc_dyn, gyro already in a frame).

All are unsigned, so the sign ambiguity of the calibration axis does not matter, and none depend on
absolute time or posture.
"""
import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks

FS = 50

NAMES = ["share_x", "share_y", "share_z", "planarity", "peak_rot", "rms_rot", "duration_s",
         "cycles_per_s", "n_cycles", "acc_per_rot"]


def bout_features(acc, gyro, fs=FS):
    e = (gyro ** 2).sum(axis=0)
    share = e / (e.sum() + 1e-12)                       # which axis carries the rotation
    ev = np.linalg.eigvalsh(np.cov(gyro.T))[::-1]
    planarity = ev[0] / (ev.sum() + 1e-12)              # 1 = rotation about one axis only
    mag = np.linalg.norm(gyro, axis=1)
    dur = len(gyro) / fs
    _, _, vt = np.linalg.svd(gyro - gyro.mean(axis=0), full_matrices=False)
    main = gyro @ vt[0]                                  # rotation speed about the main axis
    main = main[np.abs(main) > 0.15 * np.abs(main).max()]
    n_cycles = np.sum(np.diff(np.sign(main)) != 0) / 2
    acc_rms = np.sqrt((np.linalg.norm(acc, axis=1) ** 2).mean())
    return np.array([*share, planarity, mag.max(), np.sqrt((mag ** 2).mean()), dur,
                     n_cycles / dur, n_cycles, acc_rms / (np.sqrt((mag ** 2).mean()) + 1e-9)])


# --- signed and timing features for the hard cases (need the signed head frame, frames.signed_heading_from_nods) ---

SIGNED_NAMES = ["first_lobe_x", "first_lobe_y", "first_lobe_z", "loop_xy", "loop_xz", "loop_yz"]
TIMING_NAMES = ["rot_peaks", "rot_peak_gap_s", "acc_peaks", "acc_peak_gap_s", "acc_hf_rms", "acc_hf_per_rot"]


def _first_lobe(v, frac=0.3):
    """Signed area (rad) of the first clear swing: from its start until the speed changes sign."""
    idx = np.where(np.abs(v) > frac * np.abs(v).max())[0]
    if not len(idx):
        return 0.0
    i, s = idx[0], np.sign(v[idx[0]])
    a = i
    while a > 0 and np.sign(v[a - 1]) == s:
        a -= 1
    b = i
    while b < len(v) and np.sign(v[b]) == s:
        b += 1
    return v[a:b].sum() / FS


def _loop(u, w):
    """Signed area enclosed by the rotation-speed path in the (u, w) plane (closed back to its start, shoelace),
    per unit energy: + = counter-clockwise."""
    uu, ww = np.r_[u, u[:1]], np.r_[w, w[:1]]
    area = 0.5 * np.sum(uu[:-1] * ww[1:] - uu[1:] * ww[:-1])
    return area / (np.sum(u ** 2 + w ** 2) + 1e-9)


def _peaks(env, fs=FS):
    p, _ = find_peaks(env, height=0.4 * env.max(), distance=int(0.25 * fs))
    return len(p), (np.diff(p).mean() / fs if len(p) > 1 else 0.0)


def signed_features(acc, gyro):
    x, y, z = gyro.T
    return np.array([_first_lobe(x), _first_lobe(y), _first_lobe(z), _loop(x, y), _loop(x, z), _loop(y, z)])


def timing_features(acc, gyro, fs=FS):
    rot_env = uniform_filter1d(np.linalg.norm(gyro, axis=1), 5)
    jerk = np.linalg.norm(np.diff(acc, axis=0, prepend=acc[:1]), axis=1)
    acc_env = uniform_filter1d(jerk, 5)
    hf = np.sqrt((jerk ** 2).mean()) * fs                 # g/s, high-frequency acceleration (jaw shows here)
    rot_rms = np.sqrt((np.linalg.norm(gyro, axis=1) ** 2).mean())
    return np.array([*_peaks(rot_env), *_peaks(acc_env), hf, hf / (rot_rms + 1e-3)])
