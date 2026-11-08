"""All tunable parameters in one place, as plain dataclasses. Change a value here, not inside a module."""
from dataclasses import dataclass, field


@dataclass
class DetectorConfig:
    fs: float = 50.0
    smooth_s: float = 0.1          # causal moving average of the motion score
    k_on: float = 4.0              # start when score > k_on x quiet level of the score
    k_off: float = 2.0             # keep going while score > k_off x quiet level
    onset_s: float = 0.06          # score must stay above k_on this long to start
    end_s: float = 0.4             # quiet this long ends the event
    pre_s: float = 0.2             # samples kept before onset
    min_s: float = 0.3
    max_s: float = 4.0             # longer motion is cut into max_s pieces
    quiet_scale: float = 3.0       # multiply the still-pose quiet level by this. AirPods data is very smooth: the
                                   # median rotation of a still pose (~0.013 rad/s) is far below the micro-motion of
                                   # a person pausing between gestures, so at 1.0 events rarely end (Mac test
                                   # 2026-11-07: 46 events, many 4 s long; at 3.0 one 1.2-2.5 s event per motion).
                                   # Recheck on the next person before calling it final.
    adapt_window_s: float = 30.0   # without calibration: quiet level = running low percentile over this window
    adapt_percentile: float = 20.0
    split_returns: bool = False    # split an event where the head is back at its start pose and nearly still.
                                   # Off until pilot data (single motions) can judge it: on the old double gestures
                                   # it correctly cuts every double in two, so it cannot be evaluated there.
    return_frac: float = 0.2       # "back at start": orientation change below this share of the event's maximum
    pause_frac: float = 0.2        # "nearly still": rotation speed below this share of the event's peak speed


@dataclass
class FrameConfig:
    gravity_pre_s: float = 0.5     # gravity direction from the quiet just before an event
    first_swing_frac: float = 0.3  # nod sign: first swing above this share of the peak


@dataclass
class FeatureConfig:
    sets: tuple = ("axis", "signed", "timing")   # see features.FEATURE_SETS


@dataclass
class ClassifierConfig:
    name: str = "logreg"           # see classify.CLASSIFIERS
    params: dict = field(default_factory=dict)


@dataclass
class GateConfig:
    min_confidence: float = 0.5    # top class probability
    min_margin: float = 0.1        # top minus second probability


@dataclass
class DecoderConfig:
    pair_timeout_s: float = 1.5    # second motion must START within this many seconds after the first ENDS
    allow_same_twice: bool = False


@dataclass
class LabelConfig:
    window_s: float = 4.0          # event must start within [cue, cue + window_s] to take the cue's label
    early_s: float = 0.0           # motion windows open this long BEFORE the GO cue. App v2.0 speaks the motion
                                   # name + a ready beep before GO, and people start ~0.5-1 s early (P01, 2026-11-07):
                                   # use 1.5 for those sessions (process_session.py does this automatically).
    shown_margin_s: float = 0.3    # app v2.1 logs when a cue is announced: windows open this long before that
    pick: str = "largest"          # which event in a motion window is the motion: "largest" (most rotation; small
                                   # twitches before/after are 'extra') or "first" (the old rule). P01: with "first",
                                   # a 0.3 s twitch before the real tilt took the label.
    ignore_margin_s: float = 0.5   # events starting this close outside a motion window are ignored
    max_event_s: float = 4.0       # longer matched events are flagged


@dataclass
class PipelineConfig:
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    frame: FrameConfig = field(default_factory=FrameConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    classifier: ClassifierConfig = field(default_factory=ClassifierConfig)
    gate: GateConfig = field(default_factory=GateConfig)
    decoder: DecoderConfig = field(default_factory=DecoderConfig)
    label: LabelConfig = field(default_factory=LabelConfig)
