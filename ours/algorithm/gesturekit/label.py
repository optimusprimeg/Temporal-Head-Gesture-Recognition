"""Ground-truth labels for detected events, from the cue log (rules: experimental_design.md section 6b).

For every cue with a motion, the window is [t_s, t_s + window_s] (window_s is written by the collector per cue).
    motion cue (rounds, pairs)  -> the first event STARTING inside the window gets the motion; any further ones are
                                   'extra' (flagged); none at all -> the cue is 'missed'
    command cue ('a>b')         -> first event = a, second = b, more = 'extra'
    idle cue, negatives block   -> every event inside = 'none'
    calibration                 -> 'calibration' (never used for training or testing)
    practice (app v2)           -> 'practice' (never used for training or testing)
    re-wear (start..end)        -> 'ignore' (hands at the ears)
    cue with status skipped / disturbed (app v2: experimenter skip, earbud switch or data gap; the app repeats
                                   disturbed trials) -> events in its window 'ignore'
    self_paced                  -> 'self_paced' (scored at sequence level, not per event)
    anything else (gaps between cues, re-wear) -> 'none', except events starting within ignore_margin_s of a motion
                                   window -> 'ignore' (half motions, late or early starts)
Returns per-event labels and a per-cue report.
"""
import numpy as np
import pandas as pd

from .config import LabelConfig

MOTION_KINDS = ("rounds", "pairs", "commands")


def label_events(events, cues, cfg=LabelConfig()):
    starts = np.array([e.t_start for e in events])
    labels = np.full(len(events), "none", dtype=object)
    claimed = np.zeros(len(events), bool)
    report = []
    c = cues.sort_values("t_s")
    bad = c.status.isin(["skipped", "disturbed"]) if "status" in c else pd.Series(False, index=c.index)

    def window_start(cue):
        """Motion windows open early_s before GO, or at the announcement (app v2.1) if that is earlier."""
        lo = cue.t_s - cfg.early_s
        if "shown_t_s" in cue and pd.notna(cue.shown_t_s):
            lo = min(lo, cue.shown_t_s - cfg.shown_margin_s)
        return lo

    for idx, cue in c.iterrows():  # 1. windows that fix the label of everything inside
        lo = cue.t_s
        if bad[idx] and cue.kind not in ("calibration",):
            hi, lab = lo + float(cue.window_s), "ignore"
        elif cue.kind == "calibration":
            hi, lab = lo + max(float(cue.window_s), 2.0), "calibration"
        elif cue.kind == "practice":
            lo = window_start(cue)
            hi, lab = cue.t_s + float(cue.window_s), "practice"
        elif cue.kind in ("self_paced", "rewear") and cue.step == 0:
            ends = c[(c.kind == cue.kind) & (c["round"] == cue["round"]) & (c.step == 1) & (c.t_s > lo)].t_s
            hi = float(ends.iloc[0]) if len(ends) else lo + 60
            lab = "self_paced" if cue.kind == "self_paced" else "ignore"
        elif cue.kind == "negatives":
            hi, lab = lo + float(cue.window_s), "none"
        else:
            continue
        labels[(starts >= lo) & (starts < hi)] = lab
        claimed[(starts >= lo) & (starts < hi)] = True

    motion_windows = []
    for _, cue in c[c.kind.isin(MOTION_KINDS) & ~bad].iterrows():  # 2. motion cues
        lo, hi = window_start(cue), cue.t_s + float(cue.window_s)
        motion_windows.append((lo, hi))
        inside = np.where((starts >= lo) & (starts < hi) & ~claimed)[0]
        expected = cue.motion.split(">") if ">" in str(cue.motion) else [cue.motion]
        if cue.motion == "idle":
            labels[inside], claimed[inside] = "none", True
            report.append({"trial": cue.trial, "kind": cue.kind, "motion": "idle", "t_s": lo, "events": len(inside),
                           "status": "ok"})
            continue
        chosen = list(inside)
        if cfg.pick == "largest" and len(inside) > len(expected):
            energy = {i: (float((events[i].rot ** 2).sum()) if events[i].rot is not None   # rotation energy
                          else events[i].t_end - events[i].t_start) for i in inside}
            chosen = sorted(sorted(inside, key=lambda i: -energy[i])[:len(expected)])  # biggest ones, in time order
        for i in inside:
            labels[i] = "extra"
            claimed[i] = True
        for k, i in enumerate(chosen[:len(expected)]):
            labels[i] = expected[k]
        status = "missed" if len(inside) == 0 else ("extra" if len(inside) > len(expected) else
                                                    ("partial" if len(inside) < len(expected) else "ok"))
        report.append({"trial": cue.trial, "kind": cue.kind, "motion": cue.motion, "t_s": lo,
                       "events": len(inside), "status": status})

    m = cfg.ignore_margin_s  # 3. near-miss starts around motion windows
    for i in np.where(~claimed)[0]:
        if any(lo - m <= starts[i] < lo or hi <= starts[i] < hi + m for lo, hi in motion_windows):
            labels[i] = "ignore"
    for e, lab in zip(events, labels):
        e.meta["label"] = lab
        if lab not in ("none", "ignore", "calibration", "practice", "self_paced", "extra") and e.t_end - e.t_start > cfg.max_event_s:
            e.meta["flag"] = "long"
    return labels, pd.DataFrame(report)


TRAINABLE_EXCLUDE = ("ignore", "calibration", "practice", "self_paced", "extra")


def trainable(events):
    """Events usable for training/testing a classifier, with their labels."""
    keep = [e for e in events if e.meta.get("label") not in TRAINABLE_EXCLUDE]
    return keep, [e.meta["label"] for e in keep]
