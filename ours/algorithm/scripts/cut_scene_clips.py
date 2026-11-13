"""Cut one short video clip per gesture trial out of a Gesture Collector scene video (app v3.7+).

The app (when "Record scene video" is on, with the participant's consent) writes
    <data folder>/video/<session folder>/scene_NNN.mp4      the webcam video, one per segment
    <session folder>/scene_NNN_frames.csv                   frame, video_s, sensor_ns  (sensor clock)
and cues.csv has every cue on the same sensor clock (sensor_ns_est = when the name was shown, window_s = the window).
This script maps each kept trial to its segment's video time and cuts it with ffmpeg:
    <out>/<motion>/<session>_r<round>_t<trial>.mp4

Kept trials: rounds + practice rows with status "done"; for a retake / redo only the LAST try of the trial, and
nothing the experimenter marked wrong (same rule as the app's good-rep count).

Uses: real demo clips for later pilots (only from people who agreed), and checking labels by eye.
Videos show faces: never commit them (*.mp4 / *.mov are gitignored) and share only with consent.

usage (from ours/algorithm):
    python scripts/cut_scene_clips.py <session folder> [--video <dir>] [--out clips] [--only nod_down,blink_2x]
                                      [--pre 0.3] [--post 0.5] [--label] [--dry-run]
Needs ffmpeg on PATH (not for --dry-run).
"""

import argparse
import bisect
import csv
import shutil
import subprocess
import sys
from pathlib import Path


# a font for --label (ffmpeg without fontconfig finds none by itself)
FONTS = ["/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf", "C:/Windows/Fonts/arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def kept_trials(cues):
    """Each (kind, block, round, motion) trial whose LAST row is "done" (same rule as the app's good reps)."""
    final = {}
    for r in cues:
        if r.get("kind") not in ("rounds", "practice") or r.get("motion", "") in ("", "idle"):
            continue
        if r.get("status") not in ("done", "marked_wrong", "skipped", "disturbed", "cant_do"):
            continue
        key = (r["kind"], r["block"], r["round"], r["motion"])
        if r["kind"] == "practice":
            key = key + (r["trial"],)          # practice has no rounds: every row is its own trial
        final[key] = r
    return [r for r in final.values() if r["status"] == "done"]


def load_segments(session, video_dir):
    segs = []
    for fcsv in sorted(session.glob("scene_*_frames.csv")):
        n = fcsv.name.split("_")[1]
        mp4 = video_dir / f"scene_{n}.mp4"
        rows = read_csv(fcsv)
        if not rows:
            continue
        ns = [int(r["sensor_ns"]) for r in rows]
        vs = [float(r["video_s"]) for r in rows]
        segs.append({"n": n, "mp4": mp4, "ns": ns, "vs": vs})
    return segs


def to_video_s(seg, t_ns):
    """Video time of a sensor time inside this segment (linear between the two nearest frames)."""
    ns, vs = seg["ns"], seg["vs"]
    i = bisect.bisect_left(ns, t_ns)
    if i <= 0:
        return vs[0]
    if i >= len(ns):
        return vs[-1]
    a, b = ns[i - 1], ns[i]
    return vs[i - 1] + (vs[i] - vs[i - 1]) * (t_ns - a) / max(1, b - a)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", type=Path)
    ap.add_argument("--video", type=Path, help="default: <data folder>/video/<session folder name>")
    ap.add_argument("--out", type=Path, default=Path("clips"))
    ap.add_argument("--only", default="", help="comma-separated motion ids")
    ap.add_argument("--pre", type=float, default=0.3, help="seconds before the cue")
    ap.add_argument("--post", type=float, default=0.5, help="seconds after the window ends")
    ap.add_argument("--label", action="store_true", help="burn the motion name into the clip (ffmpeg drawtext)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    session = a.session.resolve()
    video_dir = (a.video or session.parent / "video" / session.name).resolve()
    cues = read_csv(session / "cues.csv")
    segs = load_segments(session, video_dir)
    if not segs:
        sys.exit(f"no scene_*_frames.csv in {session} (scene video was off for this session?)")
    only = {m for m in a.only.split(",") if m}
    if not a.dry_run and shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH (use --dry-run to only list the clips)")

    made = skipped = 0
    for r in kept_trials(cues):
        if only and r["motion"] not in only:
            continue
        t0 = int(r.get("shown_sensor_ns") or r["sensor_ns_est"]) - int(a.pre * 1e9)
        t1 = int(r["sensor_ns_est"]) + int((float(r["window_s"]) + a.post) * 1e9)
        # the segment holding the cue itself; padding outside the video is clamped (first/last trial of a segment)
        cue = int(r["sensor_ns_est"])
        seg = next((s for s in segs if s["ns"][0] <= cue <= s["ns"][-1]), None)
        if seg is None or not seg["mp4"].exists():
            skipped += 1
            continue
        t0, t1 = max(t0, seg["ns"][0]), min(t1, seg["ns"][-1])
        v0, v1 = to_video_s(seg, t0), to_video_s(seg, t1)
        out = a.out / r["motion"] / f"{session.name}_r{r['round']}_t{r['trial']}.mp4"
        print(f"{r['motion']:<22} round {r['round']:>3}  scene_{seg['n']}  {v0:8.2f}-{v1:8.2f} s  -> {out}")
        made += 1
        if a.dry_run:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{v0:.3f}", "-i", str(seg["mp4"]),
               "-t", f"{v1 - v0:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
        if a.label:
            text = r["motion"].replace("_", " ")
            font = next((f for f in FONTS if Path(f).exists()), None)
            ff = f"fontfile='{font.replace(chr(92), '/').replace(':', chr(92) + ':')}':" if font else ""
            cmd += ["-vf", f"drawtext={ff}text='{text}':x=12:y=12:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.5"]
        subprocess.run(cmd + [str(out)], check=True)
    print(f"{made} clip(s){' listed' if a.dry_run else ' written'}, {skipped} trial(s) outside the video")


if __name__ == "__main__":
    main()
