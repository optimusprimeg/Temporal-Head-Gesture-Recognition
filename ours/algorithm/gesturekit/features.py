"""Physical features of one event, in sets you can switch on and off (FeatureConfig.sets).

Every function takes (acc, rot, fs) in the head frame (frames.to_head) and returns a 1-D array.
    axis       which axis carries the rotation (unsigned)            Phase 0: gesture, not person
    signed     direction of the first swing, loop direction per plane  left/right, cw/ccw
    timing     number and spacing of rotation / acceleration peaks, high-frequency acceleration
    magnitude  speed, size, duration, repeat count                   Phase 0: mostly PERSON, normalise per person
Add a set by writing a function and registering it in FEATURE_SETS.
"""
import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks


def axis_features(acc, rot, fs):
    e = (rot ** 2).sum(axis=0)
    share = e / (e.sum() + 1e-12)
    ev = np.linalg.eigvalsh(np.cov(rot.T))[::-1] if len(rot) > 2 else np.array([1.0, 0, 0])
    linearity = ev[0] / (ev.sum() + 1e-12)  # 1 = rotation about one fixed axis
    return np.array([*share, linearity])


def _first_lobe(v, frac=0.3):
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
    return v[a:b].sum()


def _loop(u, w):
    """Signed area enclosed by the closed path (u, w), as a share of the circle at the path's peak radius:
    +1 = one full counter-clockwise circle, ~0 for a one-axis motion (a thin out-and-back loop encloses almost
    nothing). Independent of event length and sample rate (fixed 2026-11-08: the old form divided the area by
    the SUM of squared radii, so a 4 s circle scored a quarter of a 1 s one)."""
    if len(u) == 0:
        return 0.0
    uu, ww = np.r_[u, u[:1]], np.r_[w, w[:1]]  # closed path (shoelace)
    area = 0.5 * np.sum(uu[:-1] * ww[1:] - uu[1:] * ww[:-1])
    return area / (np.pi * np.max(u ** 2 + w ** 2) + 1e-9)


def signed_features(acc, rot, fs):
    x, y, z = rot.T
    return np.array([_first_lobe(x) / fs, _first_lobe(y) / fs, _first_lobe(z) / fs,
                     _loop(x, y), _loop(x, z), _loop(y, z)])


def _peaks(env, fs):
    if env.max() <= 0:
        return 0, 0.0
    p, _ = find_peaks(env, height=0.4 * env.max(), distance=max(1, int(0.25 * fs)))
    return len(p), (np.diff(p).mean() / fs if len(p) > 1 else 0.0)


def timing_features(acc, rot, fs):
    rot_env = uniform_filter1d(np.linalg.norm(rot, axis=1), 5)
    jerk = np.linalg.norm(np.diff(acc, axis=0, prepend=acc[:1]), axis=1)
    hf = np.sqrt((jerk ** 2).mean()) * fs
    rot_rms = np.sqrt((np.linalg.norm(rot, axis=1) ** 2).mean())
    return np.array([*_peaks(rot_env, fs), *_peaks(uniform_filter1d(jerk, 5), fs), hf, hf / (rot_rms + 1e-3)])


def magnitude_features(acc, rot, fs):
    mag = np.linalg.norm(rot, axis=1)
    dur = len(rot) / fs
    main = rot @ np.linalg.svd(rot - rot.mean(axis=0), full_matrices=False)[2][0]
    main = main[np.abs(main) > 0.15 * np.abs(main).max()] if np.abs(main).max() > 0 else main
    n_cycles = np.sum(np.diff(np.sign(main)) != 0) / 2
    rms = np.sqrt((mag ** 2).mean())
    acc_rms = np.sqrt((np.linalg.norm(acc, axis=1) ** 2).mean())
    return np.array([mag.max(), rms, dur, n_cycles / dur, n_cycles, acc_rms / (rms + 1e-9)])


FEATURE_SETS = {
    "axis": (axis_features, ["share_x", "share_y", "share_z", "linearity"]),
    "signed": (signed_features, ["first_lobe_x", "first_lobe_y", "first_lobe_z", "loop_xy", "loop_xz", "loop_yz"]),
    "timing": (timing_features, ["rot_peaks", "rot_peak_gap_s", "acc_peaks", "acc_peak_gap_s", "acc_hf_rms",
                                 "acc_hf_per_rot"]),
    "magnitude": (magnitude_features, ["peak_rot", "rms_rot", "duration_s", "cycles_per_s", "n_cycles",
                                       "acc_per_rot"]),
}


def feature_names(sets):
    return [n for s in sets for n in FEATURE_SETS[s][1]]


def event_features(acc, rot, fs, sets=("axis", "signed", "timing")):
    return np.concatenate([FEATURE_SETS[s][0](acc, rot, fs) for s in sets])
