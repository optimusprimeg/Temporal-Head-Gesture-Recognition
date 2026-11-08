"""One in-memory format for every data source.

A Recording is a continuous stream on a uniform time grid, in fixed channel order and SI units:
    rot  rad/s   angular velocity, earbud axes
    acc  m/s^2   user acceleration (gravity removed), earbud axes
    grav m/s^2   gravity vector, earbud axes
    quat         orientation quaternion (x, y, z, w); NaN when the source has none (EarSet)
Gaps where the source had no samples are marked in `valid` (False), never silently interpolated.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

ROT = ["rotX", "rotY", "rotZ"]
ACC = ["accX", "accY", "accZ"]
GRAV = ["gravX", "gravY", "gravZ"]
QUAT = ["quatX", "quatY", "quatZ", "quatW"]
CHANNELS = ROT + ACC + GRAV + QUAT
I_ROT, I_ACC, I_GRAV, I_QUAT = (slice(0, 3), slice(3, 6), slice(6, 9), slice(9, 13))
G = 9.80665


@dataclass
class Recording:
    t: np.ndarray                 # (T,) seconds from the start of the recording
    X: np.ndarray                 # (T, 13) in CHANNELS order
    fs: float
    valid: np.ndarray             # (T,) bool, False inside source gaps
    meta: dict = field(default_factory=dict)          # subject, device, session, source, ...
    cues: pd.DataFrame | None = None                  # cue log on the same time axis (column t_s), if any
    t0_ns: int = 0                                    # sensor clock (ns) at t = 0

    @property
    def rot(self):
        return self.X[:, I_ROT]

    @property
    def acc(self):
        return self.X[:, I_ACC]

    @property
    def grav(self):
        return self.X[:, I_GRAV]

    def __len__(self):
        return len(self.t)

    def index(self, t_s):
        """Sample index of time t_s (seconds)."""
        return int(np.clip(np.round(t_s * self.fs), 0, len(self.t) - 1))

    def slice(self, a, b):
        """Sub-recording of samples [a, b)."""
        return Recording(self.t[a:b] - self.t[a], self.X[a:b], self.fs, self.valid[a:b], dict(self.meta),
                         None, self.t0_ns + int(self.t[a] * 1e9))


def to_grid(t_s, values, fs, max_gap_s=0.1):
    """Resample irregular samples (t_s sorted, unique) to a uniform grid. Samples further than max_gap_s from
    any source sample are marked invalid (and linearly bridged so arrays stay finite)."""
    grid = np.arange(0, t_s[-1] + 0.5 / fs, 1 / fs)
    out = np.stack([np.interp(grid, t_s, values[:, j]) for j in range(values.shape[1])], axis=1)
    pos = np.searchsorted(t_s, grid).clip(1, len(t_s) - 1)
    near = np.minimum(np.abs(grid - t_s[pos - 1]), np.abs(t_s[pos] - grid))
    return grid, out, near <= max_gap_s
