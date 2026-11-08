"""Causal motion detector: finds variable-length motion events in a continuous stream.

Uses only past samples, so the same code runs live (push one sample at a time) and offline (detect()).
Motion score per sample = rotation speed / its quiet level + acceleration change / its quiet level, smoothed with
a causal moving average. Quiet levels come from the calibration still pose (`quiet_from`) or, without one, from a
running low percentile of the last `adapt_window_s` seconds.
Hysteresis: start when the score stays above k_on x quiet for onset_s, end after end_s below k_off x quiet.
An event includes pre_s before onset. Motion longer than max_s is emitted in max_s pieces. A data gap ends the
current event.
"""
from collections import deque
from dataclasses import dataclass

import numpy as np

from .config import DetectorConfig


@dataclass
class Quiet:
    rot: float      # quiet rotation speed (rad/s)
    jerk: float     # quiet acceleration change per sample (m/s^2)
    score: float    # quiet level of the combined score


def _parts(rot, acc):
    g = np.linalg.norm(rot, axis=1)
    j = np.linalg.norm(np.diff(acc, axis=0, prepend=acc[:1]), axis=1)
    return g, j


def quiet_from(rec, a, b):
    """Quiet levels from a still segment [a, b) of a recording (the calibration still pose)."""
    g, j = _parts(rec.rot[a:b], rec.acc[a:b])
    q = Quiet(float(np.median(g)) + 1e-4, float(np.median(j)) + 1e-4, 0.0)
    q.score = float(np.median(g / q.rot + j / q.jerk))
    return q


class Detector:
    def __init__(self, cfg=DetectorConfig(), quiet=None):
        if quiet is not None and cfg.quiet_scale != 1.0:  # raise rot/jerk levels, keep the score reference
            quiet = Quiet(quiet.rot * cfg.quiet_scale, quiet.jerk * cfg.quiet_scale, quiet.score)
        self.cfg, self.fixed_quiet = cfg, quiet
        n = lambda s: max(1, int(round(s * cfg.fs)))
        self.n_smooth, self.n_onset, self.n_end = n(cfg.smooth_s), n(cfg.onset_s), n(cfg.end_s)
        self.n_pre, self.n_min, self.n_max = n(cfg.pre_s), n(cfg.min_s), n(cfg.max_s)
        self.n_window = n(cfg.adapt_window_s)
        self.reset()

    def reset(self):
        self.i = -1
        self.prev_acc = None
        self.g_buf, self.j_buf = deque(maxlen=self.n_smooth), deque(maxlen=self.n_smooth)
        self.hist_g, self.hist_j = deque(maxlen=self.n_window), deque(maxlen=self.n_window)
        self.quiet = self.fixed_quiet
        self.state, self.onset, self.quiet_run, self.start, self.last_active = "wait", 0, 0, 0, 0
        self.first_valid = 0  # first sample after the latest gap: an event never reaches back across a gap

    def _update_quiet(self):
        if self.fixed_quiet is not None or len(self.hist_g) < self.cfg.fs * 2:
            return
        if self.quiet is None or self.i % int(self.cfg.fs) == 0:  # refresh once per second
            p = self.cfg.adapt_percentile
            qg = float(np.percentile(self.hist_g, p)) + 1e-4
            qj = float(np.percentile(self.hist_j, p)) + 1e-4
            self.quiet = Quiet(qg, qj, 2.0)

    def _close(self, out, end):
        if end - self.start >= self.n_min:
            out.append((self.start, end))

    def push(self, rot, acc, valid=True):
        """Feed one sample. Returns a list of finished events [(start, end)] (sample indices, end exclusive)."""
        self.i += 1
        out = []
        if not valid:
            if self.state == "rec":
                self._close(out, self.last_active + 1)
            self.state, self.onset, self.prev_acc = "wait", 0, None
            self.g_buf.clear()
            self.j_buf.clear()
            self.first_valid = self.i + 1
            return out
        jerk = 0.0 if self.prev_acc is None else float(np.linalg.norm(acc - self.prev_acc))
        self.prev_acc = acc
        g = float(np.linalg.norm(rot))
        self.g_buf.append(g)
        self.j_buf.append(jerk)
        self.hist_g.append(g)
        self.hist_j.append(jerk)
        self._update_quiet()
        if self.quiet is None:
            return out
        q = self.quiet
        s = np.mean(self.g_buf) / q.rot + np.mean(self.j_buf) / q.jerk
        if self.state == "wait":
            self.onset = self.onset + 1 if s > self.cfg.k_on * q.score else 0
            if self.onset >= self.n_onset:
                self.state, self.quiet_run = "rec", 0
                self.start = max(self.first_valid, self.i - self.n_onset - self.n_pre + 1)
                self.last_active = self.i
        else:
            if s > self.cfg.k_off * q.score:
                self.quiet_run, self.last_active = 0, self.i
            else:
                self.quiet_run += 1
            if self.quiet_run >= self.n_end:
                self._close(out, self.last_active + 1)
                self.state, self.onset = "wait", 0
            elif self.i + 1 - self.start >= self.n_max:
                self._close(out, self.i + 1)
                self.start, self.last_active = self.i + 1, self.i
        return out

    def flush(self):
        """Close an event still open at the end of the stream."""
        out = []
        if self.state == "rec":
            self._close(out, self.last_active + 1)
        self.state = "wait"
        return out


def split_returns(rot, a, b, cfg):
    """Split event [a, b) where the head is back at its starting orientation AND nearly still: the boundary between
    two motions done back to back (each single motion goes out and comes back). Uses only samples inside the event,
    so it adds no delay beyond the event's end. Returns a list of (start, end)."""
    n_min = int(round(cfg.min_s * cfg.fs))
    if b - a < 2 * n_min:
        return [(a, b)]
    w = rot[a:b]
    speed = np.convolve(np.linalg.norm(w, axis=1), np.ones(5) / 5, mode="same")
    angle = np.cumsum(w, axis=0) / cfg.fs                         # orientation change since the event start
    away = np.linalg.norm(angle, axis=1)
    ok = (speed < cfg.pause_frac * speed.max()) & (away < cfg.return_frac * away.max())
    ok[:n_min] = ok[-n_min:] = False
    if not ok.any() or away.max() < 0.05:                          # no clear out-and-back motion
        return [(a, b)]
    runs = np.split(np.where(ok)[0], np.where(np.diff(np.where(ok)[0]) > 1)[0] + 1)
    cut = a + int(min(runs, key=lambda r: speed[r].mean()).mean())  # middle of the quietest return
    return split_returns(rot, a, cut, cfg) + split_returns(rot, cut, b, cfg)


def detect(rec, cfg=None, quiet=None):
    """Run the causal detector over a whole Recording. Returns [(start, end, finished_at)] where finished_at is the
    sample index at which a live system would have known the event ended (for latency)."""
    cfg = cfg or DetectorConfig(fs=rec.fs)
    det = Detector(cfg, quiet)
    raw = []
    for i in range(len(rec)):
        for a, b in det.push(rec.rot[i], rec.acc[i], bool(rec.valid[i])):
            raw.append((a, b, i))
    for a, b in det.flush():
        raw.append((a, b, len(rec) - 1))
    if not cfg.split_returns:
        return raw
    return [(s, e, fin) for a, b, fin in raw for s, e in split_returns(rec.rot, a, b, cfg)]
