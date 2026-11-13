"""Two-person check of the full v5 set (S03, S8): within-person and cross-person, per gesture. Run from ours/algorithm.
Summarised in ours/FINDINGS.md (F11)."""
import sys, numpy as np, pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_predict, StratifiedKFold
from sklearn.metrics import confusion_matrix
B = Path(r"C:\Users\Orion\Desktop\Temporal-Head-Gesture-Recognition\ours\algorithm\scripts\benchmark_all.py")
src = B.read_text(encoding="utf-8").split("# ------------------------------------------------------------------ run")[0]
ns = {"__file__": str(B), "__name__": "b"}; exec(compile(src, str(B), "exec"), ns)
of, r96, t214, clean, OUR, CH = (ns[k] for k in ("of","receiver_96","theirs_214","clean","OUR","CH"))
REPO = Path(r"C:\Users\Orion\Desktop\Temporal-Head-Gesture-Recognition")
rows = []
for f, p in (("dataset_S03.csv","S03"),("dataset_S8.csv","S8")):
    d = pd.read_csv(REPO/f, low_memory=False)
    d = d[(d.quality=="ok") & (d.in_window==1)]
    d = d[~d.idle_variant.astype(str).str.endswith("long")]
    for tid, g in d.groupby("take_id", sort=False):
        x = g.sort_values("timestamp_ns")[CH].astype(float).reset_index(drop=True)
        n = np.linalg.norm(x[["gravX","gravY","gravZ"]].to_numpy(),axis=1).mean()
        if n > 3: x[["gravX","gravY","gravZ","accX","accY","accZ"]] /= 9.81
        lab = g.label.iloc[0] if g.label.iloc[0]!="idle" else "idle_"+str(g.idle_variant.iloc[0])
        fo = of.event_features(x, 50, heading=None); o=[fo[k] for k in OUR]; t=t214(x)
        rows.append(dict(person=p, label=lab, group=g.group.iloc[0], ours=o, r96=r96(x), t214=t, both=o+t))
D = pd.DataFrame(rows)
mk = lambda: RandomForestClassifier(300, random_state=0, n_jobs=-1)
out = []
for fs in ("ours","r96","t214","both"):
    for p in ("S03","S8"):
        s = D[D.person==p]; k = 5 if p=="S03" else 4
        pr = cross_val_predict(mk(), clean(s[fs].tolist()), s.label, cv=StratifiedKFold(k, shuffle=True, random_state=0))
        out.append((fs, f"within {p}", np.mean(pr==s.label)))
        if fs=="both": D.loc[s.index, "pred_"+p] = pr
    for a,b in (("S03","S8"),("S8","S03")):
        tr, te = D[D.person==a], D[D.person==b]
        m = mk().fit(clean(tr[fs].tolist()), tr.label); pr = m.predict(clean(te[fs].tolist()))
        out.append((fs, f"train {a} -> test {b}", np.mean(pr==te.label)))
        if fs=="both": D.loc[te.index, "x_"+b] = pr
R = pd.DataFrame(out, columns=["features","test","acc"]).pivot(index="test", columns="features", values="acc")
print(R.round(2).to_string())
for p in ("S03","S8"):
    s = D[D.person==p]
    print(f"\nper gesture, within {p} (both feats): acc | most confused with")
    for lab, g in s.groupby("label"):
        wrong = g["pred_"+p][g["pred_"+p]!=lab]
        print(f"  {lab:30s} {np.mean(g['pred_'+p]==lab):.2f}  {wrong.value_counts().head(2).to_dict()}")
s = D[D.person=="S8"]
print("\ncross S03->S8 per gesture:")
for lab, g in s.groupby("label"):
    print(f"  {lab:30s} {np.mean(g['x_S8']==lab):.2f}  {g['x_S8'][g['x_S8']!=lab].value_counts().head(2).to_dict()}")
# group-level
D["gl"] = D.group.replace({"idle":"idle"})
for p in ("S03","S8"):
    s=D[D.person==p]; pr=s["pred_"+p].map(dict(zip(D.label,D.gl)))
    print(p,"group-level acc (head/face/combo/idle):", round(np.mean(pr==s.gl),2))
