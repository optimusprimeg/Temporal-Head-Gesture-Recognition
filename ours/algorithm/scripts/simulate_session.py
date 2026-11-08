"""Write a synthetic collector-v3 session (for trying the pipeline without AirPods).

    python scripts/simulate_session.py <output folder> [subject=2] [seed=0]

Uses our old AirPods takes as motion and quiet signal (subjects 2 and 4 have still data; 1 and 3 do not).
Also writes truth.csv (true motion times) next to the collector files.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gesturekit.simulate import simulate_session  # noqa: E402

COMMANDS = {("tilt_left", "nod_down"): "GO FORWARD", ("circle_cw", "nod_down"): "NEED BACKUP",
            ("tilt_right", "tilt_left"): "MOVE"}

if __name__ == "__main__":
    out = sys.argv[1]
    subject = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    truth, clock_err = simulate_session(out, commands=COMMANDS, subject=subject, seed=seed)
    print(f"wrote {out}: {len(truth)} true motions, cue clock error {clock_err * 1000:.0f} ms")
