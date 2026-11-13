"""Micro-gesture transfer study on the teammates v5 files (dataset_S03/S8/S9.csv at the repo root): within-person,
train on n people -> test on a new one, few-shot (k own reps), per-person feature normalisation. Run from ours/algorithm.
Numbers summarised in ours/FINDINGS.md (F12-F15)."""
import itertools, numpy as np, pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_predict, StratifiedKFold
B = Path(r"C:\Users\Orion\Desktop\Temporal-Head-Gesture-Recognition\ours\algorithm\scripts\benchmark_all.py")
src = B.read_text(encoding="utf-8").split("# ------------------------------------------------------------------ run")[0]
ns = {"__file__": str(B), "__name__": "b"}; exec(compile(src, str(B), "exec"), ns)
of, r96, t214, clean, OUR, CH = (ns[k] for k in ("of","receiver_96","theirs_214","clean","OUR","CH"))
REPO = Path(r"C:\Users\Orion\Desktop\Temporal-Head-Gesture-Recognition")
rows = []
for f, p in (("dataset_S03.csv","S03"),("dataset_S8.csv","S8"),("dataset_S9.csv","S9")):
    d = pd.read_csv(REPO/f, low_memory=False)
    d = d[(d.quality=="ok") & (d.in_window==1) & d.group.isin(["face","combo","idle"])]
    d = d[(d.group != "idle") | d.idle_variant.isin(["still","swallow"])]
    for tid, g in d.groupby("take_id", sort=False):
        x = g.sort_values("timestamp_ns")[CH].astype(float).reset_index(drop=True)
        if len(x) < 20: continue
        if np.linalg.norm(x[["gravX","gravY","gravZ"]].to_numpy(),axis=1).mean() > 3:
            x[["gravX","gravY","gravZ","accX","accY","accZ"]] /= 9.81
        lab = g.label.iloc[0] if g.label.iloc[0]!="idle" else "idle_"+str(g.idle_variant.iloc[0])
        fo = of.event_features(x, 50, heading=None)
        rows.append(dict(person=p, label=lab, group=g.group.iloc[0],
                         both=[fo[k] for k in OUR]+t214(x), r96=r96(x)))
D = pd.DataFrame(rows)
common = set.intersection(*[set(D[D.person==p].label) for p in D.person.unique()])
D = D[D.label.isin(common)].reset_index(drop=True)
P = sorted(D.person.unique()); L = sorted(common)
print("people", P, "classes", len(L), "clips", D.groupby("person").size().to_dict())
mk = lambda: RandomForestClassifier(300, random_state=0, n_jobs=-1)
def fit_pred(tr, te, fs):
    m = mk().fit(clean(tr[fs].tolist()), tr.label); return m.predict(clean(te[fs].tolist()))
res = {}
# 1 within person
for fs in ("both","r96"):
    for p in P:
        s = D[D.person==p]; k = int(min(5, s.label.value_counts().min()))
        pr = cross_val_predict(mk(), clean(s[fs].tolist()), s.label, cv=StratifiedKFold(k, shuffle=True, random_state=0))
        D.loc[s.index, f"within_{fs}"] = pr
# 2 N-people curve (train on n other people, test on held-out), every combo
curve = []
for fs in ("both","r96"):
    for te in P:
        others = [q for q in P if q != te]
        for n in range(1, len(others)+1):
            for comb in itertools.combinations(others, n):
                tr = D[D.person.isin(comb)]; t = D[D.person==te]
                pr = fit_pred(tr, t, fs)
                curve.append(dict(fs=fs, test=te, n=n, train="+".join(comb), acc=np.mean(pr==t.label)))
                if n == len(others) and fs=="both": D.loc[t.index, "lopo"] = pr
                if n == 1:
                    for lab in L:
                        mm = (t.label==lab).to_numpy()
                        res.setdefault((fs,lab), []).append(np.mean(pr[mm]==lab))
C = pd.DataFrame(curve)
print("\n== train on n other people -> test on new person (mean over all combos) ==")
print(C.groupby(["fs","n"]).acc.agg(["mean","min","max","count"]).round(2).to_string())
print(C[C.fs=="both"].round(2).to_string(index=False))
# 3 few-shot personalisation: all other people + k reps of the test person
print("\n== others + k of the new person's own reps (both feats) ==")
rng = np.random.default_rng(0); fsr = []
for k in (0,1,2,3):
    if k == 0: pass
    accs=[]
    for te in P:
        t = D[D.person==te]; tr0 = D[D.person!=te]
        for rep in range(3):
            idx = [i for lab in L for i in rng.permutation(t.index[t.label==lab].to_numpy())[:max(0, min(k, int((t.label==lab).sum())-1))]]
            pick = t.loc[idx]
            rest = t.drop(pick.index)
            pr = fit_pred(pd.concat([tr0, pick]) if len(pick) else tr0, rest, "both"); accs.append(np.mean(pr==rest.label))
    print(f"  k={k}: {np.mean(accs):.2f}")
# 4 per gesture table
print("\n== per gesture (both feats): within-person | 1 other person -> new | 2 others -> new (LOPO) ==")
out=[]
for lab in L:
    m = D.label==lab
    w = np.mean(D.loc[m,"within_both"]==lab); one = np.mean(res[("both",lab)]); lo = np.mean(D.loc[m,"lopo"]==lab)
    per = {p: round(float(np.mean(D.loc[m&(D.person==p),"lopo"]==lab)),2) for p in P}
    wrong = D.loc[m & (D.lopo!=lab),"lopo"].value_counts().head(2).to_dict()
    kind = ("not separable" if w < 0.6 else "transfers" if lo >= 0.6 else "personal (needs own data)")
    out.append(dict(gesture=lab, within=round(w,2), one_person=round(one,2), lopo=round(lo,2), **{f"lopo_{p}":v for p,v in per.items()}, verdict=kind, confused_with=wrong))
O = pd.DataFrame(out).sort_values("lopo", ascending=False)
print(O.to_string(index=False))
O.to_csv(r"C:/Users/Orion/AppData/Local/Temp/claude/25f01b2e581a05b7/ca1a2936-d21d-4cdd-8d55-924fa3b8f529/scratchpad/micro_table.csv", index=False)
C.to_csv(r"C:/Users/Orion/AppData/Local/Temp/claude/25f01b2e581a05b7/ca1a2936-d21d-4cdd-8d55-924fa3b8f529/scratchpad/micro_curve.csv", index=False)

# 5 per-person normalisation (unsupervised: each person's features z-scored by their own mean/std over all their clips)
print("\n== LOPO with per-person feature normalisation ==")
for fs in ("both","r96"):
    X = {p: np.nan_to_num(np.array(clean(D[D.person==p][fs].tolist()), float)) for p in P}
    Z = {p: (X[p]-X[p].mean(0))/(X[p].std(0)+1e-9) for p in P}
    for nmode, XX in (("raw", X), ("per-person z", Z)):
        accs = []
        for te in P:
            trp = [q for q in P if q != te]
            m = mk().fit(np.vstack([XX[q] for q in trp]), pd.concat([D[D.person==q].label for q in trp]))
            accs.append(np.mean(m.predict(XX[te]) == D[D.person==te].label.to_numpy()))
        print(f"  {fs:5s} {nmode:13s} " + "  ".join(f"{p}:{a:.2f}" for p,a in zip(P,accs)) + f"  mean {np.mean(accs):.2f}")
