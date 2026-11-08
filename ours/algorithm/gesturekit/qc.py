"""Quality checks for one recording (run after every session). Each check returns (passed, value, rule)."""
import numpy as np
import pandas as pd


def check_recording(rec, cue_report=None, events=None, feature_names=None):
    rows = []

    def add(name, ok, value, rule):
        rows.append({"check": name, "passed": bool(ok), "value": value, "rule": rule})

    dt = np.diff(rec.t[rec.valid]) if rec.valid.sum() > 1 else np.array([np.nan])
    add("sample rate", 20 <= rec.fs <= 110, f"{rec.fs:.0f} Hz", "50 Hz (25 Hz on some AirPods models)")
    invalid = 1 - rec.valid.mean()
    add("missing samples", invalid < 0.02, f"{invalid:.2%}", "under 2 % of the grid inside gaps")
    gaps = np.diff(np.r_[0, (~rec.valid).astype(int), 0])
    longest = (np.where(gaps == -1)[0] - np.where(gaps == 1)[0]).max() / rec.fs if (gaps == 1).any() else 0.0
    add("longest gap", longest < 1.0, f"{longest:.2f} s", "no gap of 1 s or more")
    gm = np.median(np.linalg.norm(rec.grav[rec.valid], axis=1))
    add("gravity magnitude", abs(gm - 9.81) < 0.3, f"{gm:.2f} m/s^2", "9.81 +- 0.3 (units check)")
    switches = rec.meta.get("earbud_switches", [])
    if switches:
        cal_t = ([] if rec.cues is None else
                 list(rec.cues[(rec.cues.kind == "calibration") & (rec.cues.motion == "still")].t_s))
        uncal = [s for s in switches if not any(c > s["t_s"] for c in cal_t)]
        add("earbud switch", not uncal,
            "; ".join(f"{s['t_s']:.1f} s {s['from']}->{s['to']}" for s in switches),
            "every switch to the other bud is followed by a new calibration (still + 3 nods)")
    if rec.cues is not None:
        cal = rec.cues[rec.cues.kind == "calibration"]
        still = cal[cal.motion == "still"]
        if len(still):
            a, b = rec.index(still.t_s.iloc[0] + 0.5), rec.index(still.t_s.iloc[0] + 3.5)
            g = np.median(np.linalg.norm(rec.rot[a:b], axis=1))
            add("calibration still", g < 0.05, f"{g:.3f} rad/s", "still pose: rotation under 0.05 rad/s")
        add("calibration nods", (cal.motion == "calib_nod").sum() >= 3, int((cal.motion == "calib_nod").sum()),
            "at least 3 calibration nods")
    if cue_report is not None and len(cue_report):
        mot = cue_report[cue_report.motion != "idle"]
        missed = (mot.status == "missed").mean() if len(mot) else 0
        add("missed cues", missed < 0.05, f"{missed:.1%}", "under 5 % of motion cues without a detected event")
        extra = (mot.status == "extra").mean() if len(mot) else 0
        add("double events", extra < 0.10, f"{extra:.1%}", "under 10 % of cues with more events than expected")
    planes = [n for n in ("loop_xy", "loop_xz", "loop_yz") if feature_names and n in feature_names]
    if events and planes:
        means = {}
        for n in planes:  # the circle's plane depends on the instruction (nose clock: x-z; head roll: x-y)
            k = feature_names.index(n)
            means[n] = [np.mean([e.features[k] for e in events if e.meta.get("label") == lab] or [np.nan])
                        for lab in ("circle_cw", "circle_ccw")]
        if not np.isnan(list(means.values())).any():
            best = max(means, key=lambda n: abs(means[n][0] - means[n][1]))
            cw, ccw = means[best]
            add("circle direction", np.sign(cw) != np.sign(ccw), f"{best}: cw {cw:+.3f}, ccw {ccw:+.3f}",
                "cw and ccw loop opposite ways in their main plane (catches swapped labels)")
    return pd.DataFrame(rows)
