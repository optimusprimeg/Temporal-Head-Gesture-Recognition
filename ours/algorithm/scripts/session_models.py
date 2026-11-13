"""Every model on one continuous app session: gesture accuracy AND false commands in everyday activity.

  python scripts/session_models.py <session folder> [--out results/<name>.md]

Events = our causal detector's events over the whole stream (derived/events.csv, from process_session.py), each
labelled from the cue log; our features and rules use that file's values, i.e. WITH the session's calibration nods. Windows are cut from the raw stream for the feature sets.
  gesture events  the motion cues of the rounds blocks (enrollment, sitting, small)
  'none' events   events during idle cues and the no-gesture blocks (talking, nodding along, looking around ...)
Models (all trained on THIS person only; class 'none' included):
  rules (no training) | LR on ours 25 | RF on ours 25 | RF on receiver 96 | RF on theirs 214 | RF on ours + 214
  forest_model.json: the app's Forest mode, trained on the teammates' + old data (other people, other gestures),
                     with its own 0.60 rad/s detector run over the whole stream: a cross-person check
Tests:
  A  gesture accuracy, later 40 % of each motion's events (train: first 60 % + the 'none' events of block A)
  B  false commands per hour in the no-gesture blocks: train on one block's 'none' (+ all gestures), test on the
     other block, both ways; a model 'fires' when it says a gesture with probability >= 0.70 (the receiver's gate)
  C  doubles: the same gesture twice within 0.6 s (what tilt_2x / nod_2x would need) in the no-gesture blocks
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
src = (HERE / "benchmark_all.py").read_text(encoding="utf-8").split(
    "# ------------------------------------------------------------------ run")[0]
ns = {"__file__": str(HERE / "benchmark_all.py"), "__name__": "bench"}
exec(compile(src, "benchmark_all.py", "exec"), ns)
of, receiver_96, theirs_214, clean, OUR, CH = ns["of"], ns["receiver_96"], ns["theirs_214"], ns["clean"], ns["OUR"], ns["CH"]
ROOT = ns["ROOT"]
MOTIONS = ["nod_down", "look_up", "tilt_left", "tilt_right", "turn_left", "turn_right", "circle_cw", "circle_ccw"]
GATE = 0.70

ap = argparse.ArgumentParser()
ap.add_argument("session")
ap.add_argument("--out")
a = ap.parse_args()
S = Path(a.session)
st = pd.read_csv(S / "stream_000.csv").sort_values("sensor_ns").reset_index(drop=True)
t = (st.sensor_ns.to_numpy(np.int64) - st.sensor_ns.iloc[0]) / 1e9
cues = pd.read_csv(S / "cues.csv")
ev = pd.read_csv(S / "derived" / "events.csv")
t0 = st.sensor_ns.iloc[0]

# which block each event lies in
neg = cues[cues.kind == "negatives"].copy()
neg["a"] = (neg.sensor_ns_est - t0) / 1e9
neg["b"] = neg.a + neg.window_s
rnd = cues[cues.kind == "rounds"].copy()
rnd["a"] = (rnd.sensor_ns_est - t0) / 1e9 - 0.3
rnd["b"] = (rnd.sensor_ns_est - t0) / 1e9 + rnd.window_s


def where(ts):
    n = neg[(neg.a <= ts) & (ts < neg.b)]
    if len(n):
        return "neg_" + n.block.iloc[0][-1], n.condition.iloc[0]
    r = rnd[(rnd.a <= ts) & (ts < rnd.b)]
    if len(r):
        return ("idle" if r.motion.iloc[0] == "idle" else "rounds"), r.motion.iloc[0]
    return "other", ""


rows = []
for i, e in ev.iterrows():
    part, what = where(e.t_start)
    if part == "rounds" and e.label not in MOTIONS:
        continue                                   # extra / partial events in a motion cue
    if part == "other":
        continue
    lab = e.label if part == "rounds" else "none"
    i0, i1 = np.searchsorted(t, e.t_start), np.searchsorted(t, e.t_end, side="right")
    p0 = np.searchsorted(t, e.t_start - 0.5)
    w = st.iloc[i0:i1][CH].astype(float).reset_index(drop=True)
    if len(w) < 10:
        continue
    # our features WITH this session's calibration heading (computed by process_session.py's pipeline)
    f = {k: e[k] for k in e.index if k in OUR or k.startswith("loop_")}
    for pl in ("xy", "xz", "yz"):
        f[f"abs_loop_{pl}"] = abs(e[f"loop_{pl}"])
    rows.append({"t": e.t_start, "t_end": e.t_end, "part": part, "what": what, "label": lab,
                 "ours": [f[k] for k in OUR], "rule": of.rule_classify(f), "rcv": receiver_96(w), "214": theirs_214(w)})
E = pd.DataFrame(rows).sort_values("t").reset_index(drop=True)
FS = {"ours 25": lambda D: clean(D.ours.tolist()), "receiver 96": lambda D: clean(D.rcv.tolist()),
      "theirs 214": lambda D: clean(D["214"].tolist()),
      "ours + 214": lambda D: np.hstack([clean(D.ours.tolist()), clean(D["214"].tolist())])}
MODELS = [("LR", "ours 25"), ("RF", "ours 25"), ("RF", "receiver 96"), ("RF", "theirs 214"), ("RF", "ours + 214")]


def make(kind):
    if kind == "LR":
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=4000, C=1.0))
    return RandomForestClassifier(300, random_state=0, n_jobs=-1)


def fires(m, X):
    p = m.predict_proba(X)
    lab = m.classes_[p.argmax(1)]
    return lab, (lab != "none") & (p.max(1) >= GATE)


G = E[E.part == "rounds"].copy()
G["frac"] = G.groupby("label").cumcount() / G.groupby("label").label.transform("size")
NA, NB = E[E.part == "neg_a"], E[E.part == "neg_b"]
IDLE = E[E.part == "idle"]
min_a = neg[neg.block.str.endswith("a")].window_s.sum() / 60
min_b = neg[neg.block.str.endswith("b")].window_s.sum() / 60
L = ["# All models on one continuous app session", "",
     f"Generated by `algorithm/scripts/session_models.py` (method in its header). Session `{S.name}`. "
     f"{len(G)} gesture events (8 single head motions), {len(IDLE)} events in idle cues, "
     f"{len(NA)} + {len(NB)} events in the no-gesture blocks A ({min_a:.1f} min) and B ({min_b:.1f} min). "
     "One person: effect sizes, not population results.", ""]

# ---- A
res = []
tr_g, te_g = G[G.frac < 0.6], G[G.frac >= 0.6]
train = pd.concat([tr_g, NA, IDLE])
rule_ok = float(np.mean(te_g.rule == te_g.label))
res.append({"model": "rules (no training)", "accuracy": round(rule_ok, 2), "sent at gate 0.70": "-",
            "sent and right": "-"})
for kind, fs in MODELS:
    m = make(kind).fit(FS[fs](train), train.label)
    lab, fire = fires(m, FS[fs](te_g))
    res.append({"model": f"{kind} on {fs}", "accuracy": round(float(np.mean(lab == te_g.label)), 2),
                "sent at gate 0.70": f"{fire.mean():.0%}",
                "sent and right": f"{np.mean(lab[fire] == te_g.label.to_numpy()[fire]):.0%}" if fire.any() else "-"})
L += ["## A. Gesture accuracy (later 40 % of each motion, 8 motions + none, chance 0.11)", "",
      f"Trained on the first 60 % ({len(tr_g)} events) + the 'none' events of block A and idle cues. Test: "
      f"{len(te_g)} events.", "", pd.DataFrame(res).to_markdown(index=False), ""]


# ---- B
def false_rate(train_none, test_none, minutes):
    out = {"rules (no training)": (int((test_none.rule != "none").sum()), minutes)}
    tr = pd.concat([G, train_none, IDLE])
    for kind, fs in MODELS:
        m = make(kind).fit(FS[fs](tr), tr.label)
        _, fire = fires(m, FS[fs](test_none))
        out[f"{kind} on {fs}"] = (int(fire.sum()), minutes)
    return out


ab, ba = false_rate(NA, NB, min_b), false_rate(NB, NA, min_a)
res = []
for k in ab:
    n = ab[k][0] + ba[k][0]
    res.append({"model": k, "false commands (A->B + B->A)": n, "per hour": round(n / ((min_a + min_b) / 60))})
L += ["## B. False commands in everyday activity (single gestures as commands)", "",
      f"Talking, nodding along, looking around/behind, phone, standing up, drinking ({min_a + min_b:.1f} min, "
      f"{len(NA) + len(NB)} detected events). Trained on one block, tested on the other, both ways.", "",
      pd.DataFrame(res).to_markdown(index=False), ""]


# ---- C doubles: two firings of the same gesture within 0.6 s, with the best trained model
def doubles(test_none, train_none, kind, fs):
    tr = pd.concat([G, train_none, IDLE])
    m = make(kind).fit(FS[fs](tr), tr.label)
    lab, fire = fires(m, FS[fs](test_none))
    T = test_none.assign(lab=lab, fire=fire)
    T = T[T.fire].sort_values("t")
    n, prev = 0, None
    for _, x in T.iterrows():
        if prev is not None and x.lab == prev.lab and x.t - prev.t_end <= 0.6:
            n += 1
            prev = None
            continue
        prev = x
    return n


res = []
for kind, fs in MODELS:
    n = doubles(NB, NA, kind, fs) + doubles(NA, NB, kind, fs)
    res.append({"model": f"{kind} on {fs}", "accidental doubles": n, "per hour": round(n / ((min_a + min_b) / 60))})
L += ["## C. Accidental doubles (same gesture twice within 0.6 s, both above the gate)", "",
      pd.DataFrame(res).to_markdown(index=False), ""]

# ---- E gate sweep: real gestures sent correctly vs false commands per hour
res = []
for kind, fs in MODELS:
    m = make(kind).fit(FS[fs](train), train.label)
    pg = m.predict_proba(FS[fs](te_g))
    mb = make(kind).fit(FS[fs](pd.concat([G, NA, IDLE])), pd.concat([G, NA, IDLE]).label)
    ma = make(kind).fit(FS[fs](pd.concat([G, NB, IDLE])), pd.concat([G, NB, IDLE]).label)
    pb, pa = mb.predict_proba(FS[fs](NB)), ma.predict_proba(FS[fs](NA))
    for gate in (0.3, 0.4, 0.5, 0.6, 0.7):
        lab = m.classes_[pg.argmax(1)]
        ok = np.mean((lab == te_g.label.to_numpy()) & (pg.max(1) >= gate))
        nf = sum(int(((mm.classes_[pp.argmax(1)] != "none") & (pp.max(1) >= gate)).sum()) for mm, pp in ((mb, pb), (ma, pa)))
        res.append({"model": f"{kind} on {fs}", "gate": gate, "gestures sent correctly": f"{ok:.0%}",
                    "false commands / hour": round(nf / ((min_a + min_b) / 60))})
E_ = pd.DataFrame(res).pivot_table(index="model", columns="gate", values=["gestures sent correctly", "false commands / hour"],
                                   aggfunc="first")
L += ["## E. Gate sweep: gestures sent correctly vs false commands per hour", "",
      "Lower gate = more real gestures get through, and more everyday motion too.", "", E_.to_markdown(), ""]

# ---- D cross-person forest (the app's Forest mode)
fm = json.loads((ROOT.parents[0] / "mac_app" / "GestureCollector" / "forest_model.json").read_text())
sys.argv = [sys.argv[0]]
fx = {}
exec(compile((HERE / "export_forest_model.py").read_text(encoding="utf-8").split("def stitch")[0].split(
    "HERE = Path")[0] + "\n", "fx", "exec"), fx)                       # imports only
det_src = (HERE / "export_forest_model.py").read_text(encoding="utf-8")
det_code = det_src[det_src.index("def detect"):det_src.index("def stitch")]
fx.update({"DET": fm["detector"], "FS": 50, "deque": __import__("collections").deque, "np": np})
exec(det_code, fx)
RCV = ["yaw", "pitch", "roll", "rotX", "rotY", "rotZ", "accX", "accY", "accZ", "gravX", "gravY", "gravZ"]


def forest_proba(x):
    p = np.zeros(len(fm["classes"]))
    for tr in fm["trees"]:
        n = 0
        while tr["left"][n] >= 0:
            n = tr["left"][n] if float(np.float32(x[tr["feature"][n]])) <= tr["threshold"][n] else tr["right"][n]
        v = np.array(tr["value"][n])
        p += v / max(v.sum(), 1e-12)
    return p / len(fm["trees"])


wins = fx["detect"](st[["rotX", "rotY", "rotZ"]].to_numpy(float))
fr = []
for a0, b0 in wins:
    x = clean([receiver_96(st.iloc[a0:b0][RCV].astype(float))])[0]
    p = forest_proba(x)
    k = int(p.argmax())
    part, what = where(t[a0] + 0.3)
    fr.append({"part": part, "what": what, "label": fm["classes"][k], "conf": p[k],
               "sent": fm["classes"][k] not in ("idle", "none") and p[k] >= fm["min_confidence"]})
F = pd.DataFrame(fr)
g = F[F.part == "rounds"]
negF = F[F.part.str.startswith("neg")]
top = g[g.sent].groupby("what").label.agg(lambda s: s.value_counts().index[0] + f" ({s.value_counts().iloc[0]}/{len(s)})")
L += ["## D. Cross-person: the app's Forest mode (teammates' + old data, other people, double gestures)", "",
      f"Its own 0.60 rad/s detector found {len(F)} windows: {len(g)} in gesture cues, {len(negF)} in the no-gesture "
      f"blocks. Sent as a command (not idle, confidence >= {fm['min_confidence']}): {int(g.sent.sum())} of the "
      f"gesture windows, **{int(negF.sent.sum())} in the no-gesture blocks = "
      f"{round(negF.sent.sum() / ((min_a + min_b) / 60))} per hour**.", "",
      "What it calls this person's single motions (most common answer when it sends):", "",
      top.to_frame("forest says").to_markdown(), "",
      "Its classes are the teammates' doubles and face gestures; single motions have no class of their own, so "
      "this shows what a model trained on other people's doubles does with one person's singles and everyday motion.", ""]

out = Path(a.out) if a.out else ROOT / "results" / f"session_models_{S.name.split('_')[0]}.md"
out.write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
