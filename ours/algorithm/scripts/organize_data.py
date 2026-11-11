"""Copy every gesture CSV we have into ours/data/all_by_format/<format>/ (originals untouched, exact duplicates
skipped) and write INVENTORY.md there.  Run from the repo root: python ours/algorithm/scripts/organize_data.py
"""
import hashlib
import shutil
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "ours" / "data" / "all_by_format"
TM = REPO / "prior_work" / "teammates_repo" / "CS724_Group6_IITK_26-27_Sem_I-main"
P01 = REPO / "ours/data/internal GG 01/P01_ghanshyam_s1_airpodspro2_20261107_024251/P01_ghanshyam_s1_airpodspro2_20261107_024251"

# (source, folder, new name, who, what)
FILES = [
    (REPO / "prior_work/gesture_lab/data/raw/subject1.csv", "A_takes_with_ids", "old4_S1.csv", "S1 (previous team)", "8 classes, doubles + jaw, 50 Hz"),
    (REPO / "prior_work/gesture_lab/data/raw/subject2.csv", "A_takes_with_ids", "old4_S2.csv", "S2 (previous team)", "same"),
    (REPO / "prior_work/gesture_lab/data/raw/subject3.csv", "A_takes_with_ids", "old4_S3.csv", "S3 (previous team)", "same"),
    (REPO / "prior_work/gesture_lab/data/raw/subject4.csv", "A_takes_with_ids", "old4_S4.csv", "S4 (previous team)", "same"),
    (REPO / "micro_gesture_dataset_100hz.csv", "A_takes_with_ids", "micro_face_20261109.csv", "1 teammate", "7 face micro-gestures x ~30"),
    (TM / "Sankalp_gesture_dataset_100hz.csv", "B_takes_no_ids", "sankalp.csv", "Sankalp", "20 classes: head + jaw/smirk/tongue/eyebrow/swallow"),
    (TM / "Shubham_gesture_dataset_100hz.csv", "B_takes_no_ids", "shubham.csv", "Shubham", "4 head classes"),
    (TM / "gesture_dataset.csv", "C_gyro_only", "unknown_head8.csv", "unknown", "8 head classes, rotation only (no acc/gravity)"),
    (REPO / "merged_gestures_20261109.csv", "D_sensorlogger_trials", "touch_20261109.csv", "1 teammate", "5 touch gestures (chin, cheek, earlobe)"),
    (P01 / "stream_000.csv", "E_app_streams/P01_s1", "stream_000.csv", "P01 (us)", "our app session: continuous stream"),
    (P01 / "cues.csv", "E_app_streams/P01_s1", "cues.csv", "P01 (us)", "cue log"),
    (P01 / "derived/events.csv", "E_app_streams/P01_s1", "events.csv", "P01 (us)", "detected + labelled events"),
]
for f in sorted((REPO / "ours/data/internal GG 01").glob("airpods_2026*.csv")):
    FILES.append((f, "E_app_streams/early_tests", f.name, "P01 (us)", "early raw stream test"))
SKIPPED = [
    (REPO / "prior_work/data_4people", "copies of old4_S1..S4"),
    (TM / "gesture_dataset_100hz.csv", "same values as old4_S1 (re-saved copy)"),
]


def md5(p):
    return hashlib.md5(p.read_bytes()).hexdigest()


rows, seen = [], {}
for src, folder, name, who, what in FILES:
    if not src.exists():
        rows.append(f"| missing | `{src.relative_to(REPO)}` | | | |")
        continue
    h = md5(src)
    if h in seen:
        rows.append(f"| duplicate of {seen[h]} | `{src.relative_to(REPO)}` | | | |")
        continue
    dst = OUT / folder / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    seen[h] = f"{folder}/{name}"
    n = sum(1 for _ in open(src, "rb")) - 1
    rows.append(f"| `{folder}/{name}` | `{src.relative_to(REPO)}` | {who} | {what} | {n} |")

hdr = {}
for p in sorted(OUT.rglob("*.csv")):
    hdr.setdefault(p.parent.relative_to(OUT).as_posix(), pd.read_csv(p, nrows=0).columns.tolist())

L = ["# All gesture data, by format", "",
     "Copies made by `ours/algorithm/scripts/organize_data.py`; the originals are untouched. Local only (gitignored). "
     "Never open and re-save these in Excel: it turns the ns timestamps into 1.79E+18 (already happened to old4).", "",
     "| file | original | who | what | rows |", "|---|---|---|---|---|", *rows, "",
     "Not copied: " + "; ".join(f"`{p.relative_to(REPO)}` ({w})" for p, w in SKIPPED), "", "## Formats (columns)", ""]
for k, cols in hdr.items():
    L += [f"- **{k}**: `{', '.join(cols)}`"]
L += ["", "- A: one take per `session_id`. B: no take id; takes are split where the label changes or time jumps > 0.3 s. "
      "C: like B but rotation only. D: one take per `trial_id`, Sensor Logger names. E: our app (continuous stream + cue log)."]
(OUT / "INVENTORY.md").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
