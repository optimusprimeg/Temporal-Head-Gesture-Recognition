"""Convert a Gesture Collector app session (v5.json / v5_plus.json experiment) into collector_v5's dataset CSV.

  python scripts/app_to_v5_csv.py <session.zip | folder> --subject S07 [--out dataset_S07.csv]

Same columns and meaning as collector_v5.COLUMNS, one block of rows per take:
  take window  = from the announcement (the app's 'go': text + spoken name) for window_s (3 s + speech time)
  rows         = 0.5 s before to 1.0 s after the window (in_window marks the window), sensor timestamps in ns
  label        = the motion id; idle_still/talk/chew/swallow -> label 'idle' + idle_variant (as v5);
                 the 60 s long idles -> idle + still_long/talk_long/chew_long (group idle_cont)
  quality      = 'ok', or 'bad:<reasons>' from v5's own checks (coverage, gap, earbud switched, no movement,
                 moved during still, head moved) plus the app's (skipped/disturbed, wrong motion count for head
                 gestures, mismatch). Bad takes are kept, as v5 keeps them.
  rep          = numbered over good takes per label (as v5); round_no / pos_in_round filled (v5 leaves them empty)
Extra columns at the end (v5 tools ignore them): condition, block, attempt, app_flags, app_check_vote, source.
Practice trials are left out (v5 has none); later rounds blocks (talking, walking, small...) are kept with their
condition. Appends to --out if it exists with the same header, so several sessions can share one file.
"""
import argparse
import json
import math
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

V5_COLUMNS = (["timestamp_ns", "t_rel_s", "in_window"] +
              ["yaw", "pitch", "roll", "quatX", "quatY", "quatZ", "quatW", "rotX", "rotY", "rotZ", "accX", "accY",
               "accZ", "gravX", "gravY", "gravZ"] +
              ["sensor_location", "label", "group", "idle_variant", "take_id", "rep", "subject_id", "session_id",
               "device", "window_s", "beep_phone_ns", "n_in_window", "coverage", "max_gap_s", "side_switch",
               "quality", "gyro_rms_dps", "orient_range_deg", "round_no", "pos_in_round", "collector_version"])
EXTRA = ["condition", "block", "attempt", "app_flags", "app_check_vote", "source"]
FS, PRE, POST = 50.0, 0.5, 1.0
# collector_v5 quality thresholds
MIN_COVERAGE, MAX_GAP_S, MAX_GAP_LONG_S = 0.90, 0.20, 1.00
LOW_MOTION_DPS, STILL_MAX_DPS, HEAD_STILL_MAX_DEG = 1.8, 3.0, 20.0
LOW_MOTION_EXEMPT = {"smile_2x", "molar_tap_2x", "jaw_clench_double"}
LONG = {"SIT STILL": "still_long", "TALK": "talk_long", "CHEW": "chew_long"}


def open_session(p: Path) -> Path:
    if p.is_dir():
        hits = [q.parent for q in p.rglob("session.json") if "__MACOSX" not in q.parts]
        if not hits:
            sys.exit(f"no session.json under {p}")
        return hits[0]
    dest = Path(__file__).resolve().parents[2] / "data" / "reviews" / "_unzipped" / p.stem
    with zipfile.ZipFile(p) as z:
        for m in z.namelist():
            t = (dest / m).resolve()
            if "__MACOSX" in m or m.endswith("/") or dest.resolve() not in t.parents:
                continue
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_bytes(z.read(m))
    return open_session(dest)


def unwrap_range_deg(v):
    v = v[~np.isnan(v)]
    return math.degrees(np.ptp(np.unwrap(v))) if len(v) > 1 else 0.0


def convert(folder: Path, subject: str):
    meta = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    exp = json.loads((folder / "experiment.json").read_text(encoding="utf-8"))
    groups = {m["id"]: m.get("group", "head") for m in exp["motions"]}
    cues = pd.concat([pd.read_csv(f) for f in sorted(folder.glob("cues*.csv"))], ignore_index=True)
    st = pd.concat([pd.read_csv(f) for f in sorted(folder.glob("stream_*.csv"))], ignore_index=True)
    st = st.sort_values("sensor_ns").drop_duplicates("sensor_ns").reset_index(drop=True)
    t_all = st.sensor_ns.to_numpy(np.int64)
    session = folder.name.split("_")[-2] + "-" + folder.name.split("_")[-1] if folder.name.count("_") >= 2 else folder.name
    for c in ["flags", "check_vote", "live_verdict"]:
        if c not in cues:
            cues[c] = ""
    for c in ["flags", "check_vote", "live_verdict", "note"]:
        cues[c] = cues[c].astype(object).where(cues[c].notna(), "").astype(str)

    # v3.5: trials the experimenter marked wrong ("Last one was wrong: redo") -> bad:experimenter wrong
    wrong = {(str(r.motion), int(r.sensor_ns_est)) for _, r in cues.iterrows() if r.status == "marked_wrong"}
    takes = []
    for _, r in cues.iterrows():
        if r.kind == "rounds" and r.status in ("done", "disturbed"):
            m = str(r.motion)
            if m.startswith("idle_"):
                label, variant, group = "idle", m[5:], "idle"
            else:
                label, variant, group = m, "", groups.get(m, "head")
            long_ = False
        elif r.kind == "negatives" and str(r.block).endswith("long_idle") and r.status == "done":
            key = next((v for k, v in LONG.items() if str(r.condition).upper().startswith(k)), None)
            if key is None:
                continue
            label, variant, group, long_ = "idle", key, "idle_cont", True
        else:
            continue
        takes.append((r, label, variant, group, long_))

    rows, counts, take_no, pos = [], {}, 0, {}
    for r, label, variant, group, long_ in takes:
        start = int(r.sensor_ns_est)
        end = start + int(float(r.window_s) * 1e9)
        lo, hi = start - int(PRE * 1e9), end + int(POST * 1e9)
        i, j = np.searchsorted(t_all, lo), np.searchsorted(t_all, hi, side="right")
        seg = st.iloc[i:j]
        if seg.empty:
            continue
        win = seg[(seg.sensor_ns >= start) & (seg.sensor_ns <= end)]
        coverage = len(win) / (float(r.window_s) * FS)
        ts = np.r_[start, win.sensor_ns.to_numpy(np.int64), end]
        max_gap = float(np.diff(ts).max()) / 1e9
        sides = sorted(set(win.sensor_location.astype(str)))
        rot = win[["rotX", "rotY", "rotZ"]].to_numpy(float)
        gyro = math.degrees(math.sqrt(np.mean((rot ** 2).sum(1)))) if len(rot) else 0.0
        orient = max(unwrap_range_deg(win[k].to_numpy(float)) for k in ("yaw", "pitch", "roll")) if len(win) else 0.0
        key = label if label != "idle" else f"idle:{variant}"
        problems = []
        if coverage < MIN_COVERAGE:
            problems.append(f"coverage {coverage:.0%}")
        if max_gap > (MAX_GAP_LONG_S if long_ else MAX_GAP_S):
            problems.append(f"gap {max_gap:.2f}s")
        if len(sides) > 1:
            problems.append("earbud switched")
        if label != "idle" and label not in LOW_MOTION_EXEMPT and group in ("head", "face", "combo") and gyro < LOW_MOTION_DPS:
            problems.append("no movement")
        if key == "idle:still" and gyro > STILL_MAX_DPS:
            problems.append("moved during still")
        if group in ("face", "combo") and orient > HEAD_STILL_MAX_DEG:
            problems.append("head moved")
        if r.status == "disturbed":
            problems.append("disturbed")
        if (str(r.motion), int(r.sensor_ns_est)) in wrong:
            problems.append("experimenter: wrong motion")
        flags = [f for f in str(r["flags"]).split(";") if f]
        if "mismatch" in flags:
            problems.append("app: wrong motion")
        if "count" in flags and group == "head":
            problems.append("app: motion count")
        quality = "ok" if not problems else "bad:" + ";".join(problems)
        take_no += 1
        rep = ""
        if quality == "ok":
            counts[key] = counts.get(key, 0) + 1
            rep = counts[key]
        rnd = int(r["round"]) if not long_ else ""
        pos[(r.block, rnd)] = pos.get((r.block, rnd), 0) + 1
        meta_row = {"label": label, "group": group, "idle_variant": variant,
                    "take_id": f"{subject}_{session}_{take_no:04d}", "rep": rep, "subject_id": subject,
                    "session_id": session, "device": meta.get("device", ""), "window_s": float(r.window_s),
                    "beep_phone_ns": str(start), "n_in_window": len(win), "coverage": f"{coverage:.3f}",
                    "max_gap_s": f"{max_gap:.3f}", "side_switch": int(len(sides) > 1), "quality": quality,
                    "gyro_rms_dps": f"{gyro:.2f}", "orient_range_deg": f"{orient:.1f}", "round_no": rnd,
                    "pos_in_round": pos[(r.block, rnd)] if not long_ else "",
                    "collector_version": f"app-{meta.get('appVersion', '?')}",
                    "condition": r.condition, "block": r.block, "attempt": r.get("attempt", ""),
                    "app_flags": r["flags"], "app_check_vote": r.check_vote, "source": "app"}
        for _, s in seg.iterrows():
            row = {k: s[k] for k in V5_COLUMNS[3:19]}
            row.update(meta_row)
            row["timestamp_ns"] = str(int(s.sensor_ns))
            row["t_rel_s"] = f"{(int(s.sensor_ns) - start) / 1e9:.3f}"
            row["in_window"] = int(start <= int(s.sensor_ns) <= end)
            rows.append(row)
    return pd.DataFrame(rows, columns=V5_COLUMNS + EXTRA), counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    ap.add_argument("--subject", required=True, help="subject id as in the v5 data, e.g. S07")
    ap.add_argument("--out")
    a = ap.parse_args()
    folder = open_session(Path(a.session))
    df, counts = convert(folder, a.subject)
    out = Path(a.out or f"dataset_{a.subject}_app.csv")
    if out.exists():
        old_cols = pd.read_csv(out, nrows=0).columns.tolist()
        if old_cols != V5_COLUMNS + EXTRA:
            sys.exit(f"{out} has other columns: choose another --out")
        df.to_csv(out, mode="a", header=False, index=False)
    else:
        df.to_csv(out, index=False)
    print(f"{df.take_id.nunique()} takes, {len(df)} rows -> {out}")
    print("good takes per label:", dict(sorted(counts.items())))
    print("bad takes:", df.drop_duplicates("take_id").quality.str.startswith("bad").sum())
