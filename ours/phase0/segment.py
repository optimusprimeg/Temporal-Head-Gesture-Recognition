"""Cut a recording into bouts of motion.

A sample is "active" when its motion score is well above a quiet level; active runs closer than MERGE_S are joined.
The score adds rotation speed and acceleration change, each divided by its quiet level, so it works for strong
head motion and weak face motion alike.

The quiet level should come from the person's own still recording (`quiet_reference`), like the still pose of our
calibration block. Without one, the recording's own 20th percentile is used; that hides continuous motion
(walking, chewing: the whole file looks "normal"), so do not use it to count false alarms.
Active runs longer than MAX_S are split into MAX_S pieces (an always-on detector would emit them), not dropped.
"""
import numpy as np
from scipy.ndimage import uniform_filter1d

from earset import FS

K = 4.0          # active when score > K x quiet level of the score
MERGE_S = 0.6    # join active runs separated by less than this
MIN_S, MAX_S = 0.3, 12.0  # some people repeat the motion for 6-10 s per cue
PAD_S = 0.2


def _parts(X):
    gyro = np.linalg.norm(X[:, 3:], axis=1)
    jerk = np.linalg.norm(np.diff(X[:, :3], axis=0, prepend=X[:1, :3]), axis=1)
    return uniform_filter1d(gyro, 5), uniform_filter1d(jerk, 5)


def quiet_reference(X_still):
    """(gyro, jerk, score) quiet levels from a recording of the person sitting still."""
    g, j = _parts(X_still)
    gq, jq = np.median(g) + 1e-6, np.median(j) + 1e-6
    return gq, jq, np.median(g / gq + j / jq)


def motion_score(X, ref=None):
    g, j = _parts(X)
    if ref is None:
        return g / (np.percentile(g, 20) + 1e-6) + j / (np.percentile(j, 20) + 1e-6)
    return g / ref[0] + j / ref[1]


def bouts(X, k=K, fs=FS, ref=None):
    """-> list of (start, end) sample indices. ref: quiet_reference(...) of the same person, or None."""
    s = motion_score(X, ref)
    active = s > k * (ref[2] if ref is not None else np.percentile(s, 20))
    out, t, T = [], 0, len(s)
    merge, longest, pad = int(MERGE_S * fs), int(MAX_S * fs), int(PAD_S * fs)
    while t < T:
        if not active[t]:
            t += 1
            continue
        a = t
        while t < T and (active[t] or active[t:t + merge].any()):
            t += 1
        b = t
        if b - a < MIN_S * fs:
            continue
        for c in range(a, b, longest):
            d = min(b, c + longest)
            if d - c >= MIN_S * fs:
                out.append((max(0, c - pad), min(T, d + pad)))
    return out
