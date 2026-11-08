"""Results for one person's real AirPods data (first used on P01, 2026-11-07).

    python scripts/person_report.py <app session folder> [--earlier <mac csv> <labels csv> <still csv>]
                                    [--negatives <mac csv> ...] [--out results/<name>.md]

What it reports (one person: these are sanity checks and effect sizes, not population results):
  A. cue-level detection and reaction time (event onset relative to the GO beep)
  B. per-motion head-frame features (which axis, first swing, loop direction, duration)
  C. direction consistency inside each direction pair
  D1. a model trained only on EarSet (30 other people, other earbud) applied to this person
  D2. within this session, leave-one-event-out, 8 motions
  D3. across sessions: trained on the earlier Mac recording, tested on the app session (motions in both)
  E. false gestures in no-gesture recordings (talking, still), with the within-person model + gate
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gesturekit.config import PipelineConfig  # noqa: E402
from gesturekit.detect import quiet_from  # noqa: E402
from gesturekit.features import FEATURE_SETS  # noqa: E402
from gesturekit.frames import calibrate  # noqa: E402
from gesturekit.io import load_session  # noqa: E402
from gesturekit.label import label_events  # noqa: E402
from gesturekit.pipeline import Calibration, Pipeline  # noqa: E402

SETS = ("axis", "signed", "timing", "magnitude")
NAMES = [n for s in SETS for n in FEATURE_SETS[s][1]]
AXIS = list(FEATURE_SETS["axis"][1])
AXSIGN = AXIS + list(FEATURE_SETS["signed"][1])
MOTIONS = ["nod_down", "look_up", "tilt_left", "tilt_right", "turn_left", "turn_right", "circle_cw", "circle_ccw"]
OUT_DIR = Path(__file__).resolve().parents[1] / "results"


def logreg():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=5000, class_weight="balanced", C=1.0))


def table(df):
    return df.to_markdown(index=True, floatfmt=".2f")


def session_events(folder, early_s):
    rec = load_session(folder)
    cfg = PipelineConfig()
    cfg.features.sets = SETS
    cfg.label.early_s = early_s
    p = Pipeline(cfg)
    p.calibrate_from_cues(rec)
    ev = p.extract(rec)
    # practice cues are real, labelled motions here: label them like rounds (same labeller rules)
    cues = rec.cues.copy()
    cues.loc[cues.kind == "practice", "kind"] = "rounds"
    labels, report = label_events(ev, cues, cfg.label)
    rows = []
    starts = np.array([e.t_start for e in ev])
    for _, q in cues[cues.kind == "rounds"].iterrows():
        inside = np.where((starts >= q.t_s - early_s) & (starts < q.t_s + q.window_s))[0]
        for i in inside:
            e = ev[i]
            rows.append({"trial": q.trial, "kind": rec.cues.loc[q.name, "kind"], "cue": q.motion,
                         "label": labels[i], "nth": 0 if labels[i] == q.motion else 1,
                         "onset_rel_go": e.t_start + cfg.detector.pre_s - q.t_s, "t_start": e.t_start,
                         "duration": e.t_end - e.t_start, "peak_rot": float(np.linalg.norm(e.rot, axis=1).max()),
                         **dict(zip(NAMES, e.features))})
    return rec, p, ev, report, pd.DataFrame(rows)


def earlier_events(csv, labels_csv, still_csv, cfg):
    still, rec = load_session(still_csv), load_session(csv)
    q = quiet_from(still, 0, len(still))
    p = Pipeline(cfg)
    p.calibrations = [Calibration(0.0, q, None)]
    ev = p.extract(rec)
    lab = pd.read_csv(labels_csv)

    def label(t):
        hit = lab[(lab.t_from_s <= t) & (t < lab.t_to_s)]
        return hit.label.iloc[0] if len(hit) else "?"
    # calibration: chin-down halves of the first nods (that recording had no app calibration)
    downs = [e for e in ev if label(e.t_start) == "nod_down" and e.rot[:, 0].sum() < 0][:3]
    if len(downs) < 3:
        downs = [e for e in ev if label(e.t_start) == "nod_down"][:3]
    p.calibrations = [Calibration(0.0, q, calibrate(rec, [(e.start, e.end) for e in downs], cfg.frame))]
    ev = p.extract(rec)
    return pd.DataFrame([{"label": label(e.t_start), "duration": e.t_end - e.t_start,
                          **dict(zip(NAMES, e.features))} for e in ev])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    ap.add_argument("--earlier", nargs=3, metavar=("CSV", "LABELS", "STILL"))
    ap.add_argument("--negatives", nargs="*", default=[])
    ap.add_argument("--early", type=float, default=1.5)
    ap.add_argument("--out", default=str(OUT_DIR / "person_report.md"))
    a = ap.parse_args()

    rec, p, ev, report, df = session_events(a.session, a.early)
    who = f"{rec.meta.get('firstName', '?')} ({rec.meta.get('participant', '?')}), {rec.meta.get('device', '?')}"
    L = [f"# Real AirPods results: {who}", "",
         f"Generated by `algorithm/scripts/person_report.py`. Session `{Path(a.session).name}`, "
         f"{len(rec) / rec.fs / 60:.1f} min, {len(ev)} detected events. One person: sanity checks and effect sizes, "
         "not population results. Motion windows open "
         f"{a.early:.1f} s before GO (app v2.0 announces the motion before the beep).", ""]

    # A. detection and reaction time
    cue_rows = df[df.nth == 0]
    n_cues = rec.cues.kind.isin(["practice", "rounds"]).sum() - (rec.cues.motion == "idle").sum()
    found = cue_rows[cue_rows.cue != "idle"]
    extra = df[(df.nth > 0) & (df.cue != "idle")]
    L += ["## A. Detection and timing", "",
          f"- motion cues (practice + rounds): {n_cues}; with at least one event: {len(found)} "
          f"({len(found) / max(n_cues, 1):.0%}); cues with more than one event: {extra.trial.nunique()} "
          "(the motion was done more than once, or split)",
          f"- onset relative to GO (median, IQR): {found.onset_rel_go.median():+.2f} s "
          f"[{found.onset_rel_go.quantile(.25):+.2f}, {found.onset_rel_go.quantile(.75):+.2f}]; "
          f"{(found.onset_rel_go < 0).mean():.0%} start before the GO beep",
          f"- event duration median {found.duration.median():.2f} s; at the 4 s cap: {(df.duration >= 3.9).sum()} of {len(df)}",
          f"- idle cues with an event: {int((df[(df.cue == 'idle')].trial.nunique()))} of "
          f"{int((rec.cues.motion == 'idle').sum())}", ""]

    # B. features per motion
    one = found[found.label.isin(MOTIONS)]
    cols = ["share_x", "share_y", "share_z", "first_lobe_x", "first_lobe_y", "first_lobe_z",
            "loop_xy", "loop_xz", "loop_yz", "duration", "peak_rot"]
    g = one.groupby("label")[cols].mean().reindex([m for m in MOTIONS if m in set(one.label)])
    g.insert(0, "n", one.groupby("label").size())
    L += ["## B. Head-frame features per motion (mean)", "",
          "x = ear-to-ear axis (nod), y = nose axis (tilt), z = vertical (turn).", "", table(g), ""]

    # C. direction pairs
    pairs = [("nod_down", "look_up", "first_lobe_x"), ("tilt_left", "tilt_right", "first_lobe_y"),
             ("turn_left", "turn_right", "first_lobe_z")]
    loops = [c for c in ("loop_xy", "loop_xz", "loop_yz")]
    if {"circle_cw", "circle_ccw"} <= set(one.label):
        cw, ccw = one[one.label == "circle_cw"], one[one.label == "circle_ccw"]
        best = max(loops, key=lambda c: abs(cw[c].mean() - ccw[c].mean()))
        pairs.append(("circle_cw", "circle_ccw", best))
    rows = []
    for m1, m2, f in pairs:
        v1, v2 = one[one.label == m1][f], one[one.label == m2][f]
        if len(v1) == 0 or len(v2) == 0:
            continue
        s1 = np.sign(v1.median())
        rows.append({"pair": f"{m1} vs {m2}", "feature": f,
                     f"first: sign {'+' if s1 > 0 else '-'}": f"{int((np.sign(v1) == s1).sum())}/{len(v1)}",
                     "second: opposite sign": f"{int((np.sign(v2) == -s1).sum())}/{len(v2)}"})
    L += ["## C. Direction pairs: does one sign separate them?", "",
          pd.DataFrame(rows).to_markdown(index=False), ""]

    # D1. EarSet -> this person
    es = pd.read_csv(OUT_DIR / "earset_events.csv")
    to_es = {"nod_down": "nod", "look_up": "nod", "tilt_left": "tilt", "tilt_right": "tilt",
             "turn_left": "shake", "turn_right": "shake"}
    m = one[one.label.isin(to_es)].copy()
    m["y"] = m.label.map(to_es)
    L += ["## D1. Model trained only on EarSet (30 other people, other earbud) → this person", "",
          "Classes nod / shake (= turn) / tilt / none; circles are not in EarSet.", ""]
    for title, cols_ in [("axis features", AXIS), ("axis + signed + timing",
                                                    AXIS + list(FEATURE_SETS["signed"][1]) + list(FEATURE_SETS["timing"][1]))]:
        clf = logreg().fit(es[cols_], es.label)
        pr = clf.predict(m[cols_])
        L += [f"- {title}: **{(pr == m.y).mean():.2f}** ({int((pr == m.y).sum())}/{len(m)}); "
              f"predicted 'none' {(pr == 'none').mean():.0%}"]
    L += [""]

    # D2. within session, leave one event out
    X, y = one[AXSIGN].to_numpy(), one.label.to_numpy()
    pred = []
    for i in range(len(one)):
        tr = np.arange(len(one)) != i
        if len(set(y[tr])) < 2:
            pred.append("?")
            continue
        pred.append(logreg().fit(X[tr], y[tr]).predict(X[i:i + 1])[0])
    pred = np.array(pred)
    cm = pd.crosstab(pd.Series(y, name="true"), pd.Series(pred, name="predicted"))
    L += ["## D2. Within this session, leave one event out (8 motions, axis + signed features)", "",
          f"Accuracy **{(pred == y).mean():.2f}** ({int((pred == y).sum())}/{len(y)}), "
          f"{len(y) / max(len(set(y)), 1):.1f} examples per motion.", "", cm.to_markdown(), ""]

    # D3. across sessions
    if a.earlier:
        cfg = PipelineConfig()
        cfg.features.sets = SETS
        old = earlier_events(*a.earlier, cfg)
        shared = [c for c in ("tilt_left", "tilt_right", "turn_left", "turn_right", "circle_cw") if c in set(old.label)]
        tr = old[old.label.isin(shared)]
        te = one[one.label.isin(shared)]
        clf = logreg().fit(tr[AXSIGN], tr.label)
        pr = clf.predict(te[AXSIGN])
        L += ["## D3. Across sessions: earlier Mac recording → app session", "",
              f"Trained on {len(tr)} events of the earlier recording (taken off and put back in between, different "
              f"calibration), tested on {len(te)} app-session events of the same motions ({', '.join(shared)}).", "",
              f"Accuracy **{(pr == te.label).mean():.2f}** ({int((pr == te.label).sum())}/{len(te)})", "",
              pd.crosstab(pd.Series(te.label.to_numpy(), name="true"), pd.Series(pr, name="predicted")).to_markdown(), ""]

    # E. false gestures in no-gesture recordings
    if a.negatives:
        clf = logreg().fit(one[AXSIGN], one.label)
        rows = []
        for f in a.negatives:
            r = load_session(f)
            pn = Pipeline(p.cfg)
            pn.calibrations = p.calibrations
            evn = pn.extract(r)
            hours = len(r) / r.fs / 3600
            if evn:
                feats = [dict(zip(NAMES, e.features)) for e in evn]
                P = clf.predict_proba(pd.DataFrame([[f[c] for c in AXSIGN] for f in feats], columns=AXSIGN))
                top = P.max(1)
            else:
                top = np.array([])
            rows.append({"recording": Path(f).name, "minutes": len(r) / r.fs / 60, "events": len(evn),
                         "events / h": len(evn) / hours,
                         "gesture with p ≥ 0.7, / h": (top >= 0.7).sum() / hours,
                         "gesture with p ≥ 0.9, / h": (top >= 0.9).sum() / hours})
        L += ["## E. No-gesture recordings: false single gestures", "",
              "The within-person model has no 'none' class yet (no idle/negative events in this session), so every "
              "event it sees is forced into a gesture; only the probability gate can reject it. Short recordings: "
              "indicative only.", "", pd.DataFrame(rows).to_markdown(index=False, floatfmt=".1f"), ""]

    Path(a.out).write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
