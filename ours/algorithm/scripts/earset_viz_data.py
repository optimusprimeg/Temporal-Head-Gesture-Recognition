"""Data for the EarSet visualisation page -> ../website/assets/earset_data.js (window.EARSET = {...})

Uses results/earset_events.csv (eval_earset.py), results/variance_components.csv (R) and, for example traces and
timelines, the raw EarSet files run through the same pipeline as eval_earset.py (still -> quiet level, first 3 nods
-> head frame). Open website/earset.html after running.
Run from ours/algorithm: python scripts/earset_viz_data.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gesturekit.config import PipelineConfig  # noqa: E402
from gesturekit.detect import quiet_from  # noqa: E402
from gesturekit.frames import calibrate  # noqa: E402
from gesturekit.io import EARSET, load_earset  # noqa: E402
from gesturekit.pipeline import Calibration, Pipeline  # noqa: E402

OUT = ROOT.parent / "website" / "assets" / "earset_data.js"
E = pd.read_csv(ROOT / "results" / "earset_events.csv")
V = pd.read_csv(ROOT / "results" / "variance_components.csv")
GEST = ["nod", "shake", "tilt"]
OWN_AXIS = {"nod": "share_x", "shake": "share_z", "tilt": "share_y"}
GROUP = {"brow-raiser": "face", "brow-lowerer": "face", "wink-l": "face", "wink-r": "face", "eyes-lr": "face",
         "eyes-ud": "face", "lip-puller": "face", "chin-raiser": "face", "mouth-stretch": "face",
         "speaking": "talking", "chewing": "chewing / swallowing", "swallowing": "chewing / swallowing",
         "walking": "walking / running", "running": "walking / running", "still": "still"}
people = sorted(E.person.unique(), key=lambda s: int(s[1:]))
r3 = lambda a: [round(float(v), 3) for v in a]  # noqa: E731

# ---------------- counts
counts = E.groupby("activity").size()
order = GEST + sorted([a for a in counts.index if a not in GEST], key=lambda a: -counts[a])
activity_counts = [{"activity": a, "n": int(counts[a]), "group": a if a in GEST else GROUP.get(a, "other")}
                   for a in order]
per_person = E[E.label.isin(GEST)].groupby(["person", "label"]).size().unstack(fill_value=0).reindex(people)
demo = pd.read_csv(EARSET / "Demographics.csv")
demo = demo[demo.Participant.isin(people)]

# ---------------- points for the triangle (all gestures + a stratified sample of no-gesture events)
rng = np.random.default_rng(0)
none = E[E.label == "none"].copy()
none["group"] = none.activity.map(GROUP)
none_s = none.groupby("group", group_keys=False).apply(lambda d: d.sample(min(len(d), 150), random_state=0))
pts = pd.concat([E[E.label.isin(GEST)].assign(group=lambda d: d.label), none_s])
points = {**{c: r3(pts[c]) for c in ["share_x", "share_y", "share_z", "peak_rot", "duration_s"]},
          **{c: pts[c].astype(str).tolist() for c in ["person", "activity", "group"]}}

# ---------------- per person: own-axis share and speed per gesture
pp = []
for g in GEST:
    d = E[E.label == g].groupby("person")
    pp.append({"gesture": g, "people": people,
               "own_share": r3(d[OWN_AXIS[g]].median().reindex(people)),
               "peak_rot": r3(d.peak_rot.median().reindex(people)),
               "duration": r3(d.duration_s.median().reindex(people))})

# ---------------- variance components (R)
var = [{"feature": r.feature, "gesture": round(r.gesture, 3), "person": round(r.person, 3),
        "style": round(r.person_style, 3), "repetition": round(r.repetition, 3), "keep": bool(r.keep)}
       for r in V.itertuples()]

# ---------------- raw examples: head-frame rotation of events, and recording timelines
EX_PEOPLE = ["P0", "P10", "P20"]
EX_ACT = ["nod", "shake", "tilt", "speaking", "walking"]
examples, timelines = [], []
for pid in EX_PEOPLE:
    still, nod = load_earset(pid, "still"), load_earset(pid, "nod")
    p = Pipeline(PipelineConfig())
    q = quiet_from(still, 0, len(still))
    p.calibrations = [Calibration(0.0, q, None)]
    cal = p.extract(nod)[:3]
    p.calibrations = [Calibration(0.0, q, calibrate(nod, [(e.start, e.end) for e in cal], p.cfg.frame))]
    for act in EX_ACT:
        rec = load_earset(pid, act)
        ev = p.extract(rec)
        if act == "nod":
            ev = [e for e in ev if e.t_start >= cal[-1].t_end]
        if ev:
            e = ev[len(ev) // 2]
            examples.append({"person": pid, "activity": act, "fs": rec.fs, "duration": round(e.t_end - e.t_start, 2),
                             "x": r3(e.rot[:, 0]), "y": r3(e.rot[:, 1]), "z": r3(e.rot[:, 2])})
        if pid == "P0":
            n = min(len(rec), int(40 * rec.fs))
            mag = np.linalg.norm(rec.rot[:n], axis=1)
            step = 2
            timelines.append({"activity": act, "t": r3(np.arange(0, n, step) / rec.fs), "mag": r3(mag[::step]),
                              "events": [[round(e.t_start, 2), round(e.t_end, 2)] for e in ev if e.t_start < n / rec.fs]})
    print(pid, "done", flush=True)

data = {"n_people": len(people), "n_events": int(len(E)), "n_gesture_events": int(E.label.isin(GEST).sum()),
        "demographics": {"gender": demo.Gender.value_counts().to_dict(),
                         "age_min": int(demo.Age.min()), "age_max": int(demo.Age.max()),
                         "age_median": float(demo.Age.median())},
        "activity_counts": activity_counts,
        "per_person_counts": {"people": people, **{g: per_person[g].astype(int).tolist() for g in GEST}},
        "points": points, "per_person": pp, "variance": var, "examples": examples, "timelines": timelines}
OUT.write_text("window.EARSET = " + json.dumps(data, separators=(",", ":")) + ";\n", encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
