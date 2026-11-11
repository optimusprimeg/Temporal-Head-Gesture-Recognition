"""Our head-motion features, in one file, for the receiver code (secret_receiver_*.py, train_model.py).

Drop-in: needs only numpy, pandas and scipy. Uses the same sample keys as the receiver:
    rotX rotY rotZ   rad/s   rotation rate, earbud axes
    accX accY accZ   m/s^2   user acceleration (gravity removed)
    gravX gravY gravZ m/s^2  gravity (Apple convention: points DOWN)
yaw / pitch / roll are NOT used on purpose: they depend on where the person was facing when the stream started and
on how the earbud sits, so they describe the person, not the gesture.

What is different from the 96 receiver features (12 channels x mean/std/min/max/...):
  1. Head frame. Every event is first rotated so that +Z = up (gravity just before the motion) and, if the person did
     3 calibration nods, +X = their nod axis. Then "rotation about X" means nod for everyone, whatever the earbud
     angle, ear, posture or device.
  2. Shape, not size. The core features are RATIOS (what share of the rotation is about each head axis, how
     circular the path is). A small slow nod and a big fast nod give the same numbers, so they carry over to a new
     person. Size/speed features exist too (magnitude set) but are mostly person, not gesture: use with care.
  3. Direction from one sign. Left vs right, down vs up, cw vs ccw = the sign of the first swing / of the loop.

Usage in a receiver (event = list of sample dicts, like `samples` in classify_event):
    from our_features import event_features, rule_classify
    f = event_features(samples, fs=50)            # dict of named features
    print(rule_classify(f))                       # e.g. "tilt_left" or "none"

With calibration (recommended; 3 nods, chin down first, each as a list of sample dicts):
    heading = calibrate_heading([nod1, nod2, nod3])
    f = event_features(samples, fs=50, heading=heading)

Training: build a DataFrame of event_features(...) per take and fit any classifier on FEATURES_CORE (+ others).
Feature definitions are in FEATURE_DOCS at the bottom. Copied from ours/algorithm/gesturekit (features.py,
frames.py); check there for the maintained version.
"""
import numpy as np
import pandas as pd
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks

ROT, ACC, GRAV = ["rotX", "rotY", "rotZ"], ["accX", "accY", "accZ"], ["gravX", "gravY", "gravZ"]
GRAVITY_PRE_S = 0.5     # gravity direction from this much data at the start of the event (or the pre-buffer)
FIRST_SWING_FRAC = 0.3  # a swing counts once it passes this share of the peak

# rules used in our live app (thresholds set on one person, P01: development values, not final)
AXIS_SHARE = 0.6
LOOP_MIN = 0.15
DIRECTION = {"nod": ("first_lobe_x", "nod_down", "look_up"), "tilt": ("first_lobe_y", "tilt_left", "tilt_right"),
             "turn": ("first_lobe_z", "turn_left", "turn_right"), "circle": ("loop_xz", "circle_cw", "circle_ccw")}


# ------------------------------------------------------------------------------------------------ input
def _arrays(samples):
    """list of sample dicts or a DataFrame -> (rot, acc, grav) float arrays (n, 3)."""
    df = samples if isinstance(samples, pd.DataFrame) else pd.DataFrame(list(samples))
    return (df[ROT].to_numpy(float), df[ACC].to_numpy(float), df[GRAV].to_numpy(float))


# ------------------------------------------------------------------------------------------------ head frame
def _rotation_to(v, target):
    """Rotation matrix taking direction v onto direction target."""
    v = v / (np.linalg.norm(v) + 1e-12)
    target = target / np.linalg.norm(target)
    axis, c = np.cross(v, target), float(np.dot(v, target))
    if np.linalg.norm(axis) < 1e-8:
        if c > 0:
            return np.eye(3)
        perp = np.cross(v, [1.0, 0, 0]) if abs(v[0]) < 0.9 else np.cross(v, [0, 1.0, 0])
        perp /= np.linalg.norm(perp)
        return 2 * np.outer(perp, perp) - np.eye(3)
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)


def _rot_z(angle):
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def _up_alignment(grav):
    """Rotation taking 'up' (= -mean gravity) onto +Z."""
    g = grav.mean(axis=0)
    return _rotation_to(-g / (np.linalg.norm(g) + 1e-12), np.array([0, 0, 1.0]))


def _first_swing_sign(v):
    idx = np.where(np.abs(v) > FIRST_SWING_FRAC * np.abs(v).max())[0]
    return np.sign(v[idx[0]]) if len(idx) else 0.0


def calibrate_heading(nods, fs=50):
    """Heading of the person's nod axis (radians) from calibration nods.
    nods: list of events (each a list of sample dicts / DataFrame), one nod each, CHIN DOWN FIRST."""
    gyros = []
    for nod in nods:
        rot, _, grav = _arrays(nod)
        gyros.append(rot @ _up_alignment(grav[: max(1, int(GRAVITY_PRE_S * fs))]).T)
    W = np.concatenate(gyros)[:, :2]
    axis = np.linalg.svd(W - W.mean(axis=0), full_matrices=False)[2][0]
    if sum(_first_swing_sign(g[:, :2] @ axis) for g in gyros) < 0:
        axis = -axis
    return float(np.arctan2(axis[1], axis[0]))


def to_head(samples, fs=50, heading=None, pre=None):
    """(acc, rot) of an event in the head frame. Gravity from `pre` (samples just before the event) if given, else
    from the first GRAVITY_PRE_S of the event. heading=None: only 'up' is fixed (X/Y point an arbitrary way)."""
    rot, acc, grav = _arrays(samples)
    g = _arrays(pre)[2] if pre is not None and len(pre) else grav[: max(1, int(GRAVITY_PRE_S * fs))]
    R = _up_alignment(g)
    if heading is not None:
        R = _rot_z(-heading) @ R
    return acc @ R.T, rot @ R.T


# ------------------------------------------------------------------------------------------------ features
def _first_lobe(v):
    idx = np.where(np.abs(v) > FIRST_SWING_FRAC * np.abs(v).max())[0]
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
    if len(u) == 0:
        return 0.0
    uu, ww = np.r_[u, u[:1]], np.r_[w, w[:1]]
    area = 0.5 * np.sum(uu[:-1] * ww[1:] - uu[1:] * ww[:-1])
    return area / (np.pi * np.max(u ** 2 + w ** 2) + 1e-9)


def _peaks(env, fs):
    if env.max() <= 0:
        return 0, 0.0
    p, _ = find_peaks(env, height=0.4 * env.max(), distance=max(1, int(0.25 * fs)))
    return len(p), (np.diff(p).mean() / fs if len(p) > 1 else 0.0)


def features_from_head(acc, rot, fs=50):
    """All features from (acc, rot) already in the head frame. Returns a dict."""
    f = {}
    e = (rot ** 2).sum(axis=0)
    share = e / (e.sum() + 1e-12)
    ev = np.linalg.eigvalsh(np.cov(rot.T))[::-1] if len(rot) > 2 else np.array([1.0, 0, 0])
    f.update(share_x=share[0], share_y=share[1], share_z=share[2], linearity=ev[0] / (ev.sum() + 1e-12))

    x, y, z = rot.T
    f.update(first_lobe_x=_first_lobe(x) / fs, first_lobe_y=_first_lobe(y) / fs, first_lobe_z=_first_lobe(z) / fs,
             loop_xy=_loop(x, y), loop_xz=_loop(x, z), loop_yz=_loop(y, z))
    f.update(abs_loop_xy=abs(f["loop_xy"]), abs_loop_xz=abs(f["loop_xz"]), abs_loop_yz=abs(f["loop_yz"]))

    rot_env = uniform_filter1d(np.linalg.norm(rot, axis=1), 5)
    jerk = np.linalg.norm(np.diff(acc, axis=0, prepend=acc[:1]), axis=1)
    hf = np.sqrt((jerk ** 2).mean()) * fs
    rot_rms = np.sqrt((np.linalg.norm(rot, axis=1) ** 2).mean())
    f["rot_peaks"], f["rot_peak_gap_s"] = _peaks(rot_env, fs)
    f["acc_peaks"], f["acc_peak_gap_s"] = _peaks(uniform_filter1d(jerk, 5), fs)
    f.update(acc_hf_rms=hf, acc_hf_per_rot=hf / (rot_rms + 1e-3))

    mag = np.linalg.norm(rot, axis=1)
    dur = len(rot) / fs
    main = rot @ np.linalg.svd(rot - rot.mean(axis=0), full_matrices=False)[2][0]
    main = main[np.abs(main) > 0.15 * np.abs(main).max()] if np.abs(main).max() > 0 else main
    n_cycles = np.sum(np.diff(np.sign(main)) != 0) / 2
    acc_rms = np.sqrt((np.linalg.norm(acc, axis=1) ** 2).mean())
    f.update(peak_rot=mag.max(), rms_rot=rot_rms, duration_s=dur, cycles_per_s=n_cycles / dur, n_cycles=n_cycles,
             acc_per_rot=acc_rms / (rot_rms + 1e-9))
    return {k: float(v) for k, v in f.items()}


def event_features(samples, fs=50, heading=None, pre=None):
    """Named features of one motion event (list of sample dicts or DataFrame with rotX.. accX.. gravX..)."""
    acc, rot = to_head(samples, fs, heading, pre)
    return features_from_head(acc, rot, fs)


def features_frame(samples, fs=50, heading=None, pre=None, columns=None):
    """Same as event_features but a 1-row DataFrame (like extract_live_features in the receiver)."""
    f = pd.DataFrame([event_features(samples, fs, heading, pre)])
    return f[columns] if columns is not None else f


# ------------------------------------------------------------------------------------------------ rules
def rule_kind(f):
    shares = [f["share_x"], f["share_y"], f["share_z"]]
    i = int(np.argmax(shares))
    if shares[i] >= AXIS_SHARE:
        return ["nod", "tilt", "turn"][i]
    if max(f["abs_loop_xy"], f["abs_loop_xz"], f["abs_loop_yz"]) >= LOOP_MIN:
        return "circle"
    return "none"


def rule_classify(f):
    """One single motion: nod_down / look_up / tilt_left / tilt_right / turn_left / turn_right / circle_cw /
    circle_ccw / none. Directions need the calibration heading (except turn, which needs only gravity)."""
    kind = rule_kind(f)
    if kind == "none":
        return "none"
    key, pos, neg = DIRECTION[kind]
    return pos if f[key] > 0 else neg


# ------------------------------------------------------------------------------------------------ docs
FEATURES_CORE = ["share_x", "share_y", "share_z", "linearity", "abs_loop_xy", "abs_loop_xz", "abs_loop_yz"]
FEATURES_DIRECTION = ["first_lobe_x", "first_lobe_y", "first_lobe_z", "loop_xy", "loop_xz", "loop_yz"]
FEATURES_TIMING = ["rot_peaks", "rot_peak_gap_s", "acc_peaks", "acc_peak_gap_s", "acc_hf_rms", "acc_hf_per_rot"]
FEATURES_MAGNITUDE = ["peak_rot", "rms_rot", "duration_s", "cycles_per_s", "n_cycles", "acc_per_rot"]
FEATURE_DOCS = {
    "share_x": "share of rotation energy about the head X axis (nod axis); 0..1, shares sum to 1",
    "share_y": "share about head Y (tilt / roll axis)",
    "share_z": "share about head Z (up axis: turn / shake)",
    "linearity": "1 = rotation about one fixed axis; lower = axis changes (circle, wobble)",
    "abs_loop_xy": "|area enclosed by the rotation path in the X-Y plane| / circle at its peak radius; 1 = circle",
    "abs_loop_xz": "same in X-Z (the plane of a head circle)",
    "abs_loop_yz": "same in Y-Z",
    "first_lobe_x": "signed angle (rad) of the first swing about X: + = chin down",
    "first_lobe_y": "signed angle of the first swing about Y: + = tilt left",
    "first_lobe_z": "signed angle of the first swing about Z: + = turn left",
    "loop_xy": "signed loop (direction of travel) in X-Y", "loop_xz": "signed loop in X-Z: + = clockwise circle",
    "loop_yz": "signed loop in Y-Z",
    "rot_peaks": "number of rotation-speed peaks (1 swing out and back = 2)",
    "rot_peak_gap_s": "mean time between rotation peaks",
    "acc_peaks": "number of acceleration-change peaks", "acc_peak_gap_s": "mean time between them",
    "acc_hf_rms": "high-frequency acceleration (jerk) level: taps, jaw, footsteps",
    "acc_hf_per_rot": "jerk per unit rotation: high = shock without turning (tap, step)",
    "peak_rot": "peak rotation speed (rad/s) - PERSON-dependent", "rms_rot": "rms rotation speed - PERSON",
    "duration_s": "event length - PERSON", "cycles_per_s": "back-and-forth cycles per second",
    "n_cycles": "back-and-forth cycles (single nod ~1, double ~2)",
    "acc_per_rot": "translation per unit rotation",
}
