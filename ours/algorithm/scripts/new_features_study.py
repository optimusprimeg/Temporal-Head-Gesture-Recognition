"""Three new feature ideas for micro (face + combo) gestures, tested on every v5-format person we have
(dataset_S03 / S8 / S9 / S12.csv at the repo root; S12 = Yash, app session, LEFT bud, the rest RIGHT).

  bands   vibration bands: log energy of acc and gyro (each axis + magnitude) in 6 bands up to 25 Hz, band shares,
          spectral centroid / flatness / peak frequency (jaw, teeth and eyebrow shake the bud differently)
  halves  two-halves: split the take at the quietest point between 30 and 70 % of it, the same small feature set on
          each half + their difference + where each part peaks (for X_then_Y vs Y_then_X combos)
  idle    each person's own sitting-still noise as the baseline: every feature becomes (f - idle median) / idle MAD.
          Baseline = 3 s windows of the 60 s still_long idle (S03, S8, S12) or the 3 s idle_still takes (S9, which
          has no long idle). Idle still is never a class here, so no label leaks.

Base = our 25 + the teammates' 214 features (as in micro_transfer_study.py). Random forest, 300 trees.
Within person: 5-fold CV per person. New person: train on the other people, test on the held-out one (LOPO).
Swap = combos whose swapped twin exists (A_then_B vs B_then_A): accuracy on those, and how often the twin is named.
Units: acc in g, gravity in m/s^2 in all four files (app_to_v5_csv.py converts acc since 2026-11-14); gravity is
divided by 9.81 here. Run from ours/algorithm:  python scripts/new_features_study.py
"""
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict

B = Path(__file__).resolve().parent / "benchmark_all.py"
src = B.read_text(encoding="utf-8").split("# ------------------------------------------------------------------ run")[0]
ns = {"__file__": str(B), "__name__": "b"}
exec(compile(src, str(B), "exec"), ns)
of, t214, clean, OUR, CH = (ns[k] for k in ("of", "theirs_214", "clean", "OUR", "CH"))
REPO = Path(__file__).resolve().parents[3]
FS = 50.0
PEOPLE = ["S03", "S8", "S9", "S12"]
BANDS = [(0.5, 3), (3, 6), (6, 10), (10, 15), (15, 20), (20, 25)]


# ------------------------------------------------------------------ features
def _spec(sig):
    s = np.asarray(sig, float) - np.mean(sig)
    n = len(s)
    p = np.abs(np.fft.rfft(s * np.hanning(n))) ** 2
    f = np.fft.rfftfreq(n, 1 / FS)
    return f, p


def bands(x):
    acc = x[["accX", "accY", "accZ"]].to_numpy(float)
    rot = x[["rotX", "rotY", "rotZ"]].to_numpy(float)
    sigs = [acc[:, i] for i in range(3)] + [np.linalg.norm(acc, axis=1)] + \
           [rot[:, i] for i in range(3)] + [np.linalg.norm(rot, axis=1)]
    out = []
    for k, s in enumerate(sigs):
        f, p = _spec(s)
        e = np.array([p[(f >= lo) & (f < hi)].sum() for lo, hi in BANDS])
        out += list(np.log(e + 1e-12))
        if k in (3, 7):                                   # magnitudes: shares + shape of the spectrum
            tot = e.sum() + 1e-12
            out += list(e / tot)
            m = f >= 0.5
            pm, fm = p[m] + 1e-12, f[m]
            out += [float((fm * pm).sum() / pm.sum()),                      # centroid
                    float(np.exp(np.mean(np.log(pm))) / np.mean(pm)),       # flatness
                    float(fm[np.argmax(pm)])]                               # peak frequency
    return out


def _part(x):
    acc = x[["accX", "accY", "accZ"]].to_numpy(float)
    rot = x[["rotX", "rotY", "rotZ"]].to_numpy(float)
    am, rm = np.linalg.norm(acc, axis=1), np.linalg.norm(rot, axis=1)
    feats = list(np.sqrt((rot ** 2).mean(0))) + list(np.sqrt((acc ** 2).mean(0)))
    for s in (am, rm):
        f, p = _spec(s) if len(s) >= 8 else (np.zeros(1), np.zeros(1))
        for lo, hi in ((0.5, 6), (6, 15), (15, 25)):
            feats.append(float(np.log(p[(f >= lo) & (f < hi)].sum() + 1e-12)))
    for k in ("pitch", "roll", "yaw"):
        v = np.unwrap(x[k].to_numpy(float))
        feats.append(float(v.max() - v.min()))
    g = x[["gravX", "gravY", "gravZ"]].to_numpy(float)
    a, b = g[0] / (np.linalg.norm(g[0]) + 1e-9), g[-1] / (np.linalg.norm(g[-1]) + 1e-9)
    feats.append(float(np.degrees(np.arccos(np.clip(a @ b, -1, 1)))))
    return feats


def halves(x):
    acc = x[["accX", "accY", "accZ"]].to_numpy(float)
    rot = x[["rotX", "rotY", "rotZ"]].to_numpy(float)
    am, rm = np.linalg.norm(acc, axis=1), np.linalg.norm(rot, axis=1)
    k = max(1, int(0.3 * FS))
    sm = lambda s: np.convolve(s, np.ones(k) / k, mode="same")
    ea, er = sm(am - np.median(am)), sm(rm)
    env = ea / (ea.std() + 1e-9) + er / (er.std() + 1e-9)
    n = len(env)
    lo, hi = int(0.3 * n), max(int(0.3 * n) + 1, int(0.7 * n))
    cut = lo + int(np.argmin(env[lo:hi]))
    h1, h2 = _part(x.iloc[:cut]), _part(x.iloc[cut:])
    peak = lambda s, a, b: (a + int(np.argmax(s[a:b]))) / n
    return h1 + h2 + list(np.subtract(h2, h1)) + [cut / n, peak(ea, 0, n), peak(er, 0, n),
                                                  peak(env, 0, cut) if cut > 0 else 0.0,
                                                  peak(env, cut, n) if cut < n else 1.0]


def base(x):
    fo = of.event_features(x, FS, heading=None)
    return [fo[k] for k in OUR] + list(t214(x))


def all_feats(x):
    return {"base": base(x), "bands": bands(x), "halves": halves(x)}


# ------------------------------------------------------------------ data
def prep(g):
    x = g.sort_values("timestamp_ns")[CH].astype(float).reset_index(drop=True)
    x[["gravX", "gravY", "gravZ"]] /= 9.81          # gravity m/s^2 -> g; acc is already in g
    return x


rows, baseline = [], {}
for p in PEOPLE:
    d = pd.read_csv(REPO / f"dataset_{p}.csv", low_memory=False)
    d = d[d.quality == "ok"]
    # idle baseline: 3 s windows of the long still idle, else the short idle_still takes
    bl = []
    long_ = d[(d.idle_variant == "still_long")].sort_values("timestamp_ns")
    if len(long_):
        x = prep(long_)
        w = int(3 * FS)
        for i in range(0, len(x) - w, w):
            bl.append(all_feats(x.iloc[i:i + w].reset_index(drop=True)))
    else:
        for _, g in d[(d.in_window == 1) & (d.idle_variant == "still")].groupby("take_id"):
            if len(g) >= 20:
                bl.append(all_feats(prep(g)))
    baseline[p] = bl
    d = d[(d.in_window == 1) & (d.group.isin(["face", "combo"]) | (d.idle_variant == "swallow"))]
    for tid, g in d.groupby("take_id", sort=False):
        if len(g) < 20:
            continue
        lab = g.label.iloc[0] if g.label.iloc[0] != "idle" else "idle_swallow"
        rows.append(dict(person=p, label=lab, group=g.group.iloc[0], **all_feats(prep(g))))
    print(p, "takes", sum(r["person"] == p for r in rows), "baseline windows", len(bl), flush=True)

D = pd.DataFrame(rows)
cnt = D.groupby(["person", "label"]).size().unstack(fill_value=0)
L = sorted(c for c in cnt.columns if (cnt[c] >= 3).all())
D = D[D.label.isin(L)].reset_index(drop=True)
print("classes in common (>= 3 good takes each):", len(L), "| takes per person:", D.groupby("person").size().to_dict())
SWAP = {a: f"{a.split('_then_')[1]}_then_{a.split('_then_')[0]}" for a in L if "_then_" in a}
SWAP = {a: b for a, b in SWAP.items() if b in L}
print("swap pairs:", sorted({tuple(sorted(x)) for x in SWAP.items()}))


def matrix(sub, parts, norm):
    X = np.array([sum((list(r[k]) for k in parts), []) for _, r in sub.iterrows()], float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    if not norm:
        return X
    out = np.empty_like(X)
    for p in sub.person.unique():
        m = (sub.person == p).to_numpy()
        Bm = np.array([sum((list(b[k]) for k in parts), []) for b in baseline[p]], float)
        Bm = np.nan_to_num(Bm, nan=0.0, posinf=0.0, neginf=0.0)
        med = np.median(Bm, 0)
        mad = 1.4826 * np.median(np.abs(Bm - med), 0)
        scale = np.maximum(mad, 0.05 * X.std(0) + 1e-9)    # never divide by ~0 (constant features)
        out[m] = np.clip((X[m] - med) / scale, -50, 50)
    return out


mk = lambda: RandomForestClassifier(300, random_state=0, n_jobs=-1)
CONFIGS = [(("base",), False), (("base", "bands"), False), (("base", "halves"), False),
           (("base", "bands", "halves"), False), (("base",), True), (("base", "bands"), True),
           (("base", "halves"), True), (("base", "bands", "halves"), True)]


def swap_scores(y, pr):
    m = np.isin(y, list(SWAP))
    if not m.any():
        return np.nan, np.nan
    acc = float(np.mean(pr[m] == y[m]))
    twin = float(np.mean([pr[i] == SWAP[y[i]] for i in np.where(m)[0]]))
    return acc, twin


res = []
for parts, norm in CONFIGS:
    name = "+".join(parts) + (" | idle-norm" if norm else "")
    X, y = matrix(D, parts, norm), D.label.to_numpy()
    persons = D.person.to_numpy()
    row = {"features": name, "n_feat": X.shape[1]}
    w_pred = np.empty(len(D), dtype=object)
    for p in PEOPLE:
        m = persons == p
        k = int(min(5, pd.Series(y[m]).value_counts().min()))
        w_pred[m] = cross_val_predict(mk(), X[m], y[m], cv=StratifiedKFold(k, shuffle=True, random_state=0))
        row[f"within_{p}"] = float(np.mean(w_pred[m] == y[m]))
    row["within"] = np.mean([row[f"within_{p}"] for p in PEOPLE])
    row["within_swap"], row["within_twin"] = swap_scores(y, w_pred)
    l_pred = np.empty(len(D), dtype=object)
    for p in PEOPLE:
        m = persons == p
        l_pred[m] = mk().fit(X[~m], y[~m]).predict(X[m])
        row[f"lopo_{p}"] = float(np.mean(l_pred[m] == y[m]))
    row["lopo"] = np.mean([row[f"lopo_{p}"] for p in PEOPLE])
    row["lopo_right3"] = np.mean([row[f"lopo_{p}"] for p in PEOPLE if p != "S12"])
    row["lopo_swap"], row["lopo_twin"] = swap_scores(y, l_pred)
    res.append(row)
    print(f"{name:<34} within {row['within']:.3f}  LOPO {row['lopo']:.3f}  swap(within) {row['within_swap']:.2f}", flush=True)

R = pd.DataFrame(res).set_index("features")
pd.set_option("display.width", 250)
print("\n== mean over people ==")
print(R[["n_feat", "within", "lopo", "lopo_right3", "within_swap", "within_twin", "lopo_swap", "lopo_twin"]].round(3).to_string())
print("\n== per person: within ==")
print(R[[f"within_{p}" for p in PEOPLE]].round(3).to_string())
print("\n== per person: new person (LOPO) ==")
print(R[[f"lopo_{p}" for p in PEOPLE]].round(3).to_string())
out = REPO / "ours" / "algorithm" / "results" / "new_features_study.csv"
R.round(4).to_csv(out)
print("\nsaved", out)
