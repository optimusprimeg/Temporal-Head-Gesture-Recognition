"""Wire the stages: calibrate -> detect -> head frame -> features -> classify -> gate -> pair decoder.

    p = Pipeline(PipelineConfig(), commands)
    p.calibrate_from_cues(rec)            # or p.add_calibration(rec, t_from, still=(a, b), nods=[(a, b), ...])
    events = p.extract(rec)               # detected events with head-frame signals and features
    p.fit(train_events, train_labels)
    p.classify(events); commands = p.decode(events)
Every stage reads its parameters from PipelineConfig and can be swapped (registries in features / classify).
"""
from dataclasses import dataclass, field

import numpy as np

from .classify import make_classifier
from .config import PipelineConfig
from .decode import Motion, decode, gate
from .detect import detect, quiet_from
from .features import event_features, feature_names
from .frames import calibrate, to_head


@dataclass
class Event:
    start: int
    end: int
    finished_at: int            # sample at which a live detector would have reported it
    t_start: float
    t_end: float
    acc: np.ndarray             # head frame
    rot: np.ndarray
    features: np.ndarray
    meta: dict = field(default_factory=dict)   # subject, device, source, label (ground truth), ...
    pred: str | None = None
    proba: np.ndarray | None = None


@dataclass
class Calibration:
    t_from: float               # applies to events starting at or after this time
    quiet: object
    frame: object


def active_part(rec, a, b, frac=0.25, pad=5):
    """Trim [a, b) to where rotation is above frac of its peak (one calibration nod inside a cue window)."""
    g = np.linalg.norm(rec.rot[a:b], axis=1)
    if g.max() <= 0:
        return a, b
    idx = np.where(g > frac * g.max())[0]
    return max(a, a + idx[0] - pad), min(b, a + idx[-1] + pad + 1)


class Pipeline:
    def __init__(self, cfg=None, commands=None):
        self.cfg = cfg or PipelineConfig()
        self.commands = commands or {}
        self.calibrations = []
        self.clf = None

    # ---------------- calibration
    def add_calibration(self, rec, t_from=0.0, still=None, nods=()):
        quiet = quiet_from(rec, *still) if still else None
        frame = calibrate(rec, list(nods), self.cfg.frame) if nods else None
        self.calibrations.append(Calibration(t_from, quiet, frame))
        self.calibrations.sort(key=lambda c: c.t_from)

    def calibrate_from_cues(self, rec, nod_window_s=2.0):
        """One calibration per calibration block in the cue log (start of session, after every re-wear)."""
        c = rec.cues
        cal = c[c.kind == "calibration"].sort_values("t_s")
        blocks = (cal.motion == "still").cumsum()
        for _, blk in cal.groupby(blocks):
            still = blk[blk.motion == "still"]
            if still.empty:
                continue
            t = float(still.t_s.iloc[0])
            s = (rec.index(t + 0.5), rec.index(t + 3.5))
            nods = [active_part(rec, rec.index(x), rec.index(x + nod_window_s))
                    for x in blk[blk.motion == "calib_nod"].t_s]
            self.add_calibration(rec, t, still=s, nods=nods)

    def calibration_at(self, t):
        before = [c for c in self.calibrations if c.t_from <= t]
        return before[-1] if before else (self.calibrations[0] if self.calibrations else None)

    # ---------------- events
    def extract(self, rec, meta=None):
        cal0 = self.calibrations[0] if self.calibrations else None
        cfg = self.cfg.detector
        if cfg.fs != rec.fs:
            cfg = type(cfg)(**{**cfg.__dict__, "fs": rec.fs})
        switches = [s["t_s"] for s in rec.meta.get("earbud_switches", [])]
        out = []
        for a, b, fin in detect(rec, cfg, cal0.quiet if cal0 else None):
            t = float(rec.t[a])
            cal = self.calibration_at(t)
            frame = cal.frame if cal else None
            extra = {}
            # After an earbud switch the old head frame is wrong (other bud, other angle, new reference) until a new
            # calibration: fall back to the gravity-only frame and flag the event.
            last_switch = max((s for s in switches if s <= t), default=None)
            if frame is not None and last_switch is not None and cal.t_from < last_switch:
                frame, extra = None, {"flag_frame": "earbud switched, not recalibrated"}
            acc, rot = to_head(rec, a, b, frame, self.cfg.frame)
            f = event_features(acc, rot, rec.fs, self.cfg.features.sets)
            out.append(Event(a, b, fin, t, float(rec.t[b - 1]), acc, rot, f,
                             {**rec.meta, **(meta or {}), **extra}))
        return out

    @property
    def feature_names(self):
        return feature_names(self.cfg.features.sets)

    # ---------------- classify and decode
    def fit(self, events, labels):
        self.clf = make_classifier(self.cfg.classifier).fit(events, labels)
        return self

    def classify(self, events):
        if not events:
            return events
        P = self.clf.predict_proba(events)
        for e, p in zip(events, P):
            e.proba, e.pred = p, self.clf.classes_[int(np.argmax(p))]
        return events

    def motions(self, events):
        return [Motion(e.pred, e.t_start, e.t_end, float(e.proba.max())) for e in events
                if gate(e.pred, e.proba, self.clf.classes_, self.cfg.gate)]

    def decode(self, events):
        return decode(self.motions(events), self.commands, self.cfg.decoder)
