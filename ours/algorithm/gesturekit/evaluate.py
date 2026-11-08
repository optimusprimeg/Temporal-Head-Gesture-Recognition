"""Metrics: events against a truth table, false alarms per hour, commands."""
import numpy as np
import pandas as pd


def match_events(events, truth, min_overlap=0.3):
    """Greedy one-to-one matching of detected events to true motions (truth: t_start, t_end, label) by time
    overlap; a match needs overlap >= min_overlap x the true duration. Returns (matches, unmatched_event_idx)."""
    used, matches = set(), []
    for k, tr in truth.reset_index(drop=True).iterrows():
        best, best_ov = None, 0.0
        for i, e in enumerate(events):
            if i in used:
                continue
            ov = min(tr.t_end, e.t_end) - max(tr.t_start, e.t_start)
            if ov > best_ov:
                best, best_ov = i, ov
        hit = best is not None and best_ov >= min_overlap * (tr.t_end - tr.t_start)
        if hit:
            used.add(best)
        matches.append({"truth": k, "label": tr.label, "event": best if hit else None,
                        "onset_error_s": (events[best].t_start - tr.t_start) if hit else np.nan})
    return pd.DataFrame(matches), [i for i in range(len(events)) if i not in used]


def detection_summary(events, truth):
    m, extra = match_events(events, truth)
    return {"true_motions": len(truth), "detected": float(m.event.notna().mean()) if len(m) else np.nan,
            "extra_events": len(extra), "median_onset_error_s": float(m.onset_error_s.median())}


def rate_per_hour(count, seconds):
    return count / (seconds / 3600) if seconds > 0 else np.nan


def command_summary(commands, expected):
    """expected: list of (t_cue, first, second, message). A command counts as correct if it has the right message
    and starts within 6 s after its cue; every other sent command is a false command."""
    used, correct = set(), 0
    for t_cue, a, b, msg in expected:
        for i, c in enumerate(commands):
            if i not in used and c.message == msg and 0 <= c.t_start - t_cue <= 6.0:
                used.add(i)
                correct += 1
                break
    return {"expected": len(expected), "correct": correct, "false_commands": len(commands) - len(used)}
