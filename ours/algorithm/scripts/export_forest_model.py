"""Train the app's "Forest" live mode and write forest_model.json (+ a parity file for the Swift port).

  python scripts/export_forest_model.py            (from ours/algorithm)

Detector: an exact Python twin of ForestEngine in mac_app/.../ForestModel.swift (the receiver's start/keep/end rules).
Training windows: every person's takes stitched in random order with their own idle in between (3 orders), cut by
that detector, each window labelled by the take it overlaps (no overlap = idle). That is what live sees; training on
whole takes made live miss ~85 % (results/stitched_stream_test.md).
Features: the receiver's 96 (benchmark_all.receiver_96). Random forest, 100 trees, depth 12.
Outputs:
  ours/mac_app/GestureCollector/forest_model.json   copy it into the app's data folder (no rebuild needed)
  ours/mac_app/GestureCollector/Tests/forest_parity.json   windows + expected probabilities for the Swift check
  results/forest_model.md                           what it was trained on, leave-one-person-out score
"""
import json
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
src = (HERE / "benchmark_all.py").read_text(encoding="utf-8").split(
    "# ------------------------------------------------------------------ run")[0]
ns = {"__file__": str(HERE / "benchmark_all.py"), "__name__": "bench"}
exec(compile(src, "benchmark_all.py", "exec"), ns)
ROOT, receiver_96, clean = ns["ROOT"], ns["receiver_96"], ns["clean"]
APP = ROOT.parents[0] / "mac_app" / "GestureCollector"
RCV = ["yaw", "pitch", "roll", "rotX", "rotY", "rotZ", "accX", "accY", "accZ", "gravX", "gravY", "gravZ"]
DET = {"start": 0.60, "keep": 0.20, "end_samples": 25, "onset": 3, "pre": 15, "min_samples": 40,
       "max_samples": 150, "cooldown_s": 1.5}
FS = 50
RNG = np.random.default_rng(0)
TREES, DEPTH = 100, 12


def detect(rot):
    """Twin of ForestEngine.push: returns (a, b) sample index ranges, b exclusive."""
    p = DET
    speed = np.linalg.norm(rot, axis=1)
    pre, out = deque(maxlen=p["pre"]), []
    rec, onset, quiet, start, n_ev, cool = False, 0, 0, 0, 0, -1
    for i, s in enumerate(speed):
        if i < cool:
            pre.append(i)
        elif not rec:
            pre.append(i)
            onset = onset + 1 if s >= p["start"] else 0
            if onset >= p["onset"]:
                rec, start, n_ev, quiet, onset = True, pre[0], len(pre), 0, 0
        else:
            n_ev += 1
            quiet = quiet + 1 if s < p["keep"] else 0
            if quiet >= p["end_samples"] or n_ev >= p["max_samples"]:
                if n_ev >= p["min_samples"]:
                    out.append((start, i + 1))
                rec = False
                pre.clear()
                cool = i + 1 + int(p["cooldown_s"] * FS)
    return out


def stitch(gest, idle):
    parts, spans, pos, k = [], [], 0, 0
    idle = idle or [gest[0][0].iloc[:5] * 0]

    def filler():
        nonlocal k, pos
        need, got = int(RNG.uniform(2, 4) * FS), 0
        while got < need:
            x = idle[k % len(idle)].iloc[: need - got]
            k += 1
            parts.append(x)
            got += len(x)
        pos += got
    filler()
    for j in RNG.permutation(len(gest)):
        x, lab = gest[j]
        parts.append(x)
        spans.append((pos, pos + len(x), lab))
        pos += len(x)
        filler()
    return pd.concat(parts, ignore_index=True), spans


def windows(D, orders=3):
    X, y, person, raw = [], [], [], []
    for p, g in D.groupby("person"):
        gest = [(x, l) for x, l in zip(g.x, g.label) if l != "idle"]
        idle = list(g[g.label == "idle"].x)
        for _ in range(orders):
            S, spans = stitch(gest, idle)
            for a, b in detect(S[["rotX", "rotY", "rotZ"]].to_numpy(float)):
                lab = next((l for a2, b2, l in spans if a < b2 and b > a2), "idle")
                w = S.iloc[a:b][RCV].astype(float)
                X.append(receiver_96(w))
                y.append(lab)
                person.append(p)
                raw.append(w.to_numpy())
    return clean(X), np.array(y), np.array(person), raw


def rf():
    from sklearn.ensemble import RandomForestClassifier
    return RandomForestClassifier(TREES, max_depth=DEPTH, random_state=0, n_jobs=-1)


T = ns["load_all"]()
D = pd.DataFrame([t for t in T if t["dataset"] != "P01_app"])        # P01 events are singles with other labels
X, y, person, raw = windows(D)
print(len(y), "windows;", pd.Series(y).value_counts().to_dict())

# leave one person out on the windows (honest number for a new person)
rows = []
for p in np.unique(person):
    te = person == p
    if len(set(y[~te])) < 2:
        continue
    m = rf().fit(X[~te], y[~te])
    pr = m.predict_proba(X[te])
    lab = m.classes_[pr.argmax(1)]
    sent = (lab != "idle") & (pr.max(1) >= 0.7)
    seen = np.isin(y[te], m.classes_)
    rows.append({"person": p, "windows": int(te.sum()),
                 "correct (all windows)": round(float(np.mean(lab == y[te])), 2),
                 "gesture windows sent correctly": round(float(np.mean((lab == y[te])[sent & (y[te] != "idle")])) if (sent & (y[te] != "idle")).any() else 0, 2),
                 "idle windows sent as a command": round(float(np.mean(sent[y[te] == "idle"])) if (y[te] == "idle").any() else 0, 2),
                 "classes never seen in training": int((~seen).sum())})

m = rf().fit(X, y)
trees = []
for est in m.estimators_:
    t = est.tree_
    val = t.value[:, 0, :]
    val = val / np.maximum(val.sum(1, keepdims=True), 1e-12)
    full = val                     # forest trees share the forest's class columns (y is encoded once)
    assert full.shape[1] == len(m.classes_)
    trees.append({"left": t.children_left.tolist(), "right": t.children_right.tolist(),
                  "feature": [int(f) if f >= 0 else 0 for f in t.feature],
                  "threshold": [round(float(v), 9) for v in t.threshold],
                  "value": [[round(float(v), 3) for v in r] for r in full]})
model = {"version": f"forest-rcv96-{pd.Timestamp.now():%Y%m%d}", "feature_set": "receiver96",
         "classes": [str(c) for c in m.classes_], "trees": trees,
         "detector": DET, "min_confidence": 0.70, "crop": 100}
(APP / "forest_model.json").write_text(json.dumps(model, separators=(",", ":")), encoding="utf-8")

# parity: 25 windows, raw 12-channel rows + expected features + probabilities
idx = RNG.choice(len(raw), size=min(25, len(raw)), replace=False)
cases = []
for i in idx:                       # features from exactly the (rounded) rows the Swift test reads
    rows = raw[i].round(9)
    f = clean([receiver_96(pd.DataFrame(rows, columns=RCV))])
    cases.append({"rows": rows.tolist(), "features": f[0].tolist(), "proba": m.predict_proba(f)[0].tolist()})
(APP / "Tests" / "forest_parity.json").write_text(json.dumps({"cases": cases}), encoding="utf-8")

L = ["# Forest live model (app 'Forest' mode)", "",
     "Generated by `algorithm/scripts/export_forest_model.py` (method in its header).", "",
     f"{len(y)} detector windows from {D.person.nunique()} people; {len(m.classes_)} classes; {TREES} trees, depth {DEPTH}; "
     f"file size {(APP / 'forest_model.json').stat().st_size / 1e6:.1f} MB.", "",
     "Windows per class:", "", pd.Series(y).value_counts().to_frame("windows").to_markdown(), "",
     "## New person (leave one person out, on detector windows)", "",
     "Classes a person has that nobody else recorded can never be right for them (last column).", "",
     pd.DataFrame(rows).to_markdown(index=False), ""]
(ROOT / "results" / "forest_model.md").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
