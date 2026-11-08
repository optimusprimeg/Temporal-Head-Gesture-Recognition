"""Process one collector-v3 session: load -> calibrate -> detect -> label -> quality checks.

    python scripts/process_session.py <session folder> [<more folders>...]

Writes into <session>/derived/:
    events.csv      one row per detected event: times, label (from the cue log), flag, all features
    cue_report.csv  per cue: how many events, ok / missed / extra / partial
    qc.md           quality checks (pass/fail)
Run this right after every recording; fix or re-record when qc.md shows a failure.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gesturekit.config import PipelineConfig  # noqa: E402
from gesturekit.io import load_session  # noqa: E402
from gesturekit.label import label_events  # noqa: E402
from gesturekit.pipeline import Pipeline  # noqa: E402
from gesturekit.qc import check_recording  # noqa: E402

ALL_SETS = ("axis", "signed", "timing", "magnitude")


def process(folder):
    folder = Path(folder)
    rec = load_session(folder)
    cfg = PipelineConfig()
    cfg.features.sets = ALL_SETS
    p = Pipeline(cfg)
    if rec.cues is not None and (rec.cues.kind == "calibration").any():
        p.calibrate_from_cues(rec)
    events = p.extract(rec)
    if rec.meta.get("appVersion") == "2.0.0":  # app v2.0: name + ready beep before GO, people start early
        cfg.label.early_s = 1.5
    labels, report = (label_events(events, rec.cues, cfg.label) if rec.cues is not None
                      else (["unlabelled"] * len(events), pd.DataFrame()))
    qc = check_recording(rec, report, events, p.feature_names)

    out = folder / "derived"
    out.mkdir(exist_ok=True)
    pd.DataFrame([{"t_start": e.t_start, "t_end": e.t_end, "latency_s": (e.finished_at - e.end) / rec.fs,
                   "label": e.meta.get("label"), "flag": e.meta.get("flag", ""),
                   "subject": rec.meta.get("subject"), "device": rec.meta.get("device"),
                   **dict(zip(p.feature_names, e.features))} for e in events]).to_csv(out / "events.csv", index=False)
    report.to_csv(out / "cue_report.csv", index=False)
    lines = [f"# Quality checks: {folder.name}", "",
             f"{len(rec) / rec.fs / 60:.1f} min, {len(events)} events, "
             f"{len(p.calibrations)} calibration block(s).", "",
             qc.to_markdown(index=False), ""]
    if len(report):
        lines += ["Cue status: " + ", ".join(f"{k} {v}" for k, v in report.status.value_counts().items()), ""]
    (out / "qc.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return qc.passed.all()


if __name__ == "__main__":
    ok = all(process(f) for f in sys.argv[1:])
    sys.exit(0 if ok else 1)
