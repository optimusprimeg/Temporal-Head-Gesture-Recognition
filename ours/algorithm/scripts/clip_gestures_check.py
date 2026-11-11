"""Gesture clips recorded on AirPods (one short clip per repetition): can our pipeline detect and name them, and can
any model tell them apart once recording-order effects are ruled out?  -> results/<name>.md

Reads either clip format we have (both local only, not in git):
  merged_gestures_20261109.csv       trial_id, label, sensor_location, rotationRateX.., accelerationX.., gravityX..
  micro_gesture_dataset_100hz.csv    session_id, label, rep_id, subject_id, rotX.., accX.., gravX.. (really 50 Hz)

1. SIGNAL      peak rotation and acceleration change vs the quietest 0.5 s of the same clip.
2. DETECTION   our causal detector (gesturekit.detect), quiet level from the quietest 0.5 s of the clip (stands in for
               the calibration still pose). OUR RULES: what the live head-motion rules call each detected event.
               A micro-gesture that gets a head-motion name would send a WRONG command in our system.
3. CLASSIFY    random forest, two splits: random 5-fold, and BY TIME (first 60 % of each gesture's clips train, last
               40 % test). Feature sets: ours (25, gravity frame), ours shape-only (19), receiver 96, and the
               CONFOUND CHECK = posture only (mean gravity direction, yaw/pitch/roll means, earbud if known).
               When every gesture was recorded in its own block of time, posture alone can 'recognise' the block.
               A gesture result counts only where it clearly beats the posture-only check.
4. LEFT/RIGHT  every *_left / *_right pair, same features and splits.
Usage: python scripts/clip_gestures_check.py <clips.csv> <output name>
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.fft import fft
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPO / "ours" / "handoff"))
import our_features as of  # noqa: E402
from gesturekit.config import DetectorConfig  # noqa: E402
from gesturekit.detect import Detector, Quiet  # noqa: E402

SRC = Path(sys.argv[1])
NAME = sys.argv[2] if len(sys.argv) > 2 else SRC.stem
d = pd.read_csv(SRC).rename(columns={
    "rotationRateX": "rotX", "rotationRateY": "rotY", "rotationRateZ": "rotZ",
    "accelerationX": "accX", "accelerationY": "accY", "accelerationZ": "accZ",
    "gravityX": "gravX", "gravityY": "gravY", "gravityZ": "gravZ"})
CLIP = "trial_id" if "trial_id" in d else "session_id"
TIME = "time" if "time" in d else "timestamp"
d = d.sort_values([CLIP, TIME])
FS = round(1e9 / d.groupby(CLIP)[TIME].apply(lambda t: np.median(np.diff(t))).median())
HAS_BUD = "sensor_location" in d
RCV = ["yaw", "pitch", "roll", "rotX", "rotY", "rotZ", "accX", "accY", "accZ", "gravX", "gravY", "gravZ"]


def short(lab):
    return lab.replace("_2x", "").replace("Tap_", "tap ").replace("pull_", "pull ").replace("_", " ")


def receiver_96(x):
    if len(x) > 100:
        s = (len(x) - 100) // 2
        x = x[s:s + 100]
    f = []
    for j in range(x.shape[1]):
        v = x[:, j]
        jerk = np.diff(v)
        spec = np.abs(fft(v))[: len(v) // 2]
        f += [v.mean(), v.std(), v.min(), v.max(), np.ptp(v), jerk.std(), np.abs(jerk).max(), (spec ** 2).sum() / len(v)]
    return f


rows = []
for cid, g in d.groupby(CLIP):
    if len(g) < FS:                       # under 1 s: broken clip
        continue
    rot, acc = g[of.ROT].to_numpy(float), g[of.ACC].to_numpy(float)
    sp = np.linalg.norm(rot, axis=1)
    jk = np.r_[0, np.linalg.norm(np.diff(acc, axis=0), axis=1)]
    k = int(0.5 * FS)
    i0 = int(np.argmin(np.convolve(sp, np.ones(k), "valid")))
    qg, qj = float(np.median(sp[i0:i0 + k])) + 1e-4, float(np.median(jk[i0:i0 + k])) + 1e-4
    q = Quiet(qg, qj, float(np.median(sp[i0:i0 + k] / qg + jk[i0:i0 + k] / qj)))
    det = Detector(DetectorConfig(fs=FS), q)
    evs = []
    for i in range(len(g)):
        evs += det.push(rot[i], acc[i])
    evs += det.flush()
    names = [of.rule_classify(of.event_features(g.iloc[a:b], FS, pre=g.iloc[max(0, a - int(0.5 * FS)):a]))
             for a, b in evs]
    gm = g[of.GRAV].to_numpy(float).mean(0)
    posture = list(gm / np.linalg.norm(gm)) + list(g[["yaw", "pitch", "roll"]].mean())
    if HAS_BUD:
        posture.append(float(g.sensor_location.iloc[0] == "left"))
    rows.append({"clip": cid, "label": short(g.label.iloc[0]), "t0": g[TIME].iloc[0],
                 "bud": g.sensor_location.iloc[0] if HAS_BUD else "?",
                 "rot_x_quiet": sp.max() / qg, "jerk_x_quiet": jk.max() / qj, "peak_rot": sp.max(),
                 "n_events": len(evs), "rule_names": names, "ours": of.event_features(g, FS),
                 "rcv": receiver_96(g[RCV].to_numpy(float)), "posture": posture})
T = pd.DataFrame(rows).sort_values(["label", "t0"]).reset_index(drop=True)
CLASSES = list(dict.fromkeys(T.sort_values("t0").label))
start = T.t0.min()
blocks = T.groupby("label").t0.agg(["min", "max"]).reindex(CLASSES)

L = [f"# {NAME}: gesture clips on AirPods", "",
     f"Generated by `algorithm/scripts/clip_gestures_check.py` (method in its header) from `{SRC.name}`. "
     f"{len(T)} clips, {FS:.0f} Hz, {d.subject_id.nunique() if 'subject_id' in d else 1} person(s), one session.", "",
     "Recording order (minutes from the start). One block per gesture means time, posture and fit change WITH the "
     "gesture:", "",
     pd.DataFrame({"clips": T.groupby("label").size().reindex(CLASSES),
                   "from min": ((blocks["min"] - start) / 6e10).round(1),
                   "to min": ((blocks["max"] - start) / 6e10).round(1),
                   **({"earbud": T.groupby("label").bud.agg(lambda s: "/".join(sorted(set(s)))).reindex(CLASSES)}
                      if HAS_BUD else {})}).to_markdown(), ""]

# ---------------------------------------------------------- 1 + 2
rows2 = []
for lab in CLASSES:
    g = T[T.label == lab]
    alln = [n for ns in g.rule_names for n in ns]
    named = [n for n in alln if n != "none"]
    rows2.append({"gesture": lab, "peak rotation (rad/s)": round(g.peak_rot.median(), 2),
                  "rotation x quiet": round(g.rot_x_quiet.median(), 1), "jerk x quiet": round(g.jerk_x_quiet.median(), 1),
                  "detector fires": f"{(g.n_events > 0).mean():.0%}",
                  "named as head motion": f"{len(named)}/{len(alln)}",
                  "names": ", ".join(f"{k} {v}" for k, v in pd.Series(named).value_counts().head(3).items())})
L += ["## 1-2. Signal, our detector, our head-motion rules", "",
      "x quiet = clip peak / the clip's quietest 0.5 s. A deliberate head nod peaks at about 1-3 rad/s. "
      "'named as head motion' = detected events our live rules would turn into a (wrong) command.", "",
      pd.DataFrame(rows2).to_markdown(index=False), ""]

# ---------------------------------------------------------- 3
y = T.label.to_numpy()
order = (T.groupby("label").cumcount() / T.groupby("label").label.transform("size")).to_numpy()
OUR = of.FEATURES_CORE + of.FEATURES_DIRECTION + of.FEATURES_TIMING + of.FEATURES_MAGNITUDE
SHAPE = of.FEATURES_CORE + of.FEATURES_DIRECTION + of.FEATURES_TIMING
SETS = {"ours (25)": pd.DataFrame(T.ours.tolist())[OUR].to_numpy(),
        "ours, shape only (19)": pd.DataFrame(T.ours.tolist())[SHAPE].to_numpy(),
        "receiver 96": np.array(T.rcv.tolist()),
        "CONFOUND CHECK: posture only": np.array(T.posture.tolist())}
rf = lambda: RandomForestClassifier(300, random_state=0, n_jobs=-1)  # noqa: E731


def evaluate(X, mask=None):
    mask = np.ones(len(y), bool) if mask is None else mask
    idx = np.where(mask)[0]
    pr = np.empty(len(y), object)
    for tr, te in StratifiedKFold(5, shuffle=True, random_state=0).split(X[idx], y[idx]):
        pr[idx[te]] = rf().fit(X[idx[tr]], y[idx[tr]]).predict(X[idx[te]])
    tr, te = mask & (order < 0.6), mask & (order >= 0.6)
    pt = rf().fit(X[tr], y[tr]).predict(X[te])
    return float(np.mean(pr[idx] == y[idx])), float(np.mean(pt == y[te])), pt, y[te]


res, conf, percls = [], None, {}
for name, X in SETS.items():
    r = evaluate(X)
    res.append({"features": name, "random folds": round(r[0], 2), "by time (last 40 %)": round(r[1], 2)})
    percls[name] = {c: round(float(np.mean(r[2][r[3] == c] == c)), 2) for c in CLASSES}
    if name == "ours (25)":
        conf = pd.crosstab(pd.Series(r[3], name="true"), pd.Series(r[2], name="predicted")).reindex(
            index=CLASSES, columns=CLASSES, fill_value=0)
L += [f"## 3. Which gesture is it? ({len(CLASSES)} classes, chance {1 / len(CLASSES):.2f}, same person)", "",
      "Trust a gesture score only where it is clearly above the posture-only check.", "",
      pd.DataFrame(res).to_markdown(index=False), "", "Per gesture, split by time (recall):", "",
      pd.DataFrame(percls).to_markdown(), "", "Confusions, ours (25), split by time:", "", conf.to_markdown(), ""]

# ---------------------------------------------------------- 4
pairs = []
for lab in CLASSES:
    if " left" in lab and lab.replace(" left", " right") in CLASSES:
        b = lab.replace(" left", " right")
        for bud in (sorted(T.bud.unique()) if HAS_BUD else ["?"]):
            m = T.label.isin([lab, b]).to_numpy() & (T.bud == bud).to_numpy()
            if m.sum() < 10 or T[m].label.nunique() < 2:
                continue
            for name in ["ours, shape only (19)", "receiver 96", "CONFOUND CHECK: posture only"]:
                r = evaluate(SETS[name], m)
                pairs.append({"pair": f"{lab} vs {b}", **({"earbud": bud} if HAS_BUD else {}), "clips": int(m.sum()),
                              "features": name, "random folds": round(r[0], 2), "by time": round(r[1], 2)})
if pairs:
    L += ["## 4. Left vs right (chance 0.50)", "", pd.DataFrame(pairs).to_markdown(index=False), ""]

out = ROOT / "results" / f"{NAME}.md"
out.write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
