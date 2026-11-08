"""End-to-end on simulated collector sessions: files -> load -> calibrate -> detect -> label -> train -> decode."""
import numpy as np
import pytest

from gesturekit.evaluate import command_summary, detection_summary
from gesturekit.io import load_session
from gesturekit.label import label_events, trainable
from gesturekit.pipeline import Pipeline
from gesturekit.qc import check_recording
from gesturekit.simulate import simulate_session

CMDS = {("tilt_left", "nod_down"): "GO", ("circle_cw", "nod_down"): "HELP", ("tilt_right", "tilt_left"): "MOVE"}


@pytest.fixture(scope="module")
def sessions(tmp_path_factory):
    out = []
    for subject, seed in [(2, 1), (4, 2)]:  # subjects 1 and 3 have no still data (their idle = talking)
        d = tmp_path_factory.mktemp(f"s{subject}")
        truth, clock_err = simulate_session(d, rounds=6, commands=CMDS, subject=subject, seed=seed)
        rec = load_session(d)
        p = Pipeline(commands=CMDS)
        p.calibrate_from_cues(rec)
        events = p.extract(rec)
        labels, report = label_events(events, rec.cues)
        out.append(dict(truth=truth, clock_err=clock_err, rec=rec, p=p, events=events, report=report))
    return out


def test_clock_alignment_is_close(sessions):
    for s in sessions:
        assert abs(s["clock_err"]) < 0.2


def _split_truth(s):
    t_cmd = s["rec"].cues[s["rec"].cues.kind == "commands"].t_s.min()
    return s["truth"][s["truth"].t_start < t_cmd], s["truth"][s["truth"].t_start >= t_cmd]


def test_detector_finds_single_cued_motions(sessions):
    for s in sessions:
        single, _ = _split_truth(s)
        d = detection_summary(s["events"], single)
        assert d["detected"] >= 0.9, d


def test_back_to_back_motions_report(sessions, capsys):
    """Known open problem: two motions with a short pause (commands) are often merged into one event. This test
    only records the rate; the fix (frames split_returns, end_s) must be judged on pilot data."""
    for s in sessions:
        _, pairs = _split_truth(s)
        d = detection_summary(s["events"], pairs)
        print(f"back-to-back motions found separately: {d['detected']:.2f}")
        assert d["true_motions"] == 6


def test_quality_checks_pass(sessions):
    for s in sessions:
        qc = check_recording(s["rec"], s["report"], s["events"], s["p"].feature_names)
        failing = qc[~qc.passed]
        assert failing.empty, failing.to_string()


def test_train_on_one_person_classify_and_decode_the_other(sessions):
    train, test = sessions
    ev_tr, y_tr = trainable(train["events"])
    p = test["p"]
    p.fit(ev_tr, y_tr)
    ev_te, y_te = trainable(test["events"])
    p.classify(ev_te)
    acc = np.mean([e.pred == y for e, y in zip(ev_te, y_te)])
    # Plumbing check, not a performance claim: 6 classes incl. none, a single simulated training person, double
    # gestures standing in for single ones. Chance is about 0.17; require 2x chance.
    assert acc > 0.35, acc
    p.classify(test["events"])
    cues = test["rec"].cues
    expected = [(r.t_s, *r.motion.split(">"), r.note) for _, r in cues[cues.kind == "commands"].iterrows()]
    summary = command_summary(p.decode(test["events"]), expected)
    assert summary["expected"] == 3


def test_app_v2_folder_segments_and_cue_status(tmp_path):
    """Gesture Collector app v2 layout: stream_000.csv + stream_001.csv (resume), cues with module/attempt/status,
    practice cues, a skipped cue and a disturbed (repeated) cue."""
    import pandas as pd
    simulate_session(tmp_path, rounds=2, commands=CMDS, subject=2, seed=3)
    s = pd.read_csv(tmp_path / "stream.csv")
    half = len(s) // 2
    s.iloc[:half].to_csv(tmp_path / "stream_000.csv", index=False)
    s.iloc[half + 100:].to_csv(tmp_path / "stream_001.csv", index=False)   # 2 s lost at the resume
    (tmp_path / "stream.csv").unlink()
    c = pd.read_csv(tmp_path / "cues.csv")
    c["module"], c["attempt"], c["status"] = "core", 1, "done"
    rounds = c.index[(c.kind == "rounds") & (c.motion != "idle")]
    c.loc[rounds[0], "kind"] = "practice"
    c.loc[rounds[1], "status"] = "skipped"
    c.loc[rounds[2], "status"] = "disturbed"
    c.to_csv(tmp_path / "cues.csv", index=False)

    rec = load_session(tmp_path)
    assert rec.meta["source"] == "gesture_collector_app"
    assert (~rec.valid).sum() >= 90                     # the resume gap is marked, not bridged
    p = Pipeline(commands=CMDS)
    p.calibrate_from_cues(rec)
    events = p.extract(rec)
    labels, report = label_events(events, rec.cues)
    starts = np.array([e.t_start for e in events])
    seen = 0
    for k, want in [(0, "practice"), (1, "ignore"), (2, "ignore")]:
        lo = rec.cues.loc[rounds[k], "t_s"]
        inside = (starts >= lo) & (starts < lo + rec.cues.loc[rounds[k], "window_s"])
        seen += inside.sum()
        assert all(labels[inside] == want), (k, labels[inside])
    assert seen >= 3, "each test window should contain its motion"
    assert not any(r["t_s"] in (rec.cues.loc[rounds[1], "t_s"], rec.cues.loc[rounds[2], "t_s"]) for _, r in report.iterrows())
    keep, labs = trainable(events)
    assert "practice" not in labs and "ignore" not in labs
