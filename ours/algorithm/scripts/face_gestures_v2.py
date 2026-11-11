"""Facial micro-gestures on EarSet, done properly: real repetitions, paper methods, new person vs enrollment.
-> results/face_gestures_v2.md   (cached windows: results/face_windows_cache.npz, local only)

Why a v2: v1 (face_gestures_earset.py) took the 12 most active windows per recording, which for weak actions picks
noise. EarSet participants repeated each action on a fixed beat (~5 s, ~24 times per 2-minute recording), so:
1. SEGMENT. Activity envelope (rotation speed + acceleration change, each / its recording median, 0.3 s smoothing).
   Period = autocorrelation peak in 3.5-7 s. Phase = the offset whose beat positions collect the most activity.
   Repetition = 2 s window centred on the activity peak within +-1 s of each beat. Rest = 2 s window half a period
   later (same recording, between repetitions). Everyday = 2 s windows every 1 s from speaking and chewing.
2. METHODS (from the papers):
   RF       hand features (per-axis rms in a gravity-aligned frame, rotation shares, first-swing signs, band
            energies 0.3-3 / 3-8 / 8-15 / 15-25 Hz, peaks) -> random forest.  [ExpressEar/TongueTap-style features]
   STFT     log spectrogram (IMUFace-style: short-time Fourier, per axis) -> logistic regression.
   1NN-DTW  TeethTap: 1-nearest-neighbour with multi-dimensional dynamic time warping on the 6 raw channels
            (25 Hz, Sakoe band 20 %). Needs the person's own templates, so enrollment only.
3. PROTOCOLS
   new person   leave one person out, nothing from the test person.
   enroll k     + k repetitions per action from the test person (weighted x10), tested on their other repetitions.
   own only k   ONLY the test person's k repetitions per action (what TeethTap / ExpressEar-style systems do).
4. QUESTIONS
   Q1 which of the 9 face actions are told apart (9-way), left ear (= AirPods, one bud) and both ears.
   Q2 can each action be detected against rest + talking + chewing: hit rate when the threshold allows 1 % of
      everyday windows to trigger (threshold set on the training people / enrollment data, not on the test person).
   Q3 wink left vs right (EarSet's only one-sided pair; a smirk would be the same problem).
50 Hz everywhere (AirPods rate). EarSet has no smirk, cheek puff or teeth/tongue gestures.
Run from ours/algorithm: python scripts/face_gestures_v2.py
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import uniform_filter1d
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gesturekit.io import earset_people, load_earset  # noqa: E402

FS, W = 50, 100                       # 2 s windows
FACE = ["brow-raiser", "brow-lowerer", "wink-l", "wink-r", "eyes-lr", "eyes-ud", "lip-puller", "chin-raiser",
        "mouth-stretch"]
HEAD = ["nod", "shake", "tilt"]
EVERYDAY = ["speaking", "chewing"]
BANDS = [(0.3, 3), (3, 8), (8, 15), (15, 25)]
CACHE = ROOT / "results" / "face_windows_cache.npz"
rng = np.random.default_rng(0)


# ------------------------------------------------------------------ segmentation
def envelope(rec):
    g = np.nan_to_num(np.linalg.norm(rec.rot, axis=1))
    j = np.r_[0, np.nan_to_num(np.linalg.norm(np.diff(rec.acc, axis=0), axis=1))]
    return uniform_filter1d(g / (np.median(g) + 1e-6) + j / (np.median(j) + 1e-6), int(0.3 * FS))


def beats(env):
    e = env - env.mean()
    ac = np.correlate(e, e, "full")[len(e) - 1:]
    lo, hi = int(3.5 * FS), int(7 * FS)
    T = lo + int(np.argmax(ac[lo:hi]))
    tol = int(0.4 * FS)
    best, phase = -1, 0
    for ph in range(0, T, 5):
        s = sum(env[max(0, c - tol):c + tol].max() for c in range(ph, len(env) - tol, T))
        if s > best:
            best, phase = s, ph
    centres = []
    for c in range(phase, len(env), T):
        a, b = max(0, c - FS), min(len(env), c + FS)
        m = a + int(np.argmax(env[a:b]))
        if m - W // 2 >= 0 and m + W // 2 + T // 2 <= len(env):
            centres.append(m)
    return T / FS, centres


def window(rec, c):
    a = c - W // 2
    return np.nan_to_num(np.hstack([rec.rot[a:a + W], rec.acc[a:a + W], rec.grav[a:a + W]]))  # (W, 9)


def build():
    X, meta = [], []
    for pid in earset_people():
        for act in FACE + HEAD + EVERYDAY:
            L, R = load_earset(pid, act, "left", FS), load_earset(pid, act, "right", FS)
            if L is None or R is None:
                continue
            n = min(len(L), len(R))
            if act in EVERYDAY:
                cs = list(range(W // 2, n - W // 2, FS))
                kinds, T = ["everyday"] * len(cs), 0
            else:
                T, cs = beats(envelope(L))
                rest = [c + int(T * FS / 2) for c in cs]
                kinds = ["rep"] * len(cs) + ["rest"] * len(rest)
                cs = cs + rest
            env = envelope(L)
            for c, k in zip(cs, kinds):
                if c + W // 2 > n:
                    continue
                X.append(np.hstack([window(L, c), window(R, c)]))
                meta.append({"person": pid, "action": act, "kind": k, "period_s": T,
                             "env": float(env[c - W // 2:c + W // 2].mean())})
        print(pid, end=" ", flush=True)
    print()
    X = np.array(X, np.float32)
    M = pd.DataFrame(meta)
    np.savez_compressed(CACHE, X=X, **{c: M[c].to_numpy() for c in M})
    return X, M


if CACHE.exists():
    z = np.load(CACHE, allow_pickle=True)
    X = z["X"]
    M = pd.DataFrame({c: z[c] for c in ["person", "action", "kind", "period_s", "env"]})
else:
    X, M = build()


# ------------------------------------------------------------------ features
def up_frame(w):
    g = w[:, 6:9].mean(0)
    up = -g / (np.linalg.norm(g) + 1e-9)
    z = np.array([0, 0, 1.0])
    v, c = np.cross(up, z), up @ z
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    Rm = np.eye(3) + k + k @ k / (1 + c + 1e-9)
    return w[:, 0:3] @ Rm.T, w[:, 3:6] @ Rm.T


def bandpow(x):
    x = x - x.mean(0)
    P = np.abs(np.fft.rfft(x * np.hanning(len(x))[:, None], axis=0)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / FS)
    return [np.log(P[(f >= a) & (f < b)].sum() + 1e-9) for a, b in BANDS]


def first_lobe(v):
    idx = np.where(np.abs(v) > 0.3 * np.abs(v).max())[0]
    return float(np.sign(v[idx[0]]) * np.abs(v).max()) if len(idx) else 0.0


def ear_feats(w):
    rot, acc = up_frame(w)
    rm, am = np.linalg.norm(rot, axis=1), np.linalg.norm(acc, axis=1)
    e = (rot ** 2).sum(0)
    f = list(np.log(np.sqrt((rot ** 2).mean(0)) + 1e-6)) + list(np.log(np.sqrt((acc ** 2).mean(0)) + 1e-6))
    f += list(e / (e.sum() + 1e-12)) + [first_lobe(rot[:, i]) for i in range(3)]
    f += [first_lobe(acc[:, i]) for i in range(3)]
    f += bandpow(rot) + bandpow(acc)
    f += [np.log(rm.max() + 1e-6), np.log(am.max() + 1e-6), (np.argmax(rm) / len(rm))]
    return f


def feats(w, both):
    L, R = w[:, :9], w[:, 9:]
    f = ear_feats(L)
    if both:
        f += ear_feats(R)
        f += [np.corrcoef(L[:, i], R[:, i])[0, 1] if L[:, i].std() > 0 and R[:, i].std() > 0 else 0 for i in range(6)]
        f += [np.log((np.abs(L[:, i]).mean() + 1e-6) / (np.abs(R[:, i]).mean() + 1e-6)) for i in range(6)]
    return np.nan_to_num(np.array(f, float))


def stft_feats(w, both):
    out = []
    for side in ([w[:, :9]] + ([w[:, 9:]] if both else [])):
        rot, acc = up_frame(side)
        for x in np.hstack([rot, acc]).T:
            segs = np.lib.stride_tricks.sliding_window_view(x - x.mean(), 25)[::12] * np.hanning(25)
            S = np.log(np.abs(np.fft.rfft(segs, axis=1)) ** 2 + 1e-9)       # (frames, 13)
            out += list(S.mean(0)) + list(S.max(0))
    return np.array(out)


print("features ...", flush=True)
F_L = np.array([feats(w, False) for w in X])
F_B = np.array([feats(w, True) for w in X])
S_L = np.array([stft_feats(w, False) for w in X])


# ------------------------------------------------------------------ DTW (vectorised over pairs)
def dtw_many(A, B, band=0.2):
    """A (n, T, d), B (m, T, d) -> (n, m) DTW distances."""
    n, T, _ = A.shape
    m = B.shape[0]
    r = max(1, int(band * T))
    D = np.full((n, m, T + 1, T + 1), np.inf, np.float32)
    D[:, :, 0, 0] = 0
    for i in range(1, T + 1):
        for j in range(max(1, i - r), min(T, i + r) + 1):
            c = np.sqrt(((A[:, None, i - 1] - B[None, :, j - 1]) ** 2).sum(-1))
            D[:, :, i, j] = c + np.minimum(np.minimum(D[:, :, i - 1, j], D[:, :, i, j - 1]), D[:, :, i - 1, j - 1])
    return D[:, :, T, T]


def dtw_input(w):
    x = w[::2, :6]                                   # 25 Hz, left ear rot + acc
    x = x - x.mean(0)
    return (x / (x.std(0) + 1e-6)).astype(np.float32)


# ------------------------------------------------------------------ protocols
people = sorted(M.person.unique(), key=lambda s: int(s[1:]))
rf = lambda: RandomForestClassifier(300, random_state=0, n_jobs=-1, class_weight="balanced")  # noqa: E731
lr = lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=0.3, class_weight="balanced"))  # noqa: E731


def split_enroll(idx_person, y, k, seed):
    """Pick k reps per class of the test person for enrollment; return (enroll_idx, test_idx)."""
    r = np.random.default_rng(seed)
    en, te = [], []
    for c in np.unique(y[idx_person]):
        ids = idx_person[y[idx_person] == c]
        ids = r.permutation(ids)
        en += list(ids[:k])
        te += list(ids[k:])
    return np.array(en, int), np.array(te, int)


def classify(F, mask, classes, protocol, k=0, model=rf, seeds=(0, 1, 2)):
    """Accuracy and per-class recall over people. protocol: new / enroll / own."""
    idx = np.where(mask & M.action.isin(classes).to_numpy())[0]
    y = M.action.to_numpy()
    hits, preds, truth = [], [], []
    for p in people:
        tp = idx[M.person.to_numpy()[idx] == p]
        tr_others = idx[M.person.to_numpy()[idx] != p]
        for s in (seeds if protocol != "new" else (0,)):
            if protocol == "new":
                en, te = np.array([], int), tp
            else:
                en, te = split_enroll(tp, y, k, s)
            if protocol == "own":
                tr, wt = en, np.ones(len(en))
            else:
                tr = np.r_[tr_others, en]
                wt = np.r_[np.ones(len(tr_others)), np.full(len(en), 10.0)]
            m = model()
            if isinstance(m, RandomForestClassifier):
                m.fit(F[tr], y[tr], sample_weight=wt)
            else:
                m.fit(F[tr], y[tr], logisticregression__sample_weight=wt)
            pr = m.predict(F[te])
            preds += list(pr)
            truth += list(y[te])
    preds, truth = np.array(preds), np.array(truth)
    return float(np.mean(preds == truth)), {c: float(np.mean(preds[truth == c] == c)) for c in classes}


def classify_dtw(mask, classes, k, seeds=(0, 1, 2)):
    idx = np.where(mask & M.action.isin(classes).to_numpy())[0]
    y = M.action.to_numpy()
    preds, truth = [], []
    for p in people:
        tp = idx[M.person.to_numpy()[idx] == p]
        for s in seeds:
            en, te = split_enroll(tp, y, k, s)
            A = np.array([dtw_input(X[i]) for i in te])
            B = np.array([dtw_input(X[i]) for i in en])
            d = dtw_many(A, B)
            preds += list(y[en][np.argmin(d, axis=1)])
            truth += list(y[te])
    preds, truth = np.array(preds), np.array(truth)
    return float(np.mean(preds == truth)), {c: float(np.mean(preds[truth == c] == c)) for c in classes}


import json  # noqa: E402

STEPS = ROOT / "results" / "face_gestures_v2_steps.json"   # finished sections, so a crash does not redo them
done = json.loads(STEPS.read_text()) if STEPS.exists() else {}


def cached(key, fn):
    if key not in done:
        done[key] = fn()
        STEPS.write_text(json.dumps(done))
    return done[key]


rep = (M.kind == "rep").to_numpy()
L = ["# Facial micro-gestures on EarSet, v2: real repetitions, paper methods, new person vs enrollment", "",
     "Generated by `algorithm/scripts/face_gestures_v2.py` (method in its header). 30 people, 50 Hz, 2 s windows.", ""]

# segmentation check
seg = M[M.kind != "everyday"].groupby(["action", "kind"]).env.median().unstack()
per = M[M.kind == "rep"].groupby("action").period_s.median()
nrep = M[M.kind == "rep"].groupby("action").size()
segtab = pd.DataFrame({"beat found (s, median)": per.round(1), "repetitions": nrep,
                       "activity rep / rest": (seg["rep"] / seg["rest"]).round(2)}).reindex(FACE + HEAD)
L += ["## Segmentation check", "", "Activity of the found repetitions vs the rest windows between them "
      "(1.0 = the repetitions look like rest, so there is nothing to find).", "", segtab.to_markdown(), ""]
print("\n".join(L[-6:]), flush=True)

# Q1: 9-way face classification
rows, percls = [], {}
for name, F, both in [("RF features, left ear", F_L, False), ("RF features, both ears", F_B, True),
                      ("STFT + logistic, left ear", S_L, False)]:
    r = {"method": name}
    for proto, k in [("new", 0), ("enroll", 1), ("enroll", 3), ("enroll", 5), ("own", 5)]:
        model = lr if name.startswith("STFT") else rf
        acc, pc = cached(f"q1|{name}|{proto}|{k}", lambda: classify(F, rep, FACE, proto, k, model))
        col = "new person" if proto == "new" else (f"enroll {k}" if proto == "enroll" else f"own only {k}")
        r[col] = round(acc, 2)
        if name == "RF features, left ear":
            percls[col] = pc
    rows.append(r)
    print(r, flush=True)
for k in (1, 3, 5):
    acc, pc = cached(f"q1|dtw|{k}", lambda: classify_dtw(rep, FACE, k))
    rows.append({"method": "1NN-DTW (TeethTap), left ear", f"own only {k}": round(acc, 2)})
    percls[f"DTW own {k}"] = pc
    print("dtw", k, acc, flush=True)
Q1 = pd.DataFrame(rows).groupby("method", sort=False).first().reset_index()
L += ["## Q1. Which face action is it? (9 classes, chance 0.11)", "",
      "new person = trained on the other 29 only. enroll k = + k repetitions per action from this person. "
      "own only k = only this person's k repetitions per action.", "", Q1.to_markdown(index=False), "",
      "Per action (recall), RF left ear and DTW:", "", pd.DataFrame(percls).round(2).to_markdown(), ""]

# Q2: detection against rest + talking + chewing
ev = (M.kind.isin(["rest", "everyday"]) & ~M.action.isin(HEAD)).to_numpy()
y_act = M.action.to_numpy()
pp = M.person.to_numpy()
rows = []
def q2(act):
    pos = rep & (y_act == act)
    r = {"action": act}
    for proto, k in [("new", 0), ("enroll", 5)]:
        hit, fa = [], []
        for p in people:
            tr = (pos | ev) & (pp != p)
            te_pos, te_neg = np.where(pos & (pp == p))[0], np.where(ev & (pp == p))[0]
            en = np.array([], int)
            if proto == "enroll":
                en = rng.permutation(te_pos)[:k]
                en_neg = rng.permutation(te_neg)[:20]
                te_pos = np.setdiff1d(te_pos, en)
                te_neg = np.setdiff1d(te_neg, en_neg)
                en = np.r_[en, en_neg]
            if len(te_pos) == 0 or len(te_neg) == 0:     # this person has no repetitions of this action
                continue
            tri = np.r_[np.where(tr)[0], en]
            wt = np.r_[np.ones(tr.sum()), np.full(len(en), 10.0)]
            m = rf().fit(F_L[tri], pos[tri], sample_weight=wt)
            s_tr = m.predict_proba(F_L[np.where(ev & (pp != p))[0]])[:, 1]
            # threshold: 1 % of the TRAINING people's everyday windows (out-of-bag would be stricter)
            thr = np.quantile(s_tr, 0.99)
            hit.append(np.mean(m.predict_proba(F_L[te_pos])[:, 1] > thr))
            fa.append(np.mean(m.predict_proba(F_L[te_neg])[:, 1] > thr))
        col = "new person" if proto == "new" else "enroll 5"
        r[f"{col}: hit"] = round(float(np.mean(hit)), 2)
        r[f"{col}: false"] = round(float(np.mean(fa)), 3)
    return r


for act in FACE + HEAD:
    r = cached(f"q2|{act}", lambda: q2(act))
    rows.append(r)
    print(r, flush=True)
L += ["## Q2. Detect the action against rest + talking + chewing (left ear)", "",
      "Threshold = the score that only 1 % of the TRAINING people's everyday windows exceed (in-sample, so "
      "optimistic for the training side). hit = this person's repetitions caught; false = this person's "
      "rest/talking/chewing windows that would trigger (2 s windows every 1 s: 0.01 = ~36 false triggers per "
      "hour of talking).", "", pd.DataFrame(rows).to_markdown(index=False), ""]

# Q3: wink left vs right
rows = []
for name, F in [("left ear", F_L), ("both ears", F_B)]:
    r = {"features": name}
    for proto, k in [("new", 0), ("enroll", 3), ("own", 5)]:
        acc, _ = cached(f"q3|{name}|{proto}|{k}", lambda: classify(F, rep, ["wink-l", "wink-r"], proto, k))
        r["new person" if proto == "new" else (f"enroll {k}" if proto == "enroll" else f"own only {k}")] = round(acc, 2)
    rows.append(r)
acc, _ = cached("q3|dtw|5", lambda: classify_dtw(rep, ["wink-l", "wink-r"], 5))
rows.append({"features": "1NN-DTW left ear", "own only 5": round(acc, 2)})
L += ["## Q3. Wink left vs right (one-sided pair, like a smirk; chance 0.50)", "",
      pd.DataFrame(rows).to_markdown(index=False), ""]

out = ROOT / "results" / "face_gestures_v2.md"
out.write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
