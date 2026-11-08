"""Lever-arm check on P01: how much of the earbud acceleration does head rotation alone explain?
Run from ours/algorithm: python scripts/lever_arm_check.py (see PROJECT_REVIEW.md section 8)."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import person_report as pr
S = "../data/internal GG 01/P01_ghanshyam_s1_airpodspro2_20261107_024251/P01_ghanshyam_s1_airpodspro2_20261107_024251"
rec, p, ev, rep, df = pr.session_events(S, 1.5)
starts = {e.t_start: e for e in ev}
fs = rec.fs if hasattr(rec, "fs") else 50
rows = []
for _, r in df[df.nth == 0].iterrows():
    e = starts[r.t_start]; a, w = e.acc, e.rot
    dt = 1.0 / fs
    rows.append(dict(motion=r.label, peak_rot_dps=np.degrees(np.linalg.norm(w, axis=1).max()),
        net_yaw_deg=np.degrees(w[:, 2].sum() * dt), max_yaw_deg=np.degrees(np.abs(np.cumsum(w[:, 2]) * dt).max()),
        acc_lat=np.abs(a[:, 0]).max(), acc_nose=np.abs(a[:, 1]).max(), acc_up=np.abs(a[:, 2]).max(),
        acc_mag=np.linalg.norm(a, axis=1).max(), dur=e.t_end - e.t_start))
d = pd.DataFrame(rows)
print("fs", fs, "acc units check: |grav| =", float(np.linalg.norm(rec.grav, axis=1).mean()) if hasattr(rec, "grav") else "?")
print(d.groupby("motion").agg(["median", "max"]).round(2).T.to_string())

# ---- rigid-body check: how much of the earbud's acceleration does head rotation alone explain?
# a_ear = a_body + alpha x r + w x (w x r); with the body still (seated) a_body ~ 0, so fit r (lever arm) by least squares.
from scipy.signal import savgol_filter
def skew(v):
    x, y, z = v
    return np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
def design(w):
    ws = savgol_filter(w, 9, 2, axis=0)
    al = savgol_filter(w, 9, 2, deriv=1, delta=1 / fs, axis=0)
    return np.concatenate([skew(al[i]) + skew(ws[i]) @ skew(ws[i]) for i in range(len(w))]), ws
evs = [(r.label, starts[r.t_start]) for _, r in df[df.nth == 0].iterrows()]
order = np.arange(len(evs)); half = order % 2 == 0          # fit on even trials, test on odd ones
A = np.concatenate([design(e.rot)[0] for (_, e), h in zip(evs, half) if h])
b = np.concatenate([e.acc.reshape(-1) for (_, e), h in zip(evs, half) if h])
r, *_ = np.linalg.lstsq(A, b, rcond=None)
print("\nlever arm r (m), head frame [lateral, nose, up]:", r.round(3), " |r| =", round(float(np.linalg.norm(r)), 3))
out = []
for (lab, e), h in zip(evs, half):
    M, _ = design(e.rot); pred = (M @ r).reshape(-1, 3); a = e.acc
    out.append(dict(motion=lab, split="fit" if h else "test",
                    explained=1 - ((a - pred) ** 2).sum() / ((a - a.mean(0)) ** 2).sum(),
                    peak_acc=np.linalg.norm(a, axis=1).max(), peak_resid=np.linalg.norm(a - pred, axis=1).max()))
o = pd.DataFrame(out)
print(o.groupby(["split"])[["explained", "peak_acc", "peak_resid"]].median().round(2).to_string())
print(o[o.split == "test"].groupby("motion")[["explained", "peak_acc", "peak_resid"]].median().round(2).to_string())
