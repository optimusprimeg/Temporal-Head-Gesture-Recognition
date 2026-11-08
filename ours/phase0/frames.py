"""Three ways to express a bout's motion, to test whether a head frame removes person/device bias (H1).

R0 sensor : the earbud's own axes (depends on how the bud sits in the ear and on the device)
R1 gravity: rotated so gravity points along +Z; heading (rotation about vertical) still unknown
R2 head   : R1, then rotated about Z so the axis of the person's calibration nods is +X (left-right axis).
            Needs a few nods at session start, as in our protocol.
"""
import numpy as np


def rotation_to_z(v):
    """Rotation matrix taking direction v onto +Z."""
    v = v / (np.linalg.norm(v) + 1e-12)
    z = np.array([0.0, 0.0, 1.0])
    axis, c = np.cross(v, z), float(np.dot(v, z))
    if np.linalg.norm(axis) < 1e-8:
        return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)


def rotation_about_z(angle):
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def gravity(X, start, n=25):
    """Mean acceleration (g) in the quiet just before a bout = gravity direction in sensor axes."""
    a = max(0, start - n)
    seg = X[a:start + 3, :3] if start - a >= 5 else X[start:start + n, :3]
    return seg.mean(axis=0)


def heading_from_nods(nod_gyros):
    """Angle (in the gravity frame's XY plane) of the main horizontal rotation axis of calibration nods."""
    W = np.concatenate(nod_gyros)[:, :2]
    _, _, vt = np.linalg.svd(W - W.mean(axis=0), full_matrices=False)
    ax = vt[0]
    return np.arctan2(ax[1], ax[0])


def first_lobe_sign(v, frac=0.3):
    """Sign of the first clear swing of a 1-D rotation-speed signal."""
    idx = np.where(np.abs(v) > frac * np.abs(v).max())[0]
    return np.sign(v[idx[0]]) if len(idx) else 0.0


def signed_heading_from_nods(nod_gyros):
    """Like heading_from_nods, but the axis sign is fixed so that each nod's first swing is positive about +X.

    The direction of a nod's first swing (chin down) is the same for everyone, so +X then means the same thing
    for every person and signed features (tilt left vs right, circle cw vs ccw) become comparable.
    """
    angle = heading_from_nods(nod_gyros)
    ax = np.array([np.cos(angle), np.sin(angle)])
    votes = sum(first_lobe_sign(g[:, :2] @ ax) for g in nod_gyros)
    return angle if votes >= 0 else angle + np.pi


def to_frame(X, start, end, frame, heading=None):
    """-> (acc_dyn (T,3) in g without gravity, gyro (T,3) rad/s) of X[start:end] in the chosen frame."""
    g = gravity(X, start)
    acc, gyro = X[start:end, :3] - g, X[start:end, 3:]
    if frame == "R0":
        return acc, gyro
    R = rotation_to_z(g)
    if frame == "R2":
        R = rotation_about_z(-heading) @ R
    return acc @ R.T, gyro @ R.T
