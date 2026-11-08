"""The hard cases on our old AirPods Pro 2 data (4 people) -> results/hardcases_report.md

Hard pairs: tilt left vs right, circle cw vs ccw (need a signed head frame), jaw single vs double, jaw vs idle,
and the full vocabulary. Leave one person out, logistic regression, nothing tuned.

Frames: R0 sensor axes, R1 gravity, R2s signed head frame (axis of 3 calibration nods, sign fixed so a nod's
first swing is +X; those 3 nod takes are dropped). Feature sets add up:
  axis    : which axis (share_x/y/z, planarity)                       - unsigned, from Phase 0
  +signed : first swing direction per axis, loop direction per plane  - left/right, cw/ccw
  +timing : number of rotation / acceleration peaks and their spacing, high-frequency acceleration - single/double, jaw
  +all    : everything incl. speed, size, duration (Phase 0: mostly person-specific)
Reference on the same data (prior_work/gesture_lab/reports/02_baseline.md): MiniRocket + gravity alignment, 8 classes, 0.72.

Headline setup fixed by a rule, not picked from the grid: MAIN = signed head frame + `+timing` features (it leaves
out speed/size/duration, which Phase 0 found mostly person-specific). The full grid is exploratory: picking its
best cell on the same 4 test people would be optimistic.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from airpods import N_CALIB, takes
from features import NAMES, SIGNED_NAMES, TIMING_NAMES, bout_features, signed_features, timing_features
from frames import signed_heading_from_nods, to_frame
from segment import motion_score

OUT = Path(__file__).resolve().parent / "results"
FRAMES = {"R0": "sensor axes", "R1": "gravity", "R2s": "signed head frame"}
AXIS = ["share_x", "share_y", "share_z", "planarity"]
FEATS = {"axis": AXIS, "+signed": AXIS + SIGNED_NAMES, "+timing": AXIS + SIGNED_NAMES + TIMING_NAMES,
         "+all": NAMES + SIGNED_NAMES + TIMING_NAMES}
ALL = NAMES + SIGNED_NAMES + TIMING_NAMES
MAIN = ("R2s", "+timing")


def active(X, frac=0.3, pad=10):
    """Bout inside a take from rotation AND acceleration change, so weak jaw motion is found too."""
    s = motion_score(X)
    idx = np.where(s > frac * s.max())[0]
    return max(0, idx[0] - pad), min(len(X), idx[-1] + pad + 1)


def build():
    rows = []
    for subj in (1, 2, 3, 4):
        tk = list(takes(subj))
        nods = [X for lab, X in tk if lab == "nod_2x_front"][:N_CALIB]
        heading = signed_heading_from_nods([to_frame(X, *active(X), "R1")[1] for X in nods])
        n_nod = 0
        for i, (lab, X) in enumerate(tk):
            if lab == "nod_2x_front":
                n_nod += 1
                if n_nod <= N_CALIB:
                    continue
            a, b = active(X)
            row = {"person": f"A{subj}", "label": lab, "take": i}
            for fr in FRAMES:
                acc, gyro = to_frame(X, a, b, "R2" if fr == "R2s" else fr, heading)
                f = np.r_[bout_features(acc, gyro), signed_features(acc, gyro), timing_features(acc, gyro)]
                row.update({f"{fr}_{n}": v for n, v in zip(ALL, f)})
            rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "airpods_hard.csv", index=False)
    return df


def loso(d, y, cols):
    pred = np.empty(len(d), dtype=object)
    for p in d.person.unique():
        te = (d.person == p).to_numpy()
        m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, class_weight="balanced"))
        pred[te] = m.fit(d[cols][~te], y[~te]).predict(d[cols][te])
    return pred


df = build()
JAW = ["jaw_clench_single", "jaw_clench_double"]
lab = df.label.to_numpy()
TASKS = {
    "tilt left vs right": (df.label.isin(["tilt_2x_left", "tilt_2x_right"]), lab),
    "circle cw vs ccw": (df.label.isin(["circle_cw", "circle_ccw"]), lab),
    "jaw single vs double": (df.label.isin(JAW), lab),
    "jaw (any) vs idle": (df.label.isin(JAW + ["idle"]), np.where(np.isin(lab, JAW), "jaw", lab)),
    "8 classes (all)": (pd.Series(True, index=df.index), lab),
    "7 classes (jaw merged)": (pd.Series(True, index=df.index), np.where(np.isin(lab, JAW), "jaw", lab)),
    "6 classes (no jaw)": (~df.label.isin(JAW), lab),
}

rows, preds = [], {}
for tname, (mask, y) in TASKS.items():
    d, yy = df[mask.to_numpy()], y[mask.to_numpy()]
    for fr in FRAMES:
        for fs, names in FEATS.items():
            p = loso(d, yy, [f"{fr}_{n}" for n in names])
            preds[(tname, fr, fs)] = (yy, p)
            rows.append({"task": tname, "frame": fr, "features": fs, "accuracy": np.mean(p == yy),
                         "macro_F1": f1_score(yy, p, average="macro"),
                         **{f"A{i}": np.mean(p[d.person == f"A{i}"] == yy[d.person == f"A{i}"]) for i in (1, 2, 3, 4)}})
res = pd.DataFrame(rows)
acc = res.pivot_table(index=["task", "frame"], columns="features", values="accuracy", sort=False)[list(FEATS)]


def variance_split(d, col, y):
    x = d[col].to_numpy()
    g = pd.Series(x).groupby(y).transform("mean").to_numpy()
    c = pd.Series(x).groupby([y, d.person.to_numpy()]).transform("mean").to_numpy()
    tot = ((x - x.mean()) ** 2).sum()
    return ((g - x.mean()) ** 2).sum() / tot, ((c - g) ** 2).sum() / tot


vrows = []
for tname in ["tilt left vs right", "circle cw vs ccw", "jaw single vs double", "jaw (any) vs idle"]:
    mask, y = TASKS[tname]
    d, yy = df[mask.to_numpy()], y[mask.to_numpy()]
    for n in ALL:
        gsh, psh = variance_split(d, f"R2s_{n}", yy)
        vrows.append({"task": tname, "feature": n, "gesture": gsh, "person": psh})
vs = pd.DataFrame(vrows)
top = vs.assign(ratio=vs.gesture / vs.person.clip(lower=1e-3)).sort_values(["task", "gesture"], ascending=[True, False])
top = top.groupby("task").head(4).set_index(["task", "feature"])

y8, p8 = preds[("8 classes (all)", *MAIN)]
labs = sorted(set(y8))
cm = pd.DataFrame(confusion_matrix(y8, p8, labels=labs), index=labs, columns=labs)

out = ["# Hard cases on AirPods Pro 2 (4 people, leave one person out)", "",
       "Generated by `phase0/hardcases.py` from `../prior_work/gesture_lab/data/raw` (cued 2.5 s takes). Logistic regression, "
       "nothing tuned. Frames: R0 sensor axes, R1 gravity, R2s signed head frame (3 calibration nods per person, "
       "dropped from testing). Feature sets add up from left to right (see the script); `+timing` = "
       f"{len(AXIS + SIGNED_NAMES + TIMING_NAMES)} features, `+all` = {len(ALL)}. "
       "Reference on the same data: MiniRocket + gravity alignment, 8 classes, LOSO 0.72 "
       "(`prior_work/gesture_lab/reports/02_baseline.md`; it keeps the 3 nod takes we use for calibration).", "",
       f"## Headline: fixed setup ({MAIN[0]}, {MAIN[1]}), fixed by rule (no speed/size features), not the best cell", "",
       res[(res.frame == MAIN[0]) & (res.features == MAIN[1])].set_index("task")
       [["accuracy", "macro_F1", "A1", "A2", "A3", "A4"]].to_markdown(floatfmt=".2f"), "",
       "## Full grid (exploratory; do not quote the best cell)", "", acc.to_markdown(floatfmt=".2f"), "",
       "## Best features per hard pair (signed head frame): share of variance from gesture vs person", "",
       top[["gesture", "person"]].to_markdown(floatfmt=".2f"), "",
       f"## Confusion, 8 classes, headline setup ({MAIN[0]}, {MAIN[1]}, accuracy {np.mean(p8 == y8):.2f})", "",
       "Rows = true, columns = predicted.", "", cm.to_markdown(), ""]
(OUT / "hardcases_report.md").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
