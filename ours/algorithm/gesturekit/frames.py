"""Head frame: express an event's motion in axes tied to the head, not to the earbud.

All sources follow Apple's convention: `grav` points DOWN in earbud axes (see io.py).
    +Z  up            (opposite to gravity measured just before the event; removes earbud tilt and posture)
    +X  nod axis      (main rotation axis of the person's calibration nods, in the horizontal plane)
    +Y  = Z x X
Sign of X: a nod's first swing (chin down) is positive about +X, the same instruction for everyone, so signed
features (left/right, cw/ccw) mean the same for every person and device.
Without a calibration (frame=None) only the gravity alignment is applied (heading stays arbitrary).
"""
from dataclasses import dataclass

import numpy as np

from .config import FrameConfig


def rotation_to(v, target):
    """Rotation matrix taking direction v onto direction target."""
    v = v / (np.linalg.norm(v) + 1e-12)
    target = target / np.linalg.norm(target)
    axis, c = np.cross(v, target), float(np.dot(v, target))
    if np.linalg.norm(axis) < 1e-8:
        if c > 0:
            return np.eye(3)
        perp = np.cross(v, [1.0, 0, 0]) if abs(v[0]) < 0.9 else np.cross(v, [0, 1.0, 0])
        perp /= np.linalg.norm(perp)
        return 2 * np.outer(perp, perp) - np.eye(3)  # 180 degrees about perp
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)


def rot_z(angle):
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def gravity_before(rec, start, cfg=FrameConfig()):
    """Gravity direction (unit, pointing down, earbud axes) from the valid samples just before `start`."""
    n = int(cfg.gravity_pre_s * rec.fs)
    a = max(0, start - n)
    idx = np.arange(a, max(start, a + 1))
    idx = idx[rec.valid[idx]] if rec.valid[idx].any() else idx
    g = rec.grav[idx].mean(axis=0)
    return g / (np.linalg.norm(g) + 1e-12)


def up_alignment(g_down):
    """Rotation taking 'up' (= -gravity) onto +Z."""
    return rotation_to(-g_down, np.array([0, 0, 1.0]))


@dataclass
class HeadFrame:
    heading: float          # angle of the nod axis in the gravity-aligned XY plane
    n_nods: int

    def matrix(self, g_down):
        return rot_z(-self.heading) @ up_alignment(g_down)


def _first_swing_sign(v, frac):
    idx = np.where(np.abs(v) > frac * np.abs(v).max())[0]
    return np.sign(v[idx[0]]) if len(idx) else 0.0


def calibrate(rec, nod_windows, cfg=FrameConfig()):
    """HeadFrame from calibration nods: list of (start, end) sample ranges, each one nod (chin down first)."""
    gyros = []
    for a, b in nod_windows:
        R = up_alignment(gravity_before(rec, a, cfg))
        gyros.append(rec.rot[a:b] @ R.T)
    W = np.concatenate(gyros)[:, :2]
    _, _, vt = np.linalg.svd(W - W.mean(axis=0), full_matrices=False)
    axis = vt[0]
    votes = sum(_first_swing_sign(g[:, :2] @ axis, cfg.first_swing_frac) for g in gyros)
    if votes < 0:
        axis = -axis
    return HeadFrame(float(np.arctan2(axis[1], axis[0])), len(nod_windows))


def to_head(rec, a, b, frame=None, cfg=FrameConfig()):
    """(acc, rot) of samples [a, b) in the head frame (or gravity frame if frame is None)."""
    g = gravity_before(rec, a, cfg)
    R = frame.matrix(g) if frame is not None else up_alignment(g)
    return rec.acc[a:b] @ R.T, rec.rot[a:b] @ R.T
