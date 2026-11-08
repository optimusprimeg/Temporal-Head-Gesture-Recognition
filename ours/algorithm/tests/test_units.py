"""Unit tests on synthetic signals with known answers. Run: python -m pytest tests -q (from ours/algorithm)."""
import numpy as np
import pandas as pd
import pytest

from gesturekit.config import DecoderConfig, DetectorConfig
from gesturekit.decode import Motion, PairDecoder, decode
from gesturekit.detect import Detector, detect, quiet_from
from gesturekit.features import axis_features, event_features, feature_names, signed_features
from gesturekit.frames import calibrate, rotation_to, to_head
from gesturekit.label import label_events
from gesturekit.pipeline import Event
from gesturekit.recording import Recording

FS = 50.0


def random_rotation(rng):
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    return q * np.sign(np.linalg.det(q))


def synth(head_axes_rot, R_head_to_sensor, n_quiet=100, noise=0.005, seed=0):
    """Recording whose motion is given in head axes (x = nod axis, z = up), seen by a sensor mounted with
    rotation R (sensor = R @ head). Gravity points down (Apple convention)."""
    rng = np.random.default_rng(seed)
    rot_head = np.vstack([np.zeros((n_quiet, 3)), head_axes_rot, np.zeros((n_quiet, 3))])
    n = len(rot_head)
    rot = rot_head @ R_head_to_sensor.T + rng.normal(0, noise, (n, 3))
    grav = np.tile(R_head_to_sensor @ np.array([0, 0, -9.81]), (n, 1))
    acc = rng.normal(0, noise, (n, 3))
    X = np.hstack([rot, acc, grav, np.full((n, 4), np.nan)])
    return Recording(np.arange(n) / FS, X, FS, np.ones(n, bool))


def swing(axis, sign=1.0, n=40, amp=2.0):
    w = np.zeros((n, 3))
    w[:, axis] = sign * amp * np.sin(np.linspace(0, 2 * np.pi, n))  # go and come back
    return w


# ----------------------------------------------------------------- frames
def test_rotation_to_handles_opposite_vectors():
    R = rotation_to(np.array([0, 0, -1.0]), np.array([0, 0, 1.0]))
    assert np.allclose(R @ [0, 0, -1.0], [0, 0, 1.0])
    assert np.isclose(np.linalg.det(R), 1.0)


@pytest.mark.parametrize("seed", range(5))
def test_head_frame_recovers_axes_and_signs_for_any_mounting(seed):
    R = random_rotation(np.random.default_rng(seed))
    nods = [synth(swing(0, +1), R, seed=s) for s in range(3)]
    calib = Recording(np.concatenate([r.t + 10 * i for i, r in enumerate(nods)]),
                      np.vstack([r.X for r in nods]), FS, np.ones(sum(len(r) for r in nods), bool))
    windows = [(i * 240 + 100, i * 240 + 140) for i in range(3)]
    frame = calibrate(calib, windows)
    for axis, name in [(0, "nod"), (1, "tilt"), (2, "turn")]:
        for sign in (+1, -1):
            rec = synth(swing(axis, sign), R, seed=seed + 10)
            acc, rot = to_head(rec, 100, 140, frame)
            share = axis_features(acc, rot, FS)[:3]
            assert share[axis] > 0.95, (name, share)
            lobe = signed_features(acc, rot, FS)[axis]
            assert np.sign(lobe) == sign, (name, sign, lobe)


# ----------------------------------------------------------------- detector
def noisy_stream(bursts, n=2000, seed=0):
    rng = np.random.default_rng(seed)
    rot = rng.normal(0, 0.01, (n, 3))
    acc = rng.normal(0, 0.01, (n, 3))
    for a, b in bursts:
        rot[a:b, 0] += 2.0 * np.sin(np.linspace(0, 2 * np.pi, b - a))
    X = np.hstack([rot, acc, np.tile([0, 0, -9.81], (n, 1)), np.full((n, 4), np.nan)])
    return Recording(np.arange(n) / FS, X, FS, np.ones(n, bool))


def test_detector_finds_each_burst_with_bounded_latency():
    bursts = [(300, 350), (700, 800), (1200, 1230)]
    rec = noisy_stream(bursts)
    q = quiet_from(rec, 0, 250)
    ev = detect(rec, DetectorConfig(fs=FS), q)
    assert len(ev) == 3
    for (a, b, fin), (ta, tb) in zip(ev, bursts):
        assert a <= ta + 5 and b >= tb - 10
        assert (fin - b) / FS <= DetectorConfig().end_s + 0.05


def test_detector_splits_long_motion_and_stops_at_gap():
    rec = noisy_stream([(200, 600)])
    q = quiet_from(rec, 0, 150)
    ev = detect(rec, DetectorConfig(fs=FS, max_s=2.0), q)
    assert len(ev) >= 4 and all((b - a) / FS <= 2.0 + 1e-9 for a, b, _ in ev)
    rec.valid[400:410] = False
    ev2 = detect(rec, DetectorConfig(fs=FS), q)
    assert any(b <= 401 for a, b, _ in ev2) and any(a >= 409 for a, b, _ in ev2)


def test_detector_uses_only_past_samples():
    rec = noisy_stream([(300, 350), (900, 950)])
    q = quiet_from(rec, 0, 250)
    full = detect(rec, DetectorConfig(fs=FS), q)
    rec.X[600:] = np.random.default_rng(1).normal(0, 3, rec.X[600:].shape)  # change the future
    part = detect(rec, DetectorConfig(fs=FS), q)
    assert full[0] == part[0]


# ----------------------------------------------------------------- decoder
def M(label, t0):
    return Motion(label, t0, t0 + 0.8, 0.9)


CMDS = {("tilt_left", "nod_down"): "GO", ("nod_down", "tilt_left"): "BACK"}


def test_pair_within_timeout_is_a_command():
    out = decode([M("tilt_left", 0), M("nod_down", 1.5)], CMDS)
    assert [c.message for c in out] == ["GO"]


def test_lone_motion_and_late_second_are_dropped():
    assert decode([M("tilt_left", 0)], CMDS) == []
    assert decode([M("tilt_left", 0), M("nod_down", 0.8 + 1.6)], CMDS) == []


def test_unknown_pair_makes_second_the_new_first():
    out = decode([M("tilt_right", 0), M("tilt_left", 1.2), M("nod_down", 2.4)], CMDS)
    assert [c.message for c in out] == ["GO"]


def test_same_motion_twice_blocked_unless_allowed():
    cmds = {("nod_down", "nod_down"): "ACK"}
    assert decode([M("nod_down", 0), M("nod_down", 1.2)], cmds) == []
    assert len(decode([M("nod_down", 0), M("nod_down", 1.2)], cmds, DecoderConfig(allow_same_twice=True))) == 1


# ----------------------------------------------------------------- labeller
def ev(t):
    return Event(0, 1, 1, t, t + 1.0, None, None, None, {})


def test_labeller_rules():
    cues = pd.DataFrame([
        {"t_s": 0.0, "kind": "calibration", "motion": "still", "window_s": 4.0, "trial": 1, "step": 0, "round": 0},
        {"t_s": 10.0, "kind": "rounds", "motion": "tilt_left", "window_s": 4.0, "trial": 2, "step": 0, "round": 1},
        {"t_s": 20.0, "kind": "rounds", "motion": "idle", "window_s": 4.0, "trial": 3, "step": 0, "round": 1},
        {"t_s": 30.0, "kind": "rounds", "motion": "nod_down", "window_s": 4.0, "trial": 4, "step": 0, "round": 1},
        {"t_s": 40.0, "kind": "commands", "motion": "tilt_left>nod_down", "window_s": 6.0, "trial": 5, "step": 0,
         "round": 1},
        {"t_s": 60.0, "kind": "negatives", "motion": "none", "window_s": 60.0, "trial": 6, "step": 0, "round": 0},
    ])
    events = [ev(1.0), ev(10.5), ev(12.0), ev(21.0), ev(14.2), ev(26.0), ev(41.0), ev(43.0), ev(70.0)]
    labels, report = label_events(events, cues)
    assert list(labels) == ["calibration", "tilt_left", "extra", "none", "ignore", "none", "tilt_left", "nod_down",
                            "none"]
    assert report.set_index("trial").loc[4, "status"] == "missed"


def test_labeller_window_opens_at_announcement_and_takes_largest_event():
    """App v2.1 logs when a cue is announced: a motion started after the announcement but before GO gets the label;
    without the announcement it would fall outside. Of two events in a window, the bigger one is the motion."""
    cues = pd.DataFrame([
        {"t_s": 10.0, "shown_t_s": 8.6, "kind": "rounds", "motion": "tilt_left", "window_s": 4.0, "trial": 1,
         "step": 0, "round": 1},
        {"t_s": 20.0, "kind": "rounds", "motion": "nod_down", "window_s": 4.0, "trial": 2, "step": 0, "round": 1},
    ])
    early = ev(9.2)                                   # 0.8 s before GO, after the announcement
    twitch, real = ev(20.2), ev(21.0)
    twitch.rot, real.rot = np.full((15, 3), 0.1), np.full((60, 3), 2.0)
    labels, _ = label_events([early, twitch, real], cues)
    assert list(labels) == ["tilt_left", "extra", "nod_down"]
    labels_old, _ = label_events([ev(9.2)], cues.drop(columns="shown_t_s"))
    assert labels_old[0] != "tilt_left"


# ----------------------------------------------------------------- features
def test_feature_names_match_values():
    rng = np.random.default_rng(0)
    acc, rot = rng.normal(size=(60, 3)), rng.normal(size=(60, 3))
    for sets in [("axis",), ("axis", "signed", "timing", "magnitude")]:
        assert len(event_features(acc, rot, FS, sets)) == len(feature_names(sets))


# ---------------------------------------------------------------- earbud switch and quiet scale (Mac test 2026-11-07)
def switch_frame(with_location, gap_s=1.07, yaw_after=0.0):
    """60 s at 50 Hz, right bud, then a gap, then the left bud tilted 30 degrees with a fresh yaw reference."""
    t = np.r_[np.arange(0, 25, 0.02), np.arange(25 + gap_s, 60, 0.02)]
    n1 = int((t < 25).sum())
    g = np.tile([0.0, 0.0, -9.81], (len(t), 1))
    a = np.radians(30)
    g[n1:] = [9.81 * np.sin(a), 0.0, -9.81 * np.cos(a)]
    df = pd.DataFrame({"gravX": g[:, 0], "gravY": g[:, 1], "gravZ": g[:, 2],
                       "yaw": np.r_[np.full(n1, -0.8), np.full(len(t) - n1, yaw_after)]})
    if with_location:
        df["sensor_location"] = ["right"] * n1 + ["left"] * (len(t) - n1)
    return df, t


@pytest.mark.parametrize("with_location", [True, False])
def test_earbud_switch_found_with_and_without_location_column(with_location):
    from gesturekit.io import find_earbud_switches
    df, t = switch_frame(with_location)
    s = find_earbud_switches(df, t)
    assert len(s) == 1 and abs(s[0]["t_s"] - 26.07) < 0.05


def test_ordinary_dropout_is_not_a_switch():
    from gesturekit.io import find_earbud_switches
    df, t = switch_frame(False, gap_s=0.6, yaw_after=-0.7)  # gap during a motion, yaw continues: not a switch
    assert find_earbud_switches(df, t) == []


def test_events_after_uncalibrated_switch_are_flagged_and_qc_fails():
    from gesturekit.pipeline import Calibration, Pipeline
    from gesturekit.qc import check_recording
    R = np.eye(3)
    rec = synth(np.vstack([swing(0), np.zeros((300, 3)), swing(0)]), R, n_quiet=150)
    switch_t = rec.t[150 + 40 + 150]
    rec.meta["earbud_switches"] = [{"t_s": float(switch_t), "from": "right", "to": "left", "how": "test"}]
    p = Pipeline()
    nod = [(150, 190)]
    p.add_calibration(rec, 0.0, still=(0, 100), nods=nod)
    ev = p.extract(rec)
    assert len(ev) == 2
    assert "flag_frame" not in ev[0].meta and ev[1].meta.get("flag_frame")
    qc = check_recording(rec)
    assert not qc.set_index("check").loc["earbud switch", "passed"]


def test_quiet_scale_raises_the_fixed_quiet_level():
    q = quiet_from(synth(np.zeros((10, 3)), np.eye(3)), 0, 200)
    d1 = Detector(DetectorConfig(quiet_scale=1.0), q)
    d3 = Detector(DetectorConfig(quiet_scale=3.0), q)
    assert np.isclose(d3.fixed_quiet.rot, 3 * d1.fixed_quiet.rot) and d3.fixed_quiet.score == d1.fixed_quiet.score
