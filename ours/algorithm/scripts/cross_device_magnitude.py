"""Do speed/size features carry over from EarSet's earbud to our AirPods? -> results/cross_device_magnitude.md

The enrollment-curve test (results/enrollment_curve.md) found that raw speed/size features cut wrongly accepted
non-gestures 3x on EarSet, with no personal data. Before adding them to the app, check the device change: train on
all 30 EarSet people (their earbud), test on P01's AirPods Pro 2 recordings.

Test data (P01, AirPods Pro 2, Mac app; one person, so a sanity check):
  gestures   app-session motions + earlier Mac recording, mapped to EarSet's classes (nod_down/look_up -> nod,
             turn -> shake, tilt -> tilt; circles left out: EarSet has none; the held nods of the earlier recording
             left out, as before)
  none       every event in P01's talking recording and still recording, and events in the app session's
             "nothing" cues
Also compares the feature scales (medians per class) between the two devices.
Run from ours/algorithm: python scripts/cross_device_magnitude.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import person_report as pr  # noqa: E402
from gesturekit.config import PipelineConfig  # noqa: E402
from gesturekit.detect import quiet_from  # noqa: E402
from gesturekit.features import FEATURE_SETS  # noqa: E402
from gesturekit.io import load_session  # noqa: E402
from gesturekit.label import label_events  # noqa: E402
from gesturekit.pipeline import Calibration, Pipeline  # noqa: E402

DATA = ROOT.parent / "data" / "internal GG 01"
SESSION = DATA / "P01_ghanshyam_s1_airpodspro2_20261107_024251" / "P01_ghanshyam_s1_airpodspro2_20261107_024251"
EARLIER = (DATA / "airpods_20261107_004637.csv", DATA / "airpods_20261107_004637.labels.csv",
           DATA / "airpods_20261107_002835.csv")
NONE_FILES = [DATA / "airpods_20261107_003545.csv", DATA / "airpods_20261107_002835.csv"]   # talking, still
NAMES = [n for s in ("axis", "signed", "timing", "magnitude") for n in FEATURE_SETS[s][1]]
GESTURE_F = [n for s in ("axis", "signed", "timing") for n in FEATURE_SETS[s][1]]
PERSON_F = FEATURE_SETS["magnitude"][1]
TO_EARSET = {"nod_down": "nod", "look_up": "nod", "turn_left": "shake", "turn_right": "shake",
             "tilt_left": "tilt", "tilt_right": "tilt"}

earset = pd.read_csv(ROOT / "results" / "earset_events.csv")

# ---------------- P01 gestures
rec, p, ev, _, df = pr.session_events(str(SESSION), 1.5)
app = df[(df.nth == 0) & df.label.isin(TO_EARSET)].copy()
app["label"], app["source"] = app.label.map(TO_EARSET), "app session"
cfg = PipelineConfig(); cfg.features.sets = ("axis", "signed", "timing", "magnitude")
old = pr.earlier_events(*map(str, EARLIER), cfg)
old = old[old.label.isin(TO_EARSET) & (old.label != "nod_down")].copy()
old["label"], old["source"] = old.label.map(TO_EARSET), "earlier recording"

# ---------------- P01 no-gesture events
still = load_session(str(EARLIER[2]))
q = quiet_from(still, 0, len(still))
none_rows = []
for f in NONE_FILES:
    tp = Pipeline(cfg); tp.calibrations = [Calibration(0.0, q, None)]
    for e in tp.extract(load_session(str(f))):
        none_rows.append({**dict(zip(NAMES, e.features)), "label": "none", "source": f.name})
cues = rec.cues.copy(); cues.loc[cues.kind == "practice", "kind"] = "rounds"
labels, _ = label_events(ev, cues, p.cfg.label)
for e, lab in zip(ev, labels):
    if lab == "none":
        none_rows.append({**dict(zip(NAMES, e.features)), "label": "none", "source": "app session nothing cues"})
none = pd.DataFrame(none_rows)
test = pd.concat([app, old, none], ignore_index=True)


def model():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=4000, class_weight="balanced"))


def evaluate(cols):
    m = model().fit(earset[cols], earset.label)
    pr_ = m.predict_proba(test[cols])
    o = np.argsort(pr_, axis=1)[:, ::-1]
    top = pr_[np.arange(len(pr_)), o[:, 0]]
    margin = top - pr_[np.arange(len(pr_)), o[:, 1]]
    pred = np.array(m.classes_)[o[:, 0]]
    acc = (pred != "none") & (top >= 0.5) & (margin >= 0.1)
    g = test.label != "none"
    return {"gestures right": f"{int(((pred == test.label) & acc)[g].sum())}/{int(g.sum())}",
            "no-gesture accepted": f"{int(acc[~g].sum())}/{int((~g).sum())}",
            "gestures called none or rejected": f"{int((~acc)[g].sum())}/{int(g.sum())}"}


res = pd.DataFrame({"gesture features": evaluate(GESTURE_F), "+ speed/size (raw)": evaluate(GESTURE_F + PERSON_F)}).T

scale = []
for name, d in (("EarSet", earset), ("P01 AirPods", test)):
    for lab in ["nod", "shake", "tilt", "none"]:
        s = d[d.label == lab]
        if len(s):
            scale.append({"device": name, "class": lab, "n": len(s),
                          **{f: round(float(s[f].median()), 2) for f in ["peak_rot", "rms_rot", "duration_s", "n_cycles", "acc_per_rot"]}})
scale = pd.DataFrame(scale).set_index(["class", "device"]).sort_index()

L = ["# Speed/size features across devices: EarSet earbud → P01's AirPods", "",
     "Generated by `algorithm/scripts/cross_device_magnitude.py` (data and caveats in its header). Trained on all 30 "
     "EarSet people, tested on P01 (AirPods Pro 2). App gate 0.5 / 0.1. One person, few no-gesture events: a "
     "sanity check of the device change, not a result.", "",
     res.to_markdown(), "",
     f"Test events: {int((test.label != 'none').sum())} gestures, {int((test.label == 'none').sum())} no-gesture "
     f"({', '.join(f'{k} {v}' for k, v in none.source.value_counts().items())}).", "",
     "## Feature scales (medians)", "", scale.to_markdown(), ""]
(ROOT / "results" / "cross_device_magnitude.md").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
