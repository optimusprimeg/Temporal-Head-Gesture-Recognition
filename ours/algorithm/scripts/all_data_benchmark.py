"""Every recording in the repo, every split, three approaches: RULES vs OURS vs THEIRS -> results/all_data_benchmark.md

  python scripts/all_data_benchmark.py          (from ours/algorithm)

DATA (one row = one gesture clip)
  teammates' collector files   old4 S1-S4, Sankalp, Shubham, micro-face (ours/data/all_by_format, takes)
  Sensor Logger file export    touch clips
  our app sessions (P01)       2026-11-07 AirPods Pro 2 (app 2.0) and 2026-11-13 AirPods 5 (app 3.3): one clip per
                               practice / rounds cue, from the announcement to the end of the window
  our Mac test (P01)           2026-11-07, labelled segments; each detected event in a segment is a clip (nods unusable)
  EarSet (eSense earbud, 30 people)  only its precomputed feature table: our features exist, theirs cannot be computed
                               (no orientation / gravity channels), so it gets its own block (rules vs ours)
  not used: unknown_head8.csv (rotation only: no gravity, no acceleration)
FIX: the teammates' collector files store gravity pointing UP (gravZ ~ +0.95 when upright); the app and Sensor
  Logger's own export store it pointing DOWN (~ -0.95). Their gravity is negated on load. Checked: with the fix,
  'rotate left' turns left in 15/15 + 15/15 clips (0/30 without).
TASKS
  HEAD    which head motion: nod_down, look_up, tilt_left, tilt_right, turn_left, turn_right, circle_cw, circle_ccw,
          idle. Doubles count as their motion (tilt_2x_left -> tilt_left, nod_2x_front -> nod_down). Shared by everyone.
  NATIVE  each dataset's own full label set (face, touch, combos ...), within that dataset only.
APPROACHES
  RULES   ours, no training: largest axis share >= 0.6 -> nod/tilt/turn, else loop >= 0.15 -> circle, sign of the
          first swing; anything else idle. Gravity frame only (no person has calibration nods in every dataset).
  OURS    our 25 head-frame features; logistic regression (LR) and random forest (RF, 300 trees)
  THEIRS  train_model.py's 214 features + its RF (200 trees, depth 16); and the receiver's 96 features + RF
  BOTH    ours 25 + their 214, RF
SPLITS
  random  same person, stratified 5-fold (what is usually reported; same-minute takes in train and test)
  time    same person, first 60 % of each class trains, last 40 % tests
  LOSO    leave one person out (P01's sessions count as one person); only classes the training people have
  tool    collector people -> P01 app sessions, and back
  device  P01 AirPods Pro 2 session <-> AirPods 5 session
  EarSet  leave one person out on 30 people (rules vs ours only)
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
src = (HERE / "benchmark_all.py").read_text(encoding="utf-8").split(
    "# ------------------------------------------------------------------ run")[0]
ns = {"__file__": str(HERE / "benchmark_all.py"), "__name__": "bench"}
exec(compile(src, "benchmark_all.py", "exec"), ns)
of, receiver_96, theirs_214, clean, OUR, CH, ROOT, DATA = (ns[k] for k in (
    "of", "receiver_96", "theirs_214", "clean", "OUR", "CH", "ROOT", "DATA"))
sys.path.insert(0, str(ROOT))
from gesturekit.config import DetectorConfig  # noqa: E402
from gesturekit.detect import Detector, Quiet  # noqa: E402

FS = 50
HEAD = ["nod_down", "look_up", "tilt_left", "tilt_right", "turn_left", "turn_right", "circle_cw", "circle_ccw", "idle"]
TO_HEAD = {"tilt_2x_left": "tilt_left", "tilt_2x_right": "tilt_right", "nod_2x_front": "nod_down", "idle": "idle",
           **{m: m for m in HEAD}}
COLLECTOR = {"old4_S1", "old4_S2", "old4_S3", "old4_S4", "sankalp", "shubham", "micro_face"}
APP1 = DATA / "E_app_streams" / "P01_s1"
APP2 = ROOT.parents[0] / "data" / "reviews" / "_unzipped" / "P01_gg_s1_airpods5_20261113_020602" / "P01_gg_s1_airpods5_20261113_020602"
MACTEST = DATA / "E_app_streams" / "early_tests" / "airpods_20261107_004637"


# ------------------------------------------------------------------ load
def clip_row(x, dataset, person, device, tool, label, order):
    return {"x": x.reset_index(drop=True), "dataset": dataset, "person": person, "device": device, "tool": tool,
            "label": label, "order": order}


def load():
    rows = []
    for t in ns["load_all"]():
        if t["dataset"] == "P01_app":
            continue
        x = t["x"].copy()
        if t["dataset"] in COLLECTOR:
            x[of.GRAV] = -x[of.GRAV]                               # gravity sign fix (see header)
        tool = "teammates' collector" if t["dataset"] in COLLECTOR else "Sensor Logger export"
        rows.append(clip_row(x, t["dataset"], t["person"], "AirPods Pro 2", tool, t["label"], t["order"]))
    for folder, name, dev, early in ((APP1, "P01 app 11-07", "AirPods Pro 2", 1.5), (APP2, "P01 app 11-13", "AirPods 5", 0.3)):
        if not (folder / "stream_000.csv").exists():
            continue
        st = pd.read_csv(folder / "stream_000.csv").sort_values("sensor_ns").reset_index(drop=True)
        tt = st.sensor_ns.to_numpy(np.int64)
        cues = pd.read_csv(folder / "cues.csv")
        cues = cues[cues.kind.isin(["practice", "rounds"]) & (cues.status == "done")]
        for k, (_, c) in enumerate(cues.iterrows()):
            a = int(c.sensor_ns_est - early * 1e9)
            b = int(c.sensor_ns_est + c.window_s * 1e9)
            i, j = np.searchsorted(tt, a), np.searchsorted(tt, b)
            if j - i >= 20:
                rows.append(clip_row(st.iloc[i:j][CH].astype(float), name, "P01", dev, "our app", c.motion, k))
    if Path(str(MACTEST) + ".csv").exists():
        st = pd.read_csv(str(MACTEST) + ".csv").sort_values("sensor_ns").reset_index(drop=True)
        lab = pd.read_csv(str(MACTEST) + ".labels.csv")
        tt = (st.sensor_ns - st.sensor_ns.iloc[0]).to_numpy() / 1e9
        rot, acc = st[of.ROT].to_numpy(float), st[of.ACC].to_numpy(float)
        sp = np.linalg.norm(rot, axis=1)
        jk = np.r_[0, np.linalg.norm(np.diff(acc, axis=0), axis=1)]
        k = 25
        i0 = int(np.argmin(np.convolve(sp, np.ones(k), "valid")))
        qg, qj = float(np.median(sp[i0:i0 + k])) + 1e-4, float(np.median(jk[i0:i0 + k])) + 1e-4
        det = Detector(DetectorConfig(fs=FS), Quiet(qg, qj, float(np.median(sp[i0:i0 + k] / qg + jk[i0:i0 + k] / qj))))
        evs = []
        for i in range(len(st)):
            evs += det.push(rot[i], acc[i])
        evs += det.flush()
        n = 0
        for s, e in evs:
            seg = lab[(lab.t_from_s <= tt[s]) & (tt[s] < lab.t_to_s)]
            if len(seg) and seg.label.iloc[0] != "nod_down" and e - s >= 15:
                rows.append(clip_row(st.iloc[max(0, s - 10):e + 10][CH].astype(float), "P01 Mac test 11-07", "P01",
                                     "AirPods Pro 2", "our app", seg.label.iloc[0], n))
                n += 1
    return rows


def featurize(rows):
    for r in rows:
        x = r.pop("x")
        f = of.event_features(x, FS)
        r["ours"] = [f[k] for k in OUR]
        r["rule"] = of.rule_classify(f)
        r["rcv"] = receiver_96(x)
        r["214"] = theirs_214(x)
    return pd.DataFrame(rows)


D = featurize(load())
D["hd"] = D.label.map(TO_HEAD)
D["rule_head"] = D.rule.where(D.rule != "none", "idle")
X = {"ours": clean(D.ours.tolist()), "rcv": clean(D.rcv.tolist()), "214": clean(D["214"].tolist())}
X["both"] = np.hstack([X["ours"], X["214"]])
APPROACHES = [  # name, family, features, model
    ("RULES (no training)", "rules", None, None),
    ("OURS: 25 features, LR", "ours", "ours", lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=4000))),
    ("OURS: 25 features, RF", "ours", "ours", lambda: RandomForestClassifier(300, random_state=0, n_jobs=-1)),
    ("THEIRS: 214 features, RF (train_model.py)", "theirs", "214",
     lambda: RandomForestClassifier(200, max_depth=16, random_state=42, n_jobs=-1)),
    ("THEIRS: receiver 96, RF", "theirs", "rcv", lambda: RandomForestClassifier(300, random_state=0, n_jobs=-1)),
    ("BOTH: ours 25 + 214, RF", "both", "both", lambda: RandomForestClassifier(300, random_state=0, n_jobs=-1)),
]


def run(train_idx, test_idx, ycol):
    """accuracy of every approach on test_idx (rules ignore the training set)"""
    y = D[ycol].to_numpy()
    out = {}
    for name, fam, fx, mk in APPROACHES:
        if fam == "rules":
            pred = (D.rule_head if ycol == "hd" else D.rule).to_numpy()[test_idx]
        else:
            pred = mk().fit(X[fx][train_idx], y[train_idx]).predict(X[fx][test_idx])
        out[name] = float(np.mean(pred == y[test_idx]))
    return out


L = ["# All our data: rules vs ours vs theirs", "",
     "Generated by `algorithm/scripts/all_data_benchmark.py` (method, data list and fixes in its header). "
     "Accuracy 0-1. **Bold** = best per row.", ""]

# ---- inventory
inv = D.groupby(["dataset", "person", "device", "tool"]).agg(
    clips=("label", "size"), classes=("label", "nunique"),
    head_task_clips=("hd", lambda s: int(s.notna().sum()))).reset_index()
inv["gestures"] = D.groupby("dataset").label.agg(lambda s: ", ".join(sorted(s.unique())[:10]) + (" ..." if s.nunique() > 10 else "")).reindex(inv.dataset).to_numpy()
L += ["## Data used", "", inv.to_markdown(index=False), "",
      f"Total {len(D)} clips, {D.person.nunique()} people (+ EarSet's 30 below). Not used: `unknown_head8.csv` (rotation "
      "only). The teammates' collector files had gravity negated (sign fix, see the script header).", ""]


def bold(df):
    num = [a[0] for a in APPROACHES if a[0] in df.columns]
    out = df.astype(object)
    for i, r in df.iterrows():
        best = pd.to_numeric(r[num], errors="coerce").max()
        for c in num:
            out.loc[i, c] = f"**{r[c]:.2f}**" if r[c] == best and pd.notna(r[c]) else (f"{r[c]:.2f}" if pd.notna(r[c]) else "-")
    return out


names = [a[0] for a in APPROACHES]
H = D[D.hd.notna()]

# ---- 1. same person (HEAD task), random and by time
rows = []
for (ds, p), g in H.groupby(["dataset", "person"]):
    if g.hd.nunique() < 2 or g.hd.value_counts().min() < 3:
        continue
    idx = g.index.to_numpy()
    y = g.hd.to_numpy()
    k = min(5, int(g.hd.value_counts().min()))
    acc_r = {n: [] for n in names}
    for tr, te in StratifiedKFold(k, shuffle=True, random_state=0).split(idx, y):
        for n, v in run(idx[tr], idx[te], "hd").items():
            acc_r[n].append(v * len(te))
    frac = (g.groupby("hd").cumcount() / g.groupby("hd").hd.transform("size")).to_numpy()
    rt = run(idx[frac < 0.6], idx[frac >= 0.6], "hd")
    for split, vals in (("random 5-fold", {n: sum(v) / len(idx) for n, v in acc_r.items()}), ("by time", rt)):
        rows.append({"data": ds, "split": split, "clips": len(g), "classes": g.hd.nunique(), **vals})
R1 = pd.DataFrame(rows)
L += ["## 1. Same person, head motions (HEAD task)", "",
      "random = the usual, optimistic number; by time = trained on earlier takes, tested on later ones.", "",
      bold(R1).to_markdown(index=False), ""]

# ---- 2. LOSO (HEAD task)
rows = []
for p in H.person.unique():
    te = H[H.person == p]
    tr = H[H.person != p]
    te = te[te.hd.isin(tr.hd.unique())]
    if len(te) < 10:
        continue
    rows.append({"test person": p, "test clips": len(te), "classes": te.hd.nunique(),
                 **run(tr.index.to_numpy(), te.index.to_numpy(), "hd")})
R2 = pd.DataFrame(rows)
mean = {"test person": "MEAN", "test clips": int(R2["test clips"].sum()), "classes": "",
        **{n: R2[n].mean() for n in names}}
R2 = pd.concat([R2, pd.DataFrame([mean])], ignore_index=True)
L += ["## 2. New person (leave one person out), HEAD task", "",
      "Trained on everyone else, tested on this person's clips of the classes the others have.", "",
      bold(R2).to_markdown(index=False), ""]

# ---- 3. cross tool / cross device
rows = []
app = H[H.tool == "our app"]
col = H[H.tool == "teammates' collector"]
for a_name, tr, te in (("collector people -> P01 app", col, app), ("P01 app -> collector people", app, col)):
    te = te[te.hd.isin(tr.hd.unique())]
    rows.append({"split": a_name, "train clips": len(tr), "test clips": len(te), **run(tr.index.to_numpy(), te.index.to_numpy(), "hd")})
pro, ap5 = H[H.dataset.isin(["P01 app 11-07", "P01 Mac test 11-07"])], H[H.dataset == "P01 app 11-13"]
for a_name, tr, te in (("P01 Pro 2 -> P01 AirPods 5", pro, ap5), ("P01 AirPods 5 -> P01 Pro 2", ap5, pro)):
    te = te[te.hd.isin(tr.hd.unique())]
    if len(tr) and len(te):
        rows.append({"split": a_name, "train clips": len(tr), "test clips": len(te), **run(tr.index.to_numpy(), te.index.to_numpy(), "hd")})
R3 = pd.DataFrame(rows)
L += ["## 3. Across recording tools and AirPods models (HEAD task)", "", bold(R3).to_markdown(index=False), ""]

# ---- 4. NATIVE labels, same person by time (face, touch, combos included; rules only where all labels are head)
rows = []
for ds, g in D.groupby("dataset"):
    if g.label.value_counts().min() < 3 or g.label.nunique() < 2:
        continue
    idx = g.index.to_numpy()
    frac = (g.groupby("label").cumcount() / g.groupby("label").label.transform("size")).to_numpy()
    r = run(idx[frac < 0.6], idx[frac >= 0.6], "label")
    if not g.label.isin(HEAD).all():
        r["RULES (no training)"] = np.nan
    rows.append({"data": ds, "classes": g.label.nunique(), "clips": len(g), **r})
R4 = pd.DataFrame(rows)
L += ["## 4. Each dataset's own labels (face, touch, combos too), same person, by time", "",
      "Rules only name head motions, so they are left out where a dataset has other gestures.", "",
      bold(R4).to_markdown(index=False), ""]

# ---- 5. EarSet (30 people, eSense earbud): rules vs ours, leave one person out
E = pd.read_csv(ROOT / "results" / "earset_events.csv")
for p_ in ("xy", "xz", "yz"):
    E[f"abs_loop_{p_}"] = E[f"loop_{p_}"].abs()
E["rule"] = [{"nod": "nod", "tilt": "tilt", "turn": "shake"}.get(of.rule_kind(dict(r)), "none") for _, r in E.iterrows()]
feat = [c for c in OUR if c in E.columns]
XE, yE, gE = clean(E[feat].to_numpy()), E.label.to_numpy(), E.person.to_numpy()
pr = {"LR": np.empty(len(E), object), "RF": np.empty(len(E), object)}
for p in np.unique(gE):
    te = gE == p
    pr["LR"][te] = make_pipeline(StandardScaler(), LogisticRegression(max_iter=4000)).fit(XE[~te], yE[~te]).predict(XE[te])
    pr["RF"][te] = RandomForestClassifier(300, random_state=0, n_jobs=-1).fit(XE[~te], yE[~te]).predict(XE[te])
R5 = pd.DataFrame([{"EarSet, 30 people, leave one person out": f"{len(E)} events, classes {', '.join(sorted(set(yE)))}",
                    "RULES (no training)": float(np.mean(E.rule == yE)), "OURS: 25 features, LR": float(np.mean(pr["LR"] == yE)),
                    "OURS: 25 features, RF": float(np.mean(pr["RF"] == yE))}])
L += ["## 5. EarSet (other earbud, 30 people): rules vs ours", "",
      "Their 214 / 96 features need orientation and gravity channels EarSet does not have.", "",
      bold(R5).to_markdown(index=False), ""]

# ---- summary
summ = []
for title, df in (("1 same person, random", R1[R1.split == "random 5-fold"]), ("1 same person, by time", R1[R1.split == "by time"]),
                  ("2 new person (LOSO)", R2[R2["test person"] != "MEAN"]), ("3 across tools / AirPods", R3),
                  ("4 own labels, by time", R4)):
    summ.append({"test": title, **{n: df[n].mean() for n in names}})
summ.append({"test": "5 EarSet LOSO", **{n: R5[n].iloc[0] if n in R5 else np.nan for n in names}})
S = pd.DataFrame(summ)
L[4:4] = ["## Summary (mean accuracy per test)", "", bold(S).to_markdown(index=False), ""]
(ROOT / "results" / "all_data_benchmark.md").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
