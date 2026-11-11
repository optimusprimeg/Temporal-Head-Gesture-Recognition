"""Which facial micro-gestures could an earbud IMU pick up and tell apart? EarSet -> results/face_gestures_earset.md

EarSet has, per person, one ~2-minute recording per action (the action repeated): brow raise / lower, wink left /
right, eyes left-right / up-down, lip-corner puller (smile, closest to a smirk), chin raise, mouth stretch, plus the
head gestures nod / shake / tilt for comparison, and still.
EarSet has no event labels inside a recording, so per recording we take the 12 most active 1.5 s windows (at least
1.5 s apart) as that action's examples. Everything at 50 Hz (what AirPods give).

1. Detectable? Per person: median activity of the 12 windows / 95th percentile of their STILL recording's windows.
   Ratio >= 2 = clearly above sensor noise.
2. Tell apart on a NEW person? Leave one person out, logistic regression on frame-free window features (rotation and
   acceleration: rms, peak, high-frequency part, per-axis rms of the earbud), all 12 actions at once.
   LEFT EAR ONLY (AirPods stream one earbud at a time), and both ears for comparison.
3. Wink left vs right alone (the only left/right facial pair in EarSet), left ear only vs both ears.
Caveats: the "examples" are the most active windows, not labelled events; EarSet's earbud is not an AirPod
(raw IMU, different fit); people did each action on cue, repeatedly, not covertly.
Run from ours/algorithm: python scripts/face_gestures_earset.py
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gesturekit.io import earset_people, load_earset  # noqa: E402

FACE = ["brow-raiser", "brow-lowerer", "wink-l", "wink-r", "eyes-lr", "eyes-ud", "lip-puller", "chin-raiser",
        "mouth-stretch"]
HEAD = ["nod", "shake", "tilt"]
ACTS = FACE + HEAD
FS, WIN, HOP, TOP = 50, 75, 12, 12          # 1.5 s windows, 0.24 s hop, 12 per recording


def energy(rec):
    """Per-sample activity: rotation speed + acceleration magnitude (both NaN-safe)."""
    r = np.nan_to_num(np.linalg.norm(rec.rot, axis=1))
    a = np.nan_to_num(np.linalg.norm(rec.acc, axis=1))
    return r, a


def windows(n):
    return [(s, s + WIN) for s in range(0, max(n - WIN, 0), HOP)]


def feats(rec, a, b):
    rot, acc = np.nan_to_num(rec.rot[a:b]), np.nan_to_num(rec.acc[a:b])
    rm, am = np.linalg.norm(rot, axis=1), np.linalg.norm(acc, axis=1)
    hf = np.linalg.norm(np.diff(acc, axis=0), axis=1)
    f = [rm.mean(), rm.max(), np.sqrt((rm ** 2).mean()), am.mean(), am.max(), np.sqrt((am ** 2).mean()),
         hf.mean(), hf.max(), rm.max() / (am.max() + 1e-6)]
    f += list(np.sqrt((rot ** 2).mean(0))) + list(np.sqrt((acc ** 2).mean(0)))
    tot = (rot ** 2).sum(0)
    f += list(tot / (tot.sum() + 1e-9))
    return f


def top_windows(rec, still_scale):
    r, a = energy(rec)
    score = r / still_scale[0] + a / still_scale[1]
    ws = windows(len(score))
    s = np.array([score[x:y].mean() for x, y in ws])
    chosen = []
    for i in np.argsort(s)[::-1]:
        if all(abs(ws[i][0] - ws[j][0]) >= WIN for j in chosen):
            chosen.append(i)
        if len(chosen) == TOP:
            break
    return [ws[i] for i in chosen], s[chosen]


rows, det = [], []
for pid in earset_people():
    still = {e: load_earset(pid, "still", e) for e in ("left", "right")}
    if still["left"] is None:
        continue
    r, a = energy(still["left"])
    scale = (np.percentile(r, 50) + 1e-6, np.percentile(a, 50) + 1e-6)
    sr = r / scale[0] + a / scale[1]
    still_ref = np.percentile([sr[x:y].mean() for x, y in windows(len(sr))], 95)
    for act in ACTS:
        recs = {e: load_earset(pid, act, e) for e in ("left", "right")}
        if recs["left"] is None:
            continue
        ws, s = top_windows(recs["left"], scale)
        det.append({"person": pid, "action": act, "ratio": float(np.median(s) / still_ref)})
        for (x, y) in ws:
            fl = feats(recs["left"], x, y)
            fr = feats(recs["right"], x, y) if recs["right"] is not None and len(recs["right"].t) >= y else [np.nan] * len(fl)
            rows.append({"person": pid, "action": act, "left": fl, "right": fr})
    print(pid, end=" ", flush=True)
print()

D = pd.DataFrame(det)
W = pd.DataFrame(rows)
XL = np.array(W.left.tolist(), float)
XR = np.array(W.right.tolist(), float)
ok = ~np.isnan(XR).any(1)
XB = np.hstack([XL, np.nan_to_num(XR), np.log((XL[:, [2]] + 1e-6) / (np.nan_to_num(XR[:, [2]]) + 1e-6)),
                np.log((XL[:, [5]] + 1e-6) / (np.nan_to_num(XR[:, [5]]) + 1e-6))])
y, grp = W.action.to_numpy(), W.person.to_numpy()


def loso(X, y, grp, mask=None):
    mask = np.ones(len(y), bool) if mask is None else mask
    pred = np.empty(len(y), object)
    for p in np.unique(grp[mask]):
        te, tr = mask & (grp == p), mask & (grp != p)
        m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=0.5)).fit(X[tr], y[tr])
        pred[te] = m.predict(X[te])
    return pred


pL = loso(XL, y, grp)
pB = loso(XB, y, grp, ok)
wink = np.isin(y, ["wink-l", "wink-r"])
wL = loso(XL, y, grp, wink)
wB = loso(XB, y, grp, wink & ok)

res = []
for act in ACTS:
    m = y == act
    d = D[D.action == act]
    conf = pd.Series(pL[m]).value_counts()
    conf = conf.drop(act, errors="ignore")
    res.append({"action": act, "type": "head" if act in HEAD else "face",
                "people >= 2x still": f"{int((d.ratio >= 2).sum())}/{len(d)}",
                "median x still": round(float(d.ratio.median()), 1),
                "recall, left ear": round(float(np.mean(pL[m] == act)), 2),
                "recall, both ears": round(float(np.mean(pB[m & ok] == act)), 2),
                "most confused with (left ear)": ", ".join(f"{k} {v / m.sum():.0%}" for k, v in conf.head(2).items())})
R = pd.DataFrame(res).sort_values(["type", "recall, left ear"], ascending=[True, False])

chance = 1 / len(ACTS)
L = ["# Facial micro-gestures on an earbud IMU (EarSet, 30 people)", "",
     "Generated by `algorithm/scripts/face_gestures_earset.py` (method and caveats in its header). 50 Hz, the 12 most "
     "active 1.5 s windows per recording as examples, leave one person out, all 12 actions classified at once "
     f"(chance = {chance:.2f}). Head gestures are included as a reference.", "",
     R.to_markdown(index=False), "",
     f"Overall recall, left ear: {np.mean(pL == y):.2f}; both ears: {np.mean(pB[ok] == y[ok]):.2f}.", "",
     "## Wink left vs right (2 classes, chance 0.50)", "",
     f"- left ear only: {np.mean(wL[wink] == y[wink]):.2f}",
     f"- both ears: {np.mean(wB[wink & ok] == y[wink & ok]):.2f}", "",
     "`people >= 2x still`: people whose action windows are at least twice as active as the noisiest 5 % of their own "
     "still recording (below that, a detector cannot tell the action from sitting still).", ""]
out = ROOT / "results" / "face_gestures_earset.md"
out.write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
