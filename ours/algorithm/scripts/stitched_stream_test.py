"""Live-like test on recorded takes -> results/stitched_stream_test.md

The takes were recorded one by one. Here they are stitched into one continuous stream per person, in RANDOM order,
with 2-4 s of that person's own idle recording between gestures (idle takes are never used as gestures). Then each
live pipeline runs over the stream sample by sample, exactly as it would live:

  detector  THEIRS  secret_receiver_20_event.py: start when |rotation| >= 0.60 rad/s for 3 samples, keep while
                    >= 0.20, end after 25 quiet samples, 15-sample pre-buffer, 40-150 samples, 1.5 s cooldown
            OURS    gesturekit causal detector, quiet level from the person's training idle takes (x3)
  model     random forest on: sir/receiver 96, theirs 214, ours 25, ours + 214. Trained on single takes WITH the
            idle class. Fires only if the class is not idle and confidence >= 0.70 (their rule).

Two settings:
  SAME PERSON  model trained on the person's first 60 % takes of every class; stream = the last 40 %
  NEW PERSON   model trained on the other people; stream = all of this person's takes of the head classes
               everyone shares (tilt 2x L/R, nod 2x, circle cw/ccw)
People: old4 S1-S4 and Sankalp (the ones with idle recordings).

Scoring per inserted gesture: CORRECT = a fired command overlaps it with the right name; WRONG = fired, wrong name;
MISSED = nothing fired. FALSE = commands fired during the idle filler, per minute of filler.
Caveat: idle filler is short idle takes (sitting still), not talking or walking, so FALSE is a best case.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
src = (HERE / "benchmark_all.py").read_text(encoding="utf-8").split(
    "# ------------------------------------------------------------------ run")[0]
ns = {"__file__": str(HERE / "benchmark_all.py"), "__name__": "bench"}
exec(compile(src, "benchmark_all.py", "exec"), ns)
sys.path.insert(0, str(ns["ROOT"]))
from gesturekit.config import DetectorConfig  # noqa: E402
from gesturekit.detect import Detector, Quiet  # noqa: E402

of, FS, CH, OUR = ns["of"], ns["FS"], ns["CH"], ns["OUR"]
receiver_96, theirs_214, clean, rf = ns["receiver_96"], ns["theirs_214"], ns["clean"], ns["rf"]
RNG = np.random.default_rng(0)
PEOPLE = ["S1", "S2", "S3", "S4", "sankalp"]
SHARED = ["tilt_2x_left", "tilt_2x_right", "nod_2x_front", "circle_cw", "circle_ccw"]
CONF = 0.70


def feats(x):
    f = of.event_features(x, FS)
    o = [f[k] for k in OUR]
    t = theirs_214(x)
    return {"sir/receiver 96": receiver_96(x), "theirs 214": t, "ours 25": o, "ours + 214": o + t}


MODELS = ["sir/receiver 96", "theirs 214", "ours 25", "ours + 214"]


def their_detector(rot):
    sp = np.linalg.norm(rot, axis=1)
    out, state, onset, quiet, start, last_end = [], "W", 0, 0, 0, -10 ** 9
    for i, m in enumerate(sp):
        if i - last_end < 1.5 * FS:
            continue
        if state == "W":
            onset = onset + 1 if m >= 0.60 else 0
            if onset >= 3:
                state, start, quiet, onset = "R", max(0, i - 2 - 15), 0, 0
        else:
            quiet = quiet + 1 if m < 0.20 else 0
            if quiet >= 25 or i - start + 1 >= 150:
                if i - start + 1 >= 40:
                    out.append((start, i + 1))
                state, last_end = "W", i
    return out


def our_detector(rot, acc, idle_takes):
    sp, jk = [], []
    for x in idle_takes:
        r, a = x[of.ROT].to_numpy(), x[of.ACC].to_numpy()
        sp.append(np.linalg.norm(r, axis=1))
        jk.append(np.r_[0, np.linalg.norm(np.diff(a, axis=0), axis=1)])
    sp, jk = np.concatenate(sp), np.concatenate(jk)
    qg, qj = float(np.median(sp)) + 1e-4, float(np.median(jk)) + 1e-4
    det = Detector(DetectorConfig(fs=FS), Quiet(qg, qj, float(np.median(sp / qg + jk / qj))))
    ev = []
    for i in range(len(rot)):
        ev += det.push(rot[i], acc[i])
    return ev + det.flush()


def stitch(gest, idle):
    parts, spans, pos, k = [], [], 0, 0
    order = RNG.permutation(len(gest))
    idle = idle or [None]

    def filler():
        nonlocal k, pos
        need = int(RNG.uniform(2, 4) * FS)
        got = 0
        while got < need:
            x = idle[k % len(idle)]
            k += 1
            x = x.iloc[: need - got]
            parts.append(x)
            got += len(x)
        pos += got
    filler()
    for j in order:
        x, lab = gest[j]
        parts.append(x)
        spans.append((pos, pos + len(x), lab))
        pos += len(x)
        filler()
    return pd.concat(parts, ignore_index=True), spans


def run_stream(S, spans, models, idle_train, cut_models=None):
    rot, acc = S[of.ROT].to_numpy(float), S[of.ACC].to_numpy(float)
    gest_mask = np.zeros(len(S), bool)
    for a, b, _ in spans:
        gest_mask[a:b] = True
    filler_min = (~gest_mask).sum() / FS / 60
    rows = []
    for det_name, evs in (("THEIRS (0.60 rad/s)", their_detector(rot)),
                          ("OURS (adaptive)", our_detector(rot, acc, idle_train))):
        fe = [feats(S.iloc[a:b].reset_index(drop=True)) for a, b in evs]
        variants = [("whole takes", models)]
        if cut_models:
            variants.append(("detector cuts (FIX)", cut_models["their" if det_name.startswith("THEIRS") else "our"]))
        for (trained, mset), m in [(v, m) for v in variants for m in MODELS]:
            clf = mset[m]
            fired = []
            if fe:
                P = clf.predict_proba(clean([f[m] for f in fe]))
                for (a, b), p in zip(evs, P):
                    lab = clf.classes_[p.argmax()]
                    if lab != "idle" and p.max() >= CONF:
                        fired.append((a, b, lab))
            res = {"correct": 0, "wrong": 0, "missed": 0}
            used = set()
            for a, b, lab in spans:
                hit = [f for f in fired if f[0] < b and f[1] > a]
                used.update(hit)
                if not hit:
                    res["missed"] += 1
                elif any(h[2] == lab for h in hit):
                    res["correct"] += 1
                else:
                    res["wrong"] += 1
            false = len([f for f in fired if f not in used])
            rows.append({"detector": det_name, "trained on": trained, "model": m, **res, "gestures": len(spans),
                         "false": false, "filler_min": filler_min})
    return rows


def train(D):
    """As the teammates train: one row per whole take."""
    X = {m: [] for m in MODELS}
    for x in D.x:
        f = feats(x)
        for m in MODELS:
            X[m].append(f[m])
    y = D.label.to_numpy()
    return {m: rf().fit(clean(X[m]), y) for m in MODELS}


def train_on_cuts(D, detector, idle_train):
    """FIX: train on what live will see. Stitch the TRAINING takes into a stream (3 random orders), run the same
    detector, label each detected window by the take it overlaps (no overlap = idle)."""
    X, y = {m: [] for m in MODELS}, []
    gest = [(x, l) for x, l in zip(D.x, D.label) if l != "idle"]
    idle = list(D[D.label == "idle"].x)
    for _ in range(3):
        S, spans = stitch(gest, idle)
        rot, acc = S[of.ROT].to_numpy(float), S[of.ACC].to_numpy(float)
        evs = their_detector(rot) if detector == "their" else our_detector(rot, acc, idle_train)
        for a, b in evs:
            lab = next((l for a2, b2, l in spans if a < b2 and b > a2), "idle")
            f = feats(S.iloc[a:b].reset_index(drop=True))
            for m in MODELS:
                X[m].append(f[m])
            y.append(lab)
    y = np.array(y)
    if len(set(y)) < 2:                      # detector found (almost) nothing: fall back to whole takes
        print("  no detector cuts for training, using whole takes", flush=True)
        return train(D)
    return {m: rf().fit(clean(X[m]), y) for m in MODELS}


T =[t for t in ns["load_all"]() if t["person"] in PEOPLE]
D = pd.DataFrame(T)
D["frac"] = D.groupby(["person", "label"]).cumcount() / D.groupby(["person", "label"]).label.transform("size")
allrows = []
for p in PEOPLE:
    g = D[D.person == p]
    tr, te = g[g.frac < 0.6], g[g.frac >= 0.6]
    models = train(tr)
    idle_tr = list(tr[tr.label == "idle"].x)
    cut = {d: train_on_cuts(tr, d, idle_tr) for d in ("their", "our")}
    S, spans = stitch([(x, l) for x, l in zip(te.x, te.label) if l != "idle"], list(te[te.label == "idle"].x))
    allrows += [{"setting": "SAME PERSON", "person": p, **r} for r in run_stream(S, spans, models, idle_tr, cut)]
    print(p, "same done", flush=True)
for p in PEOPLE:
    others = D[(D.person != p) & D.label.isin(SHARED + ["idle"])]
    models = train(others)
    cut = {d: train_on_cuts(others, d, list(others[others.label == "idle"].x)[:40]) for d in ("their", "our")}
    g = D[D.person == p]
    idle = list(g[g.label == "idle"].x)
    S, spans = stitch([(x, l) for x, l in zip(g.x, g.label) if l in SHARED], idle)
    allrows += [{"setting": "NEW PERSON", "person": p, **r} for r in run_stream(S, spans, models, idle[:20], cut)]
    print(p, "new done", flush=True)

R = pd.DataFrame(allrows)
L = ["# Stitched-stream (live-like) test", "",
     "Generated by `algorithm/scripts/stitched_stream_test.py` (method in its header). Takes stitched in random "
     "order with idle between, each live pipeline run sample by sample.", ""]
for setting in ("SAME PERSON", "NEW PERSON"):
    g = R[R.setting == setting]
    s = g.groupby(["trained on", "detector", "model"])[["correct", "wrong", "missed", "gestures", "false", "filler_min"]].sum()
    s["correct %"] = (100 * s.correct / s.gestures).round(0)
    s["wrong %"] = (100 * s.wrong / s.gestures).round(0)
    s["missed %"] = (100 * s.missed / s.gestures).round(0)
    s["false / min idle"] = (s.false / s.filler_min).round(2)
    L += [f"## {setting} (all {len(PEOPLE)} people summed)", "",
          s[["gestures", "correct %", "wrong %", "missed %", "false / min idle"]].reset_index().to_markdown(index=False), ""]
    pp = g.assign(pct=(100 * g.correct / g.gestures).round(0)).pivot_table(
        index=["trained on", "detector", "model"], columns="person", values="pct")
    L += ["Correct % per person:", "", pp.reset_index().to_markdown(index=False), ""]
out = ns["ROOT"] / "results" / "stitched_stream_test.md"
out.write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
