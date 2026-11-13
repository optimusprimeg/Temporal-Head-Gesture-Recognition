"""Reverse cross-person test: train on ONE person's continuous app session, test on the teammates' recordings.

  python scripts/reverse_cross_person.py <session folder> [--out results/<name>.md]

Train (the app session, e.g. P01 on AirPods 5): our detector's events, 8 single head motions + 'none' (events in
idle cues and the no-gesture blocks: talking, nodding along, looking around ...).
Test (other people, other AirPods, block-recorded clips, from ours/data/all_by_format): old4 S1-S4, Sankalp,
Shubham (head doubles, jaw, face, idle), the micro-face and touch clips (all should give 'none').
Their labels are mapped to what a single-motion model can say: tilt_2x_left -> tilt_left, nod_2x_front -> nod_down,
rotate_left_chin_down -> turn_left (its first motion), circles stay; idle, jaw, face, touch -> none.
No calibration nods exist in their data, so every feature here uses gravity only (no heading), in training too.
Two ways to cut a test clip:
  event  our detector runs over the clip (quiet level = the clip's quietest 0.5 s); its FIRST event is classified
  clip   the whole clip is classified (the teammates' way: one window per take)
A model sends a command when it says a gesture with probability >= 0.70; otherwise the clip counts as 'none'.
"""
import argparse
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
of, receiver_96, theirs_214, clean, OUR, CH, ROOT = (ns[k] for k in ("of", "receiver_96", "theirs_214", "clean", "OUR",
                                                                     "CH", "ROOT"))
sys.path.insert(0, str(ROOT))
from gesturekit.config import DetectorConfig  # noqa: E402
from gesturekit.detect import Detector, Quiet  # noqa: E402

MOTIONS = ["nod_down", "look_up", "tilt_left", "tilt_right", "turn_left", "turn_right", "circle_cw", "circle_ccw"]
MAP = {"tilt_2x_left": "tilt_left", "tilt_2x_right": "tilt_right", "nod_2x_front": "nod_down",
       "circle_cw": "circle_cw", "circle_ccw": "circle_ccw", "rotate_left_chin_down": "turn_left",
       "rotate_right_chin_down": "turn_right"}
GATE, FS = 0.70, 50

ap = argparse.ArgumentParser()
ap.add_argument("session")
ap.add_argument("--out")
ap.add_argument("--flip-rot", action="store_true",
                help="negate the test clips' rotation rate (Sensor Logger vs app sign check)")
a = ap.parse_args()
S = Path(a.session)


def feats(w, pre=None):
    f = of.event_features(w, FS, heading=None, pre=pre)
    o = [f[k] for k in OUR]
    t = theirs_214(w)
    return {"ours 25": o, "receiver 96": receiver_96(w), "theirs 214": t, "ours + 214": o + t}


# ------------------------------------------------------------------ training: the app session
st = pd.read_csv(S / "stream_000.csv").sort_values("sensor_ns").reset_index(drop=True)
t = (st.sensor_ns.to_numpy(np.int64) - st.sensor_ns.iloc[0]) / 1e9
t0 = st.sensor_ns.iloc[0]
cues, ev = pd.read_csv(S / "cues.csv"), pd.read_csv(S / "derived" / "events.csv")
neg = cues[cues.kind == "negatives"].assign(a=lambda c: (c.sensor_ns_est - t0) / 1e9).assign(b=lambda c: c.a + c.window_s)
rnd = cues[cues.kind == "rounds"].assign(a=lambda c: (c.sensor_ns_est - t0) / 1e9 - 0.3).assign(
    b=lambda c: (c.sensor_ns_est - t0) / 1e9 + c.window_s)
TR = []
for _, e in ev.iterrows():
    inneg = ((neg.a <= e.t_start) & (e.t_start < neg.b)).any()
    r = rnd[(rnd.a <= e.t_start) & (e.t_start < rnd.b)]
    if inneg or (len(r) and r.motion.iloc[0] == "idle"):
        lab = "none"
    elif len(r) and e.label in MOTIONS:
        lab = e.label
    else:
        continue
    i0, i1 = np.searchsorted(t, e.t_start), np.searchsorted(t, e.t_end, side="right")
    p0 = np.searchsorted(t, e.t_start - 0.5)
    w = st.iloc[i0:i1][CH].astype(float).reset_index(drop=True)
    if len(w) >= 10:
        TR.append({"label": lab, **feats(w, st.iloc[p0:i0][CH].astype(float))})
TR = pd.DataFrame(TR)
MODELS = [("LR", "ours 25"), ("RF", "ours 25"), ("RF", "receiver 96"), ("RF", "theirs 214"), ("RF", "ours + 214")]


def make(kind):
    return (make_pipeline(StandardScaler(), LogisticRegression(max_iter=4000)) if kind == "LR"
            else RandomForestClassifier(300, random_state=0, n_jobs=-1))


fitted = {(k, f): make(k).fit(clean(TR[f].tolist()), TR.label) for k, f in MODELS}
print("trained on", len(TR), "events:", TR.label.value_counts().to_dict(), flush=True)

# ------------------------------------------------------------------ test: their clips
T = [x for x in ns["load_all"]() if x["dataset"] != "P01_app"]
rows = []
for x in T:
    g = x["x"].copy()
    if a.flip_rot:
        g[of.ROT] = -g[of.ROT]
    truth = MAP.get(x["label"], "none")
    rot, acc = g[of.ROT].to_numpy(float), g[of.ACC].to_numpy(float)
    sp = np.linalg.norm(rot, axis=1)
    jk = np.r_[0, np.linalg.norm(np.diff(acc, axis=0), axis=1)]
    k = int(0.5 * FS)
    if len(sp) > k:
        i0 = int(np.argmin(np.convolve(sp, np.ones(k), "valid")))
        qg, qj = float(np.median(sp[i0:i0 + k])) + 1e-4, float(np.median(jk[i0:i0 + k])) + 1e-4
        det = Detector(DetectorConfig(fs=FS), Quiet(qg, qj, float(np.median(sp[i0:i0 + k] / qg + jk[i0:i0 + k] / qj))))
        evs = []
        for i in range(len(g)):
            evs += det.push(rot[i], acc[i])
        evs += det.flush()
    else:
        evs = []
    evs = [(s, e) for s, e in evs if e - s >= 10]
    win = {"clip": feats(g)}
    if evs:
        s, e = evs[0]
        win["event"] = feats(g.iloc[s:e].reset_index(drop=True), g.iloc[max(0, s - k):s])
    for (kind, fs), m in fitted.items():
        for cut in ("event", "clip"):
            if cut not in win:
                pred = "none"
            else:
                p = m.predict_proba(clean([win[cut][fs]]))[0]
                j = int(p.argmax())
                pred = m.classes_[j] if (m.classes_[j] != "none" and p[j] >= GATE) else "none"
            rows.append({"dataset": x["dataset"], "label": x["label"], "truth": truth, "model": f"{kind} on {fs}",
                         "cut": cut, "pred": pred})
R = pd.DataFrame(rows)
R["is_head"] = R.truth != "none"
R["dsgroup"] = R.dataset.where(~R.dataset.str.startswith("old4"), "old4 (4 people)")

L = ["# Reverse test: trained on one app session, tested on the teammates' recordings", "",
     f"Generated by `algorithm/scripts/reverse_cross_person.py` (method in its header). Training: `{S.name}`, "
     f"{len(TR)} events ({', '.join(f'{k} {v}' for k, v in TR.label.value_counts().items())}). "
     "All features without a calibration heading.", ""]
for cut in ("event", "clip"):
    rr = []
    for (dsg, mod), g in R[R.cut == cut].groupby(["dsgroup", "model"]):
        h, n = g[g.is_head], g[~g.is_head]
        rr.append({"data": dsg, "model": mod,
                   "head gestures right": f"{np.mean(h.pred == h.truth):.0%}" if len(h) else "-",
                   "head sent wrong": f"{np.mean((h.pred != 'none') & (h.pred != h.truth)):.0%}" if len(h) else "-",
                   "head missed": f"{np.mean(h.pred == 'none'):.0%}" if len(h) else "-",
                   "idle/face/touch sent as a command": f"{np.mean(n.pred != 'none'):.0%}" if len(n) else "-",
                   "clips": len(g)})
    L += [f"## Cut: {cut} ({'first detected event of each clip' if cut == 'event' else 'whole clip, the teammates way'})",
          "", pd.DataFrame(rr).to_markdown(index=False), ""]
best = R[(R.cut == "event") & (R.model == "LR on ours 25") & R.is_head]
L += ["Per gesture, LR on ours 25, event cut (what it says most):", "",
      best.groupby("label").pred.agg(lambda s: f"{s.value_counts().index[0]} ({s.value_counts().iloc[0]}/{len(s)}), "
                                     f"right {np.mean(s == best.loc[s.index, 'truth']):.0%}").to_frame("prediction").to_markdown(), ""]
out = Path(a.out) if a.out else ROOT / "results" / "reverse_cross_person.md"
out.write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
