"""From classified events to commands.

Gate: an event becomes a motion only if its top class is not 'none', its probability >= min_confidence and it beats
the second class by >= min_margin.
PairDecoder: a command = (first motion, second motion) looked up in a dictionary {(first, second): message}.
The second motion must start within pair_timeout_s after the first ends; otherwise the first is discarded.
A pair not in the dictionary (or the same motion twice, unless allowed) is not sent; the second motion then becomes
the new first, since the person may be starting a new command.
"""
from dataclasses import dataclass

import numpy as np

from .config import DecoderConfig, GateConfig

NONE = "none"


@dataclass
class Motion:
    label: str
    t_start: float
    t_end: float
    confidence: float


@dataclass
class Command:
    first: str
    second: str
    message: str
    t_start: float
    t_end: float


def gate(label, proba, classes, cfg=GateConfig()):
    """True if this classified event should count as a motion."""
    p = np.sort(proba)[::-1]
    margin = p[0] - (p[1] if len(p) > 1 else 0.0)
    return label != NONE and p[0] >= cfg.min_confidence and margin >= cfg.min_margin


class PairDecoder:
    def __init__(self, commands, cfg=DecoderConfig()):
        self.commands, self.cfg = dict(commands), cfg
        self.pending = None

    def reset(self):
        self.pending = None

    def tick(self, t_now):
        """Drop a pending first motion whose time ran out (call regularly in live use)."""
        if self.pending is not None and t_now - self.pending.t_end > self.cfg.pair_timeout_s:
            self.pending = None

    def push(self, m):
        """Feed one gated motion (in time order). Returns a Command or None."""
        self.tick(m.t_start)
        if self.pending is None:
            self.pending = m
            return None
        first, self.pending = self.pending, None
        same = first.label == m.label and not self.cfg.allow_same_twice
        msg = None if same else self.commands.get((first.label, m.label))
        if msg is None:
            self.pending = m
            return None
        return Command(first.label, m.label, msg, first.t_start, m.t_end)


def decode(motions, commands, cfg=DecoderConfig()):
    dec = PairDecoder(commands, cfg)
    return [c for m in sorted(motions, key=lambda m: m.t_start) if (c := dec.push(m)) is not None]
