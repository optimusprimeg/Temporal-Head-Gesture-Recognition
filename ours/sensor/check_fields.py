"""Check what Sensor Logger's AirPods columns really are, from our own recordings (not from docs).

Uses subject 2 and 3 of ../../prior_work/gesture_lab/data/raw (their timestamps are intact). Checks:
 1. sample rate
 2. quaternion is unit length; gravity magnitude (g or m/s^2?)
 3. Euler angles vs quaternion (which convention)
 4. gravity vector vs quaternion: is the quaternion's reference frame Z-up? (as logged, and with X,Z flipped)
 5. rotation rate vs the derivative of the quaternion (angular velocity in the quaternion's body axes; expect the
    X and Z correlations to be negative, i.e. the same X,Z flip)
 6. user acceleration units: tangential acceleration = radius x angular acceleration; fit the radius under
    "acc in g" and "acc in m/s^2" and see which gives a head-sized radius (5-15 cm)
"""
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path(__file__).resolve().parents[2] / "prior_work" / "gesture_lab" / "data" / "raw"


def qmul(a, b):
    w1, x1, y1, z1 = a.T
    w2, x2, y2, z2 = b.T
    return np.stack([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2], axis=1)


def rotmat(q):  # q = (w, x, y, z), body -> reference
    w, x, y, z = q.T
    return np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], -1),
                     np.stack([2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)], -1),
                     np.stack([2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)], -1)], 1)


def corr(a, b):
    return np.corrcoef(a, b)[0, 1]


for s in (2, 3):
    df = pd.read_csv(RAW / f"subject{s}.csv")
    print(f"\n===== subject {s}: {len(df)} rows, {df.session_id.nunique()} takes")
    ts = pd.to_numeric(df.timestamp, errors="coerce")
    dt = ts.groupby(df.session_id).diff().dropna() / 1e6
    print(f"1. sample step median {dt.median():.1f} ms -> {1000 / dt.median():.1f} Hz; "
          f"steps > 30 ms: {(dt > 30).mean():.1%}")

    q = df[["quatW", "quatX", "quatY", "quatZ"]].to_numpy()
    g = df[["gravX", "gravY", "gravZ"]].to_numpy()
    print(f"2. |quaternion| median {np.median(np.linalg.norm(q, axis=1)):.4f}; "
          f"|gravity| median {np.median(np.linalg.norm(g, axis=1)):.3f} (9.81 = m/s^2, 1.0 = g)")

    R = rotmat(q)
    # Apple CMAttitude: pitch about X, roll about Y, yaw about Z (Tait-Bryan, Z-X-Y order)
    pitch = np.arcsin(np.clip(R[:, 2, 1], -1, 1))
    roll = np.arctan2(-R[:, 2, 0], R[:, 2, 2])
    yaw = np.arctan2(-R[:, 0, 1], R[:, 1, 1])
    wrap = lambda d: np.abs((d + np.pi) % (2 * np.pi) - np.pi)
    print("3. Euler from quaternion (Apple Z-X-Y) vs logged, median abs error (rad): "
          f"pitch {np.median(wrap(pitch - df.pitch)):.4f}, roll {np.median(wrap(roll - df.roll)):.4f}, "
          f"yaw {np.median(wrap(yaw - df['yaw'])):.4f}")

    gu = g / np.linalg.norm(g, axis=1, keepdims=True)
    F = np.diag([-1.0, 1.0, -1.0])  # vector columns vs quaternion body axes: X and Z flipped (180 deg about Y)
    for name, M in [("as logged", np.eye(3)), ("X,Z flipped", F)]:
        g_ref = np.einsum("nij,nj->ni", R, gu @ M.T)  # gravity expressed in the quaternion's reference frame
        spread = pd.DataFrame(g_ref).groupby(df.session_id.to_numpy()).std().to_numpy().sum(1).mean()
        print(f"4. gravity in the quaternion's reference frame ({name}): mean z {g_ref[:, 2].mean():+.4f}, "
              f"spread within take {spread:.4f}  (z = -1 and spread 0 = reference frame is Z-up, gravity = -Z)")

    rot = df[["rotX", "rotY", "rotZ"]].to_numpy()
    acc = df[["accX", "accY", "accZ"]].to_numpy()
    rows_w, rows_body, rows_alpha, rows_acc = [], [], [], []
    for _, idx in df.groupby("session_id").indices.items():
        if len(idx) < 20:
            continue
        qi = q[idx]
        dq = np.gradient(qi, axis=0) * 50
        conj = qi * np.array([1, -1, -1, -1])
        w_body = 2 * qmul(conj, dq)[:, 1:]  # angular velocity in body (earbud) axes
        rows_w.append(rot[idx])
        rows_body.append(w_body)
        alpha = np.gradient(rot[idx], axis=0) * 50
        rows_alpha.append(np.linalg.norm(alpha, axis=1))
        rows_acc.append(np.linalg.norm(acc[idx], axis=1))
    W, B = np.concatenate(rows_w), np.concatenate(rows_body)
    keep = np.linalg.norm(B, axis=1) < 20  # drop quaternion sign flips
    print("5. rotation rate vs angular velocity from the quaternion (earbud axes), correlation per axis: "
          + ", ".join(f"{c} {corr(W[keep, i], B[keep, i]):.3f}" for i, c in enumerate("XYZ")))
    print(f"   median ratio |rot| / |from quaternion| during motion: "
          f"{np.median(np.linalg.norm(W[keep], axis=1)[np.linalg.norm(B[keep], axis=1) > 0.5] / np.linalg.norm(B[keep], axis=1)[np.linalg.norm(B[keep], axis=1) > 0.5]):.3f}")

    al, ac = np.concatenate(rows_alpha), np.concatenate(rows_acc)
    m = al > 2.0  # clear angular acceleration
    slope = np.sum(al[m] * ac[m]) / np.sum(al[m] ** 2)
    print(f"6. |user acc| ~ r * |angular acc|: slope {slope:.4f} -> radius {slope * 9.81 * 100:.1f} cm if acc in g, "
          f"{slope * 100:.2f} cm if acc in m/s^2 (a head is ~5-15 cm)")
