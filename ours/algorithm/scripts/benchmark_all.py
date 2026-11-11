"""Every gesture recording we have, every method, one report -> results/benchmark_all.md

Data: ours/data/all_by_format (made by organize_data.py). One row per take (one gesture repetition).
  A  old4_S1..S4, micro_face      take = session_id
  B  sankalp, shubham             no take id: split where the label changes or time jumps > 0.3 s
  D  touch                        take = trial_id
  E  P01 (our app)                take = labelled event from derived events.csv, cut from the stream
  C  unknown_head8 (rotation only) is used only for the data check (no acceleration/gravity).
Labels are made consistent: tilt_2x_front -> nod_2x_front, rotate_L/R_chin_down -> rotate_left/right_chin_down,
jaw_double_clench -> jaw_clench_double.

Methods (random forest, 300 trees, for every feature set):
  ours 25         our head-frame shape features (ours/handoff/our_features.py)
  sir/receiver 96 12 channels x 8 stats, the live receiver's features
  theirs 214      train_model.py's extract_maximum_feature_matrix on its 120-sample crop (needs quaternions;
                  sankalp/shubham have none, so their quaternion features are 0 there)
  ours + 214      both together
  POSTURE ONLY    mean gravity direction + yaw/pitch/roll means. The confound check: in block-recorded data
                  this alone can 'recognise' the block. A score counts only where it clearly beats this.
  our rules       no training; head motions only (expected rule name per class below)

Splits:
  random 5-fold   what is usually reported (same person, takes from the same minute in train and test)
  by time         same person, first 60 % of each class's takes train, last 40 % test
  new person      leave one person out, on the head classes several people share
"""
import importlib.util
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.fft import fft
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
DATA = REPO / "ours" / "data" / "all_by_format"
sys.path.insert(0, str(REPO / "ours" / "handoff"))
import our_features as of  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "tm", REPO / "prior_work/teammates_repo/CS724_Group6_IITK_26-27_Sem_I-main/train_model.py")
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)

FS = 50
CH = ["yaw", "pitch", "roll", "quatX", "quatY", "quatZ", "quatW", "rotX", "rotY", "rotZ", "accX", "accY", "accZ",
      "gravX", "gravY", "gravZ"]
RCV = ["yaw", "pitch", "roll", "rotX", "rotY", "rotZ", "accX", "accY", "accZ", "gravX", "gravY", "gravZ"]
RENAME = {"quaternionX": "quatX", "quaternionY": "quatY", "quaternionZ": "quatZ", "quaternionW": "quatW",
          "rotationRateX": "rotX", "rotationRateY": "rotY", "rotationRateZ": "rotZ", "accelerationX": "accX",
          "accelerationY": "accY", "accelerationZ": "accZ", "gravityX": "gravX", "gravityY": "gravY",
          "gravityZ": "gravZ"}
LABELS = {"tilt_2x_front": "nod_2x_front", "rotate_L_chin_down": "rotate_left_chin_down",
          "rotate_R_chin_down": "rotate_right_chin_down", "jaw_double_clench": "jaw_clench_double"}
RULE_EXPECT = {"tilt_2x_left": "tilt_left", "tilt_2x_right": "tilt_right", "nod_2x_front": "nod_down",
               "circle_cw": "circle_cw", "circle_ccw": "circle_ccw", "rotate_left_chin_down": "turn_left",
               "rotate_right_chin_down": "turn_right", "nod_down": "nod_down", "look_up": "look_up",
               "tilt_left": "tilt_left", "tilt_right": "tilt_right", "turn_left": "turn_left",
               "turn_right": "turn_right"}
GROUP = lambda l: ("idle" if l in ("idle", "none", "still") else  # noqa: E731
                   "head" if l in RULE_EXPECT else "touch" if l.startswith(("tap", "pull")) else "face")


# ------------------------------------------------------------------ load takes
def takes_from(df, key, dataset, person):
    df = df.rename(columns=RENAME)
    for c in CH:
        if c not in df:
            df[c] = 0.0
    t = "timestamp" if "timestamp" in df else "time"
    for i, (k, g) in enumerate(df.groupby(key, sort=False)):
        g = g.sort_values(t) if df[t].dtype != float or g[t].nunique() > 1 else g
        yield {"dataset": dataset, "person": person, "take": f"{dataset}:{k}", "label": LABELS.get(g.label.iloc[0], g.label.iloc[0]),
               "order": i, "x": g[CH].astype(float).reset_index(drop=True),
               "bud": g.sensor_location.iloc[0] if "sensor_location" in g else "?"}


def split_runs(df):
    t = df.timestamp.astype("int64").to_numpy()
    lab = df.label.to_numpy()
    br = np.r_[False, (np.diff(t) > 0.3e9) | (np.diff(t) < 0) | (lab[1:] != lab[:-1])]
    return np.cumsum(br)


def load_all():
    T, checks = [], []
    for s in (1, 2, 3, 4):
        d = pd.read_csv(DATA / f"A_takes_with_ids/old4_S{s}.csv")
        T += list(takes_from(d, "session_id", f"old4_S{s}", f"S{s}"))
    d = pd.read_csv(DATA / "A_takes_with_ids/micro_face_20261109.csv")
    T += list(takes_from(d, "session_id", "micro_face", "micro_P"))
    for name in ("sankalp", "shubham"):
        d = pd.read_csv(DATA / f"B_takes_no_ids/{name}.csv")
        d["take_no"] = split_runs(d)
        T += list(takes_from(d, "take_no", name, name))
    d = pd.read_csv(DATA / "D_sensorlogger_trials/touch_20261109.csv")
    T += list(takes_from(d, "trial_id", "touch", "touch_P"))
    # P01: labelled events of our app session
    st = pd.read_csv(DATA / "E_app_streams/P01_s1/stream_000.csv")
    ev = pd.read_csv(DATA / "E_app_streams/P01_s1/events.csv")
    ts = (st.sensor_ns - st.sensor_ns.iloc[0]) / 1e9
    for i, e in ev.iterrows():
        if e.label in ("calibration",) or pd.isna(e.label):
            continue
        g = st[(ts >= e.t_start) & (ts <= e.t_end)]
        if len(g) >= 10:
            T.append({"dataset": "P01_app", "person": "P01", "take": f"P01:{i}", "label": e.label, "order": i,
                      "x": g[CH].astype(float).reset_index(drop=True), "bud": g.sensor_location.iloc[0]})
    return [t for t in T if len(t["x"]) >= 10]


# ------------------------------------------------------------------ features
def receiver_96(x):
    x = x[RCV].to_numpy()
    if len(x) > 100:
        s = (len(x) - 100) // 2
        x = x[s:s + 100]
    f = []
    for j in range(x.shape[1]):
        v = x[:, j]
        jerk = np.diff(v)
        spec_ = np.abs(fft(v))[: len(v) // 2]
        f += [v.mean(), v.std(), v.min(), v.max(), np.ptp(v), jerk.std(), np.abs(jerk).max(), (spec_ ** 2).sum() / len(v)]
    return f


def theirs_214(x):
    w = tm.crop_or_pad_session(x, target_frames=120).reset_index(drop=True)
    return list(tm.extract_maximum_feature_matrix(w).values())


OUR = of.FEATURES_CORE + of.FEATURES_DIRECTION + of.FEATURES_TIMING + of.FEATURES_MAGNITUDE


def featurize(T):
    for t in T:
        x = t["x"]
        f = of.event_features(x, FS)
        t["ours"] = [f[k] for k in OUR]
        t["rule"] = of.rule_classify(f)
        t["rcv"] = receiver_96(x)
        t["214"] = theirs_214(x)
        gm = x[of.GRAV].to_numpy().mean(0)
        t["posture"] = list(gm / (np.linalg.norm(gm) + 1e-9)) + list(x[["yaw", "pitch", "roll"]].mean())
        t["n"] = len(x)
        t["peak_rot"] = float(np.linalg.norm(x[of.ROT].to_numpy(), axis=1).max())
    return T


SETS = {"ours 25": lambda D: np.array(D.ours.tolist()),
        "sir/receiver 96": lambda D: np.array(D.rcv.tolist()),
        "theirs 214": lambda D: np.array(D["214"].tolist()),
        "ours + 214": lambda D: np.hstack([np.array(D.ours.tolist()), np.array(D["214"].tolist())]),
        "POSTURE ONLY": lambda D: np.array(D.posture.tolist())}
rf = lambda: RandomForestClassifier(300, random_state=0, n_jobs=-1)  # noqa: E731


def clean(X):
    return np.nan_to_num(np.asarray(X, float), nan=0.0, posinf=0.0, neginf=0.0)


def within(D):
    y = D.label.to_numpy()
    frac = (D.groupby("label").cumcount() / D.groupby("label").label.transform("size")).to_numpy()
    tr, te = frac < 0.6, frac >= 0.6
    out = {}
    for name, fx in SETS.items():
        X = clean(fx(D))
        k = min(5, int(D.label.value_counts().min()))
        pr = np.empty(len(y), object)
        for a, b in StratifiedKFold(k, shuffle=True, random_state=0).split(X, y):
            pr[b] = rf().fit(X[a], y[a]).predict(X[b])
        pt = rf().fit(X[tr], y[tr]).predict(X[te])
        out[name] = (float(np.mean(pr == y)), float(np.mean(pt == y[te])))
    return out


# ------------------------------------------------------------------ run
T = featurize(load_all())
D = pd.DataFrame([{k: v for k, v in t.items() if k != "x"} for t in T])
D["group"] = D.label.map(GROUP)
L = ["# Benchmark: all our data, all methods", "",
     "Generated by `algorithm/scripts/benchmark_all.py` (method in its header). Accuracy 0-1; chance = 1 / classes.",
     ""]

# 1. data check
rows = []
for ds, g in D.groupby("dataset", sort=False):
    labs = g.sort_values("order").label.to_numpy()
    switches = int((labs[1:] != labs[:-1]).sum())
    rows.append({"dataset": ds, "person": g.person.iloc[0], "takes": len(g), "classes": g.label.nunique(),
                 "takes/class min-max": f"{g.label.value_counts().min()}-{g.label.value_counts().max()}",
                 "take length s (median)": round(g.n.median() / FS, 1),
                 "recording order": "BLOCKS" if switches <= 2 * g.label.nunique() else "mixed",
                 "earbud": "/".join(sorted(set(g.bud.astype(str)))),
                 "groups": ", ".join(f"{k} {v}" for k, v in g.group.value_counts().items())})
L += ["## 1. Data check", "", pd.DataFrame(rows).to_markdown(index=False), "",
      "Problems found while loading:",
      "- old4_S1..S4: timestamps were saved by Excel as 1.79E+18, so time inside a take is lost (sample order "
      "is still the file order; 50 Hz assumed).",
      "- teammates' `gesture_dataset_100hz.csv` is the same data as old4_S1, and `prior_work/data_4people` are "
      "copies of old4: counted once.",
      "- every file named *_100hz is really 50 Hz (one sample every 20 ms).",
      "- sankalp/shubham have no take id and no quaternions; takes were split by label change / time gap.",
      "- `unknown_head8.csv` has rotation only (no acceleration, gravity): left out of the models.", ""]
lc = D.groupby(["dataset", "label"]).size().unstack(0).fillna(0).astype(int)
L += ["Takes per class and dataset:", "", lc.to_markdown(), ""]

# 2. rules
H = D[D.label.isin(RULE_EXPECT)]
rr = H.assign(ok=H.rule == H.label.map(RULE_EXPECT)).groupby(["dataset", "label"]).agg(
    takes=("ok", "size"), correct=("ok", "mean"), most_common=("rule", lambda s: s.value_counts().index[0]))
rr["correct"] = rr.correct.round(2)
NR = D[~D.label.isin(RULE_EXPECT)]
nf = NR.groupby("dataset").rule.apply(lambda s: f"{(s != 'none').mean():.0%}")
L += ["## 2. Our rules (no training, no calibration nods here, so nod/tilt can mix)", "",
      "Head classes: share named correctly. Doubles count as correct when the rule names the first motion.", "",
      rr.reset_index().to_markdown(index=False), "",
      "Face / touch / idle takes that the rules would wrongly turn into a head command:", "",
      nf.to_frame("fired").to_markdown(), ""]

# 3. within each person
res = []
for ds, g in D.groupby("dataset", sort=False):
    if g.label.nunique() < 2 or g.label.value_counts().min() < 3:
        continue
    r = within(g.reset_index(drop=True))
    res.append({"dataset": ds, "classes": g.label.nunique(),
                **{f"{k}": f"{v[0]:.2f} / {v[1]:.2f}" for k, v in r.items()}})
    print(ds, "done", flush=True)
L += ["## 3. Same person: random 5-fold / split by time", "",
      "Each cell: random folds / by time. When POSTURE ONLY is also high, the score reflects the recording "
      "blocks, not the gesture.", "", pd.DataFrame(res).to_markdown(index=False), ""]

# 4. all data combined in one model (every class of every dataset), split by time inside each dataset
D2 = D.copy()
D2["ylab"] = D2.label
frac = (D2.groupby(["dataset", "label"]).cumcount() / D2.groupby(["dataset", "label"]).label.transform("size")).to_numpy()
y = D2.ylab.to_numpy()
tr, te = frac < 0.6, frac >= 0.6
comb = []
for name, fx in SETS.items():
    X = clean(fx(D2))
    pt = rf().fit(X[tr], y[tr]).predict(X[te])
    per = pd.Series(pt == y[te]).groupby(D2.group.to_numpy()[te]).mean()
    comb.append({"features": name, "all": round(float(np.mean(pt == y[te])), 2),
                 **{g: round(float(v), 2) for g, v in per.items()}})
L += [f"## 4. Everything in one model ({D2.ylab.nunique()} classes, all datasets), split by time", "",
      pd.DataFrame(comb).to_markdown(index=False), ""]

# 5. new person on shared head classes
SH = ["tilt_2x_left", "tilt_2x_right", "nod_2x_front", "circle_cw", "circle_ccw", "idle"]
P = D[D.label.isin(SH)].reset_index(drop=True)
people = [p for p, g in P.groupby("person") if g.label.nunique() >= 3]
P = P[P.person.isin(people)].reset_index(drop=True)
y = P.label.to_numpy()
loso = []
for name, fx in SETS.items():
    X = clean(fx(P))
    r = {"features": name}
    for p in people:
        te = (P.person == p).to_numpy()
        pt = rf().fit(X[~te], y[~te]).predict(X[te])
        r[p] = round(float(np.mean(pt == y[te])), 2)
    r["mean"] = round(float(np.mean([r[p] for p in people])), 2)
    loso.append(r)
rule_p = {p: round(float((P[P.person == p].query("label != 'idle'").pipe(
    lambda g: g.rule == g.label.map(RULE_EXPECT))).mean()), 2) for p in people}
loso.append({"features": "our rules (no training, head only)", **rule_p,
             "mean": round(float(np.mean(list(rule_p.values()))), 2)})
L += ["## 5. New person (leave one person out), shared head classes", "",
      f"Classes: {', '.join(SH)} (whichever each person has). People: {', '.join(people)}.", "",
      pd.DataFrame(loso).to_markdown(index=False), ""]

out = ROOT / "results" / "benchmark_all.md"
out.write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
