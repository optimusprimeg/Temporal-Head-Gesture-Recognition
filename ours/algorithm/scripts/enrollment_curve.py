"""Person-independent vs personalised recognition: the enrollment curve on EarSet -> results/enrollment_curve.md

Question: how much do k of a new person's own trials (per gesture) add, and do person-based features (speed, size,
rhythm: what R says is mostly PERSON) become useful once they are expressed relative to that person?

Leave one person out over EarSet's 30 people. The test person contributes k enrollment trials per gesture (their
EARLIEST k nods / shakes / tilts); everything else of theirs is the test set: the remaining gestures plus all their
no-gesture events (face, talking, chewing, walking, running...). Logistic regression + the app's gate (top
probability >= 0.5, margin >= 0.1), classes nod / shake / tilt / none.

Feature sets
  gesture   axis + signed + timing (the pipeline default; no speed or size)
  +person   gesture + magnitude features (speed, size, duration, cycles), raw
  +person/norm  the same, but every person-heavy feature divided by THIS person's median over their own enrollment
            trials (training people: their own first k trials too). Needs k >= 1.
Methods
  base      trained on the other 29 people only (k own trials not used for training)
  weighted  + the k own trials in training, weight 5 each (the earlier team's personalization)
Metrics, averaged over the 30 people: gestures right (named right AND accepted by the gate), no-gesture events
wrongly accepted as a gesture (lower is better).
Caveat: in EarSet each gesture is one 2-minute recording, so enrollment and test trials come from the same wear;
real enrollment (another session, after re-wearing) will gain less.
Run from ours/algorithm: python scripts/enrollment_curve.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gesturekit.features import FEATURE_SETS  # noqa: E402

E = pd.read_csv(ROOT / "results" / "earset_events.csv")
GESTURES = ["nod", "shake", "tilt"]
GESTURE_F = [n for s in ("axis", "signed", "timing") for n in FEATURE_SETS[s][1]]
PERSON_F = FEATURE_SETS["magnitude"][1]                       # speed, size, duration, cycles
NORM_F = PERSON_F + ["acc_hf_rms", "rot_peak_gap_s", "acc_peak_gap_s"]   # person-heavy (R: person + style dominate)
KS = [0, 1, 2, 3, 5]
MIN_CONF, MIN_MARGIN = 0.5, 0.1


def enroll_split(df, k):
    """Index of each person's earliest k trials per gesture."""
    if k == 0:
        return pd.Index([])
    g = df[df.label.isin(GESTURES)].sort_values(["person", "label", "t_start"])
    return g.groupby(["person", "label"]).head(k).index


def normalise(df, enroll_idx):
    """Person-heavy features divided by the person's median over their own enrollment trials."""
    out = df.copy()
    med = df.loc[enroll_idx].groupby("person")[NORM_F].median()
    for f in NORM_F:
        scale = out.person.map(med[f]).astype(float)
        out[f] = out[f] / scale.where(scale.abs() > 1e-9, np.nan)
    return out.fillna(0.0)


def model():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=4000, class_weight="balanced"))


def gate(proba, classes):
    o = np.argsort(proba, axis=1)[:, ::-1]
    top = proba[np.arange(len(proba)), o[:, 0]]
    margin = top - proba[np.arange(len(proba)), o[:, 1]]
    pred = np.array(classes)[o[:, 0]]
    accepted = (pred != "none") & (top >= MIN_CONF) & (margin >= MIN_MARGIN)
    return pred, accepted


rows = []
people = sorted(E.person.unique(), key=lambda s: int(s[1:]))
for k in KS:
    enroll = enroll_split(E, k)
    normed = normalise(E, enroll) if k >= 1 else None
    variants = [("gesture", "base", E, GESTURE_F), ("+person", "base", E, GESTURE_F + PERSON_F)]
    if k >= 1:
        variants += [("gesture", "weighted", E, GESTURE_F), ("+person", "weighted", E, GESTURE_F + PERSON_F),
                     ("+person/norm", "base", normed, GESTURE_F + PERSON_F),
                     ("+person/norm", "weighted", normed, GESTURE_F + PERSON_F)]
    for fset, method, data, cols in variants:
        for pid in people:
            mine = data.person == pid
            own_enroll = data.index.isin(enroll) & mine
            test = mine & ~own_enroll
            train = ~mine
            Xtr, ytr = data.loc[train, cols], data.loc[train, "label"]
            w = np.ones(train.sum())
            if method == "weighted":
                Xtr = pd.concat([Xtr, data.loc[own_enroll, cols]])
                ytr = pd.concat([ytr, data.loc[own_enroll, "label"]])
                w = np.r_[w, np.full(own_enroll.sum(), 5.0)]
            m = model().fit(Xtr, ytr, logisticregression__sample_weight=w)
            pred, acc = gate(m.predict_proba(data.loc[test, cols]), list(m.classes_))
            y = data.loc[test, "label"].to_numpy()
            g = np.isin(y, GESTURES)
            rows.append({"k": k, "features": fset, "method": method, "person": pid,
                         "gestures_right": float(np.mean((pred[g] == y[g]) & acc[g])),
                         "none_accepted": float(np.mean(acc[~g]))})
    print("k", k, "done", flush=True)

R = pd.DataFrame(rows)
summary = R.groupby(["features", "method", "k"]).agg(gestures_right=("gestures_right", "mean"),
                                                      gr_sd=("gestures_right", "std"),
                                                      none_accepted=("none_accepted", "mean")).reset_index()

L = ["# Enrollment curve on EarSet: person-independent vs personalised", "",
     "Generated by `algorithm/scripts/enrollment_curve.py` (method and caveats in its header). Leave one person out, "
     "30 people, classes nod / shake / tilt / none, app gate (0.5 / 0.1). `gestures right` = named right and accepted; "
     "`no-gesture accepted` = share of the person's no-gesture events wrongly accepted as a gesture (lower is better). "
     "Mean over people (± SD across people).", ""]
for fset in ["gesture", "+person", "+person/norm"]:
    L += [f"## Features: {fset}", "", "| k own trials per gesture | method | gestures right | no-gesture accepted |",
          "|---:|:---|---:|---:|"]
    for _, r in summary[summary.features == fset].sort_values(["method", "k"]).iterrows():
        L.append(f"| {r.k} | {r.method} | {r.gestures_right:.3f} ± {r.gr_sd:.3f} | {r.none_accepted:.3f} |")
    L.append("")
best0 = summary[(summary.k == 0)].sort_values("gestures_right").iloc[-1]
L += [f"Best with no own trials (k = 0): {best0.features}, {best0.gestures_right:.3f} gestures right, "
      f"{best0.none_accepted:.3f} no-gesture accepted.", ""]
(ROOT / "results" / "enrollment_curve.md").write_text("\n".join(L), encoding="utf-8")
R.to_csv(ROOT / "results" / "enrollment_curve.csv", index=False)
print("\n".join(L))
