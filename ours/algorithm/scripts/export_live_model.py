"""Train the live recogniser's model and export it for the Gesture Collector app (live mode).

The live recogniser decides an event in two steps (the same in Rules mode and Model mode):
  1. KIND: nod / tilt / turn / circle / none
       Rules mode: dominant rotation axis (share >= AXIS_SHARE) -> nod/tilt/turn; else a clear loop -> circle; else none
       Model mode: logistic regression on length-independent head-frame features (exported here as JSON)
  2. DIRECTION from one sign (P01: every direction pair separated by it, p01_airpods_report.md section C):
       nod: first_lobe_x > 0 -> nod_down     tilt: first_lobe_y > 0 -> tilt_left
       turn: first_lobe_z > 0 -> turn_left   circle: loop_xz > 0 -> circle_cw

Training data: EarSet (30 people; nod / shake=turn / tilt / none from face, talking, chewing, walking, running...)
+ P01's app session and earlier Mac recordings (the only data with circles, and with real AirPods).
Retrain after the pilot by adding the new sessions here; the app loads live_model.json from its data folder, so a
new model needs no rebuild.

Writes:
  ../mac_app/GestureCollector/live_model.json         model + rule thresholds (copy into the app's data folder)
  ../mac_app/GestureCollector/Tests/parity.json        raw P01 events + the Python answers (Swift check in CI)
  results/live_model.md                                 how well each mode does, and on what
Run from ours/algorithm: python scripts/export_live_model.py
"""
import json
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
from gesturekit.pipeline import Calibration, Pipeline  # noqa: E402

DATA = ROOT.parent / "data" / "internal GG 01"
SESSION = DATA / "P01_ghanshyam_s1_airpodspro2_20261107_024251" / "P01_ghanshyam_s1_airpodspro2_20261107_024251"
EARLIER = (DATA / "airpods_20261107_004637.csv", DATA / "airpods_20261107_004637.labels.csv",
           DATA / "airpods_20261107_002835.csv")
TALKING = DATA / "airpods_20261107_003545.csv"          # P01 talking, no gestures
APP = ROOT.parent / "mac_app" / "GestureCollector"

KIND = {"nod": "nod", "shake": "turn", "tilt": "tilt", "none": "none",
        "nod_down": "nod", "look_up": "nod", "tilt_left": "tilt", "tilt_right": "tilt",
        "turn_left": "turn", "turn_right": "turn", "circle_cw": "circle", "circle_ccw": "circle"}
KINDS = ["nod", "tilt", "turn", "circle", "none"]
DIRECTION = {"nod": ("first_lobe_x", "nod_down", "look_up"), "tilt": ("first_lobe_y", "tilt_left", "tilt_right"),
             "turn": ("first_lobe_z", "turn_left", "turn_right"), "circle": ("loop_xz", "circle_cw", "circle_ccw")}
# Model features: all length-independent and cheap to compute live. Only the three axis shares pass the R keep
# rule (results/variance_components.md); linearity FAILED it (gesture share 0.24) and |loop| was never screened
# (EarSet has no circles). They are kept here as development inputs until the pilot's R run decides, and the
# rule thresholds below were set on P01's data: P01 numbers are development numbers, not a test.
# Magnitude (speed, size) is left out on purpose: R found it is mostly PERSON.
FEATURES = ["share_x", "share_y", "share_z", "linearity", "abs_loop_xy", "abs_loop_xz", "abs_loop_yz"]
AXIS_SHARE = 0.6     # rules: one axis carries at least this share of the rotation energy -> one-axis motion
LOOP_MIN = 0.15      # rules: otherwise a loop at least this big -> circle. |loop| = enclosed area / circle at the
                     # peak radius (1 = perfect circle). P01: circles median 0.28-0.44, one-axis motions <= 0.28
                     # max (medians 0.05-0.19). Set on P01 (2026-11-08, after the loop fix): development value.
NAMES = [n for s in ("axis", "signed", "timing", "magnitude") for n in FEATURE_SETS[s][1]]


def add_abs(df):
    for p in ("xy", "xz", "yz"):
        df[f"abs_loop_{p}"] = df[f"loop_{p}"].abs()
    return df


def rule_kind(r):
    shares = [r.share_x, r.share_y, r.share_z]
    i = int(np.argmax(shares))
    if shares[i] >= AXIS_SHARE:
        return ["nod", "tilt", "turn"][i]
    if max(r.abs_loop_xy, r.abs_loop_xz, r.abs_loop_yz) >= LOOP_MIN:
        return "circle"
    return "none"


def direction(kind, r):
    if kind == "none":
        return "none"
    f, pos, neg = DIRECTION[kind]
    return pos if getattr(r, f) > 0 else neg


def model():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=5000, class_weight="balanced", C=1.0))


# ------------------------------------------------------------------ data
earset = add_abs(pd.read_csv(ROOT / "results" / "earset_events.csv"))
earset["kind"] = earset.label.map(KIND)
earset["source"] = "EarSet"

rec, p, ev, report, p01 = pr.session_events(str(SESSION), 1.5)
p01 = add_abs(p01[p01.nth == 0].copy())
p01["kind"] = p01.label.map(KIND)
p01["person"], p01["source"], p01["motion"] = "P01", "P01 app session", p01.label

cfg = PipelineConfig(); cfg.features.sets = ("axis", "signed", "timing", "magnitude")
old = add_abs(pr.earlier_events(*map(str, EARLIER), cfg))
old = old[old.label.isin(KIND)].copy()
old["kind"], old["motion"], old["person"], old["source"] = old.label.map(KIND), old.label, "P01", "P01 earlier Mac"
old = old[old.label != "nod_down"]               # that recording's nods were held down and split (labels note)

still = load_session(str(EARLIER[2]))
talk_rec = load_session(str(TALKING))
tp = Pipeline(cfg); tp.calibrations = [Calibration(0.0, quiet_from(still, 0, len(still)), None)]
talk = add_abs(pd.DataFrame([dict(zip(NAMES, e.features)) for e in tp.extract(talk_rec)]))
talk["kind"], talk["motion"], talk["person"], talk["source"] = "none", "none", "P01", "P01 talking"

train = pd.concat([earset, p01, old, talk], ignore_index=True)

# ------------------------------------------------------------------ evaluation
L = ["# Live recogniser: Rules mode vs Model mode", "",
     "Generated by `algorithm/scripts/export_live_model.py`. Both modes: kind (nod / tilt / turn / circle / none), "
     "then direction from one sign. Model = logistic regression on " + ", ".join(f"`{f}`" for f in FEATURES) +
     f". Rules: dominant axis share >= {AXIS_SHARE} -> nod/tilt/turn, else |loop| >= {LOOP_MIN} -> circle, "
     "else none.", "",
     f"Training data: {len(earset)} EarSet events (30 people), {len(p01)} P01 app-session motions, {len(old)} P01 "
     f"earlier-recording motions, {len(talk)} P01 talking events.", ""]

# EarSet leave-one-person-out (kinds nod/tilt/turn/none only; no circles in EarSet)
es_people = sorted(earset.person.unique())
pred_m, pred_r = pd.Series(index=earset.index, dtype=object), earset.apply(rule_kind, axis=1)
extra = pd.concat([p01, old, talk])
for pid in es_people:
    te = earset.person == pid
    m = model().fit(pd.concat([earset[~te], extra])[FEATURES], pd.concat([earset[~te], extra]).kind)
    pred_m[te] = m.predict(earset.loc[te, FEATURES])
L += ["## EarSet, leave one person out (each person tested by a model trained on the other 29 + P01)", ""]
for name, pred in (("Rules", pred_r), ("Model", pred_m)):
    ok = pred == earset.kind
    g = earset.kind != "none"
    L.append(f"- **{name}**: kind accuracy {ok.mean():.2f}; head gestures right {ok[g].mean():.2f}; "
             f"no-gesture events called 'none' {ok[~g].mean():.2f}")
L += ["", "Rules have no real 'none' test (anything with one dominant axis is a motion): in the app the pair rule "
      "and the detector carry most of the false-command protection, as before.", ""]

# P01 (trained on EarSet + P01's OTHER recording: earlier Mac -> app session, and the reverse)
def p01_eval(test, extra_train):
    m = model().fit(pd.concat([earset, extra_train])[FEATURES], pd.concat([earset, extra_train]).kind)
    km, kr = m.predict(test[FEATURES]), test.apply(rule_kind, axis=1)
    rows = []
    for (_, r), a, b in zip(test.iterrows(), km, kr):
        rows.append({"motion": r.motion, "model": direction(a, r), "rules": direction(b, r)})
    return pd.DataFrame(rows)

res = pd.concat([p01_eval(p01, pd.concat([old, talk])), p01_eval(old, talk)], ignore_index=True)
L += ["## P01 (Ghanshyam), final motion name (8 motions)", "",
      "App-session motions: model trained on EarSet + P01's earlier recording + talking. Earlier-recording motions: "
      "model trained on EarSet + talking only, so it has never seen a circle there (circles can only come out of "
      "it by accident). One person, few trials: a sanity check, not a result.", ""]
tab = pd.DataFrame([{"motion": mot, "n": int((res.motion == mot).sum()),
                     "rules": f"{((res.motion == mot) & (res.rules == mot)).sum()}/{(res.motion == mot).sum()}",
                     "model": f"{((res.motion == mot) & (res.model == mot)).sum()}/{(res.motion == mot).sum()}"}
                    for mot in sorted(res.motion.unique())]).set_index("motion")
L += [tab.to_markdown(), "",
      f"Overall: rules {(res.rules == res.motion).mean():.2f}, model {(res.model == res.motion).mean():.2f} "
      f"({len(res)} motions).", ""]
talk_r, talk_m = talk.apply(rule_kind, axis=1), model().fit(pd.concat([earset, p01, old])[FEATURES],
                                                            pd.concat([earset, p01, old]).kind).predict(talk[FEATURES])
L += [f"P01 talking ({len(talk)} events in 1.4 min): called a motion by rules {(talk_r != 'none').sum()}, "
      f"by the model {(talk_m != 'none').sum()} (model trained without the talking file).", ""]

# ------------------------------------------------------------------ final model on everything -> JSON
final = model().fit(train[FEATURES], train.kind)
sc, lr = final.named_steps["standardscaler"], final.named_steps["logisticregression"]
out = {"version": "live-v2 (EarSet + P01, loop fix, 2026-11-08)", "features": FEATURES, "classes": list(lr.classes_),
       "mean": sc.mean_.tolist(), "scale": sc.scale_.tolist(), "coef": lr.coef_.tolist(),
       "intercept": lr.intercept_.tolist(),
       "rules": {"axis_share": AXIS_SHARE, "loop_min": LOOP_MIN},
       "gate": {"min_confidence": 0.5, "min_margin": 0.1},
       "direction": {k: {"feature": v[0], "positive": v[1], "negative": v[2]} for k, v in DIRECTION.items()},
       "pair_timeout_s": 1.5,
       "n_train": {k: int(v) for k, v in train.kind.value_counts().items()}}
(APP / "live_model.json").write_text(json.dumps(out, indent=1))

# parity: raw samples of every P01 app-session motion event, with Python's head frame, features and answers
lab_starts = set(p01.t_start)
cases = []
for e in ev:
    if e.t_start not in lab_starts:
        continue
    cal = p.calibration_at(e.t_start) if hasattr(p, "calibration_at") else p.calibrations[-1]
    n_pre = int(cfg.frame.gravity_pre_s * rec.fs)
    a = max(0, e.start - n_pre)
    seg = slice(a, e.end)
    feats = dict(zip(NAMES, e.features))
    r = pd.Series({**feats, **{f"abs_loop_{q}": abs(feats[f"loop_{q}"]) for q in ("xy", "xz", "yz")}})
    proba = final.predict_proba(pd.DataFrame([r[FEATURES].astype(float)]))[0]
    cases.append({"fs": rec.fs, "pre": e.start - a, "heading": cal.frame.heading,
                  "rot": rec.rot[seg].tolist(),
                  "grav": rec.grav[seg].tolist(), "valid": rec.valid[seg].astype(int).tolist(),
                  "features": {k: float(r[k]) for k in FEATURES + ["first_lobe_x", "first_lobe_y", "first_lobe_z",
                                                                  "loop_xy", "loop_xz", "loop_yz"]},
                  "proba": proba.tolist(), "rule_kind": rule_kind(r),
                  "rule_motion": direction(rule_kind(r), r),
                  "model_kind": lr.classes_[int(np.argmax(proba))]})
(APP / "Tests").mkdir(exist_ok=True)
cases = cases[::2][:14]   # a sample is enough for the check (keeps the repo file small)
(APP / "Tests" / "parity.json").write_text(json.dumps({"model": out, "cases": cases}))
L += [f"Exported `live_model.json` (trained on all {len(train)} events: "
      + ", ".join(f"{k} {v}" for k, v in out["n_train"].items()) + f") and {len(cases)} parity cases.", ""]
(ROOT / "results" / "live_model.md").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
