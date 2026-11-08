"""Are two-motion commands reliable? Offline test of the live pipeline before the pilot -> results/pair_reliability.md

The live app does: detector (quiet x3) -> head frame -> features -> Rules or Model (live_model.json) -> pair decoder.
This script runs the same chain in Python (the Swift code is checked equal to it in CI) on two kinds of data:

A. REAL back-to-back motions, 4 people: the earlier teammates' AirPods Pro 2 takes (prior_work/gesture_lab/data/raw),
   'tilt_2x_left', 'tilt_2x_right', 'nod_2x_front' = the same motion done twice in a row, at the person's own pace,
   in 2.5 s cued takes. Each take is padded with that person's own still signal (with the gravity of the person's nearest idle take:
   2.5 s takes often start mid-motion) so the
   detector sees a continuous stream. Question: does the detector give TWO events, and are both named right? These 4 people were never used
   for training or tuning (clean test), but doubles are a stress test: people did them fast, with no pause.
   Head frame: from that person's first 3 double nods (excluded from the test).

B. COMMANDS from P01's real single motions, stitched: two of Ghanshyam's recorded motions (raw samples) joined by
   a pause of g seconds of his own still signal, for every command of the dictionary. Question: from which pause on
   does the full chain give the right command? Caveat: P01's motions were in the model's training data, and the
   joins are artificial (the motion snippets come from different moments).
Run from ours/algorithm: python scripts/pair_reliability.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT.parent / "archive" / "collector_v3"))
from config import COMMANDS  # noqa: E402  ours/archive/collector_v3/config.py: the 20 placeholder commands
from gesturekit.config import PipelineConfig  # noqa: E402
from gesturekit.decode import Motion, PairDecoder  # noqa: E402
from gesturekit.detect import quiet_from  # noqa: E402
from gesturekit.features import FEATURE_SETS  # noqa: E402
from gesturekit.frames import HeadFrame, calibrate  # noqa: E402
from gesturekit.io import load_old_takes, load_session  # noqa: E402
from gesturekit.pipeline import Calibration, Pipeline  # noqa: E402
from gesturekit.recording import Recording  # noqa: E402

MODEL = json.loads((ROOT.parent / "mac_app" / "GestureCollector" / "live_model.json").read_text())
NAMES = [n for s in ("axis", "signed", "timing", "magnitude") for n in FEATURE_SETS[s][1]]
SETS = ("axis", "signed", "timing", "magnitude")
DOUBLE = {"tilt_2x_left": "tilt_left", "tilt_2x_right": "tilt_right", "nod_2x_front": "nod_down"}
rng = np.random.default_rng(0)


# ------------------------------------------------------------------ the app's decision, from live_model.json
def feats(e):
    f = dict(zip(NAMES, e.features))
    for p in ("xy", "xz", "yz"):
        f[f"abs_loop_{p}"] = abs(f[f"loop_{p}"])
    return f


def direction(kind, f):
    if kind == "none":
        return "none"
    d = MODEL["direction"][kind]
    return d["positive"] if f[d["feature"]] > 0 else d["negative"]


def rules(f):
    s = [f["share_x"], f["share_y"], f["share_z"]]
    i = int(np.argmax(s))
    if s[i] >= MODEL["rules"]["axis_share"]:
        k = ["nod", "tilt", "turn"][i]
    elif max(f["abs_loop_xy"], f["abs_loop_xz"], f["abs_loop_yz"]) >= MODEL["rules"]["loop_min"]:
        k = "circle"
    else:
        k = "none"
    return direction(k, f), k != "none"


def model(f):
    z = (np.array([f[n] for n in MODEL["features"]]) - MODEL["mean"]) / MODEL["scale"]
    lg = np.array(MODEL["coef"]) @ z + MODEL["intercept"]
    p = np.exp(lg - lg.max()); p /= p.sum()
    o = np.argsort(p)[::-1]
    k = MODEL["classes"][o[0]]
    ok = k != "none" and p[o[0]] >= MODEL["gate"]["min_confidence"] and p[o[0]] - p[o[1]] >= MODEL["gate"]["min_margin"]
    return direction(k, f), ok


def like(x, neighbour, at_start):
    """Still signal x with the gravity of the neighbouring motion snippet (its first or last sample): padding cut
    from other moments has another head/earbud orientation, and the head frame reads gravity just before an event."""
    x = x.copy()
    x[:, 6:9] = neighbour[0 if at_start else -1, 6:9]
    return x


def neutral(x, g):
    """Still signal x with gravity g (the person's neutral head, from the nearest idle take)."""
    x = x.copy()
    x[:, 6:9] = g
    return x


def stream(parts, fs):
    X = np.concatenate(parts)
    return Recording(np.arange(len(X)) / fs, X, fs, np.ones(len(X), bool), {})


def pipeline(quiet, frame, split=False):
    cfg = PipelineConfig(); cfg.features.sets = SETS; cfg.detector.split_returns = split
    p = Pipeline(cfg); p.calibrations = [Calibration(0.0, quiet, frame)]
    return p


# ------------------------------------------------------------------ A. real doubles, 4 people
def still_parts(takes, fs, n):
    """n samples of the person's genuinely still signal, cut from their idle takes (lowest-rotation quarter)."""
    idle = [r.X for r in takes if r.meta["label"] == "idle"]
    allq = np.concatenate(idle)
    thr = np.percentile(np.linalg.norm(allq[:, :3], axis=1), 25)
    runs = []
    for x in idle:
        still = np.r_[np.linalg.norm(x[:, :3], axis=1) < thr, False]
        st = None
        for i, s in enumerate(still):
            if s and st is None:
                st = i
            elif not s and st is not None:
                if i - st >= 10:
                    runs.append(x[st:i])
                st = None
    out, tot = [], 0
    while tot < n:
        r = runs[rng.integers(len(runs))]
        out.append(r); tot += len(r)
    return np.concatenate(out)[:n]


rows_a = []
for subj in (1, 2, 3, 4):
    takes = load_old_takes(subj)
    fs = takes[0].fs
    pad = lambda: still_parts(takes, fs, int(2.0 * fs))  # noqa: E731
    qrec = stream([still_parts(takes, fs, int(6 * fs))], fs)
    quiet = quiet_from(qrec, 0, len(qrec))
    nods = [r for r in takes if r.meta["label"] == "nod_2x_front"]
    idle_idx = [i for i, r in enumerate(takes) if r.meta["label"] == "idle"]
    pos = {id(r): i for i, r in enumerate(takes)}

    def g0(r):  # neutral gravity: mean of the nearest idle take in recording order
        j = min(idle_idx, key=lambda k: abs(k - pos[id(r)]))
        return takes[j].grav.mean(axis=0)
    # head frame from the first 3 double nods (chin down first, as the calibration assumes)
    cal_rec = stream(sum(([neutral(pad(), g0(r)), r.X, neutral(pad(), g0(r))] for r in nods[:3]), []), fs)
    ev = pipeline(quiet, None).extract(cal_rec)
    big = sorted(ev, key=lambda e: -float((e.rot ** 2).sum()))[:3]
    frame = calibrate(cal_rec, [(e.start, e.end) for e in sorted(big, key=lambda e: e.start)])
    for r in takes:
        lab = r.meta["label"]
        if lab not in DOUBLE or (lab == "nod_2x_front" and any(r is c for c in nods[:3])):
            continue
        a = int(2.0 * fs)
        rec = stream([neutral(pad(), g0(r)), r.X, neutral(pad(), g0(r))], fs)
        flipped = HeadFrame(frame.heading + np.pi, frame.n_nods)   # as if the person nodded chin UP first
        for split, fr, tag in ((False, frame, "calibrated"), (True, frame, "calibrated"), (False, flipped, "flipped")):
            evs = [e for e in pipeline(quiet, fr, split).extract(rec) if a - 10 <= e.start < a + len(r.X)]
            names_r = [rules(feats(e)) for e in evs]
            names_m = [model(feats(e)) for e in evs]
            want = DOUBLE[lab]
            rows_a.append({"person": f"A{subj}", "double": lab, "split_returns": split, "frame": tag, "events": len(evs),
                           "rules_both": len(evs) == 2 and all(n == want and ok for n, ok in names_r),
                           "model_both": len(evs) == 2 and all(n == want and ok for n, ok in names_m),
                           "rules_any": any(n == want and ok for n, ok in names_r),
                           "durations": [round(e.t_end - e.t_start, 2) for e in evs]})
A_all = pd.DataFrame(rows_a)
A, A_flip = A_all[A_all.frame == "calibrated"], A_all[A_all.frame == "flipped"]

# ------------------------------------------------------------------ B. stitched commands from P01's singles
DATA = ROOT.parent / "data" / "internal GG 01"
SESSION = DATA / "P01_ghanshyam_s1_airpodspro2_20261107_024251" / "P01_ghanshyam_s1_airpodspro2_20261107_024251"
sys.path.insert(0, str(ROOT / "scripts"))
import person_report as pr  # noqa: E402

srec, sp, sev, _, sdf = pr.session_events(str(SESSION), 1.5)
sdf = sdf[sdf.nth == 0]
by_start = {e.t_start: e for e in sev}
snips = {}
for _, r in sdf.iterrows():
    e = by_start[r.t_start]
    snips.setdefault(r.label, []).append(srec.X[e.start:e.end])
still = load_session(str(DATA / "airpods_20261107_002835.csv"))
fsb = srec.fs
cal = sp.calibration_at(by_start[sdf.t_start.iloc[0]].t_start)
qb = cal.quiet


def still_b(n):
    x = still.X[: len(still)]
    s = rng.integers(0, max(1, len(x) - n))
    out = x[s:s + n]
    while len(out) < n:
        out = np.concatenate([out, x[:n - len(out)]])
    return out


GAPS = [0.1, 0.3, 0.5, 0.8, 1.2]
rows_b = []
cmds = {k: v for k, v in COMMANDS.items() if k[0] in snips and k[1] in snips}
for gap in GAPS:
    for (m1, m2), msg in cmds.items():
        for rep in range(3):
            s1 = snips[m1][rng.integers(len(snips[m1]))]
            s2 = snips[m2][rng.integers(len(snips[m2]))]
            rec = stream([like(still_b(int(2 * fsb)), s1, True), s1, like(still_b(max(1, int(gap * fsb))), s2, True),
                          s2, like(still_b(int(2.5 * fsb)), s2, False)], fsb)
            evs = pipeline(qb, cal.frame).extract(rec)
            out = {}
            for mode, fn in (("rules", rules), ("model", model)):
                dec = PairDecoder(COMMANDS)
                got = None
                for e in evs:
                    name, ok = fn(feats(e))
                    if ok:
                        c = dec.push(Motion(name, e.t_start, e.t_end, 1.0))
                        if c is not None:
                            got = c.message
                out[mode] = got
            rows_b.append({"gap_s": gap, "command": msg, "events": len(evs), "rules": out["rules"] == msg,
                           "model": out["model"] == msg})
B = pd.DataFrame(rows_b)

# ------------------------------------------------------------------ report
L = ["# Two-motion commands: reliability test before the pilot", "",
     "Generated by `algorithm/scripts/pair_reliability.py`: the live app's chain (detector with quiet x3 -> head "
     "frame -> features -> Rules or Model from `live_model.json` -> pair decoder) run in Python.", "",
     "**Summary.** (1) Two motions done back to back without a pause merge into ONE detected event (real doubles of 4 "
     "people: 84-89 % merged), so the command is lost. The detector needs ~0.4 s of stillness to end a motion. (2) With "
     "a pause of 0.5 s or more between the two motions, the full chain gets about 9 in 10 commands right on P01's "
     "motions (most failures involve circles). (3) Naming on NEW people is not shown by this test: only the live test "
     "(or the pilot) can show it.", "",
     "## A. Real back-to-back motions, 4 people never used for training (old AirPods Pro 2 takes)", "",
     "The same motion twice in a row, at the person's own (fast) pace. Success = the detector gives exactly two "
     "events and both get the right name. `split_returns` = the detector option that cuts an event where the head is "
     "back at the start and nearly still (off in the app today).", ""]
for split in (False, True):
    s = A[A.split_returns == split]
    L += [f"**split_returns = {split}** ({len(s)} doubles)", "",
          s.groupby("double").agg(n=("events", "size"), two_events=("events", lambda x: f"{(x == 2).mean():.2f}"),
                                  one_event=("events", lambda x: f"{(x == 1).mean():.2f}"),
                                  rules_both_right=("rules_both", "mean"), model_both_right=("model_both", "mean"),
                                  rules_at_least_one=("rules_any", "mean")).round(2).to_markdown(), "",
          "Per person (two events and both right, Rules): " +
          ", ".join(f"{p} {g.rules_both.mean():.2f}" for p, g in s.groupby("person")), "",
          f"Event length when merged into one event: median "
          f"{np.median([d[0] for d in s[s.events == 1].durations]) if (s.events == 1).any() else float('nan'):.2f} s", ""]
L += ["**Naming check.** Even when merged, a double tilt-left is still a tilt whose first swing goes left, so "
      "'at least one right' should be high; it is not. Flipping the nod sign (as if these people nodded chin UP first) "
      "does not fix it either, so it is not only the calibration sign:", "",
      A_flip.groupby("double").rules_any.mean().round(2).to_frame("rules_at_least_one, sign flipped").to_markdown(), "",
      "Whole-person head-frame shares on this data are right (tilts load on the tilt axis), so the per-event naming of "
      "these old cut takes fails for reasons not pinned down here (merged double motions mix axes and swings; 2.5 s "
      "takes often start mid-motion, so the head posture before an event is unknown). Treat part A as evidence about "
      "MERGING only, not about naming.", ""]
L += ["## B. Commands built from P01's real single motions, by pause between the two motions", "",
      f"{len(cmds)} commands of the dictionary whose motions P01 recorded, 3 random versions each, per pause. "
      "Success = the decoder outputs exactly that command. P01's motions were in the model's training data.", "",
      B.groupby("gap_s").agg(n=("command", "size"), rules=("rules", "mean"), model=("model", "mean"),
                             events_median=("events", "median")).round(2).to_markdown(), ""]
bad = B[(B.gap_s >= 0.5) & ~B.rules].command.value_counts()
L += ["Commands that failed with Rules at pauses >= 0.5 s: " +
      (", ".join(f"{k} ({v})" for k, v in bad.items()) if len(bad) else "none"), ""]
out = ROOT / "results" / "pair_reliability.md"
out.write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
