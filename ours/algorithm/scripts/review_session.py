"""Review one Gesture Collector session (zip or folder) -> ours/data/reviews/<session>.md (local, not in git).

  python scripts/review_session.py <session.zip | session folder> [more ...]

What it checks:
  1. who / what: session.json (participant, AirPods, experiment, status, time budget, early end, can't-do list)
  2. stream health: rate, gaps, earbud side changes, per segment
  3. trials: per motion how many were done / skipped / can't-do / retaken, the app's own checks (motion count,
     too small, posture jump, mismatch vote), signal strength (peak rotation in the cue window / still level)
  4. recording order: were motions mixed (rounds) or in blocks
  5. a quick same-person classifier on the cue windows (ours 25 + receiver 96, random forest, first 60 % of each
     motion's trials train, last 40 % test) next to the POSTURE ONLY check. Needs >= 3 trials per motion.
Nothing in the session is changed; a zip is unpacked into ours/data/reviews/_unzipped/.
"""
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
src = (HERE / "benchmark_all.py").read_text(encoding="utf-8").split(
    "# ------------------------------------------------------------------ run")[0]
ns = {"__file__": str(HERE / "benchmark_all.py"), "__name__": "bench"}
exec(compile(src, "benchmark_all.py", "exec"), ns)
of, receiver_96, clean, OUR, CH = ns["of"], ns["receiver_96"], ns["clean"], ns["OUR"], ns["CH"]
REPO = ns["REPO"]
OUT = REPO / "ours" / "data" / "reviews"


def session_folder(p: Path) -> Path:
    if p.is_dir():
        hits = [q.parent for q in p.rglob("session.json") if "__MACOSX" not in q.parts]
        return hits[0] if hits else p
    dest = OUT / "_unzipped" / p.stem
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(p) as z:
        for m in z.namelist():
            if "__MACOSX" in m or m.endswith("/"):
                continue
            target = (dest / m).resolve()
            if dest.resolve() not in target.parents:          # never write outside the folder
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(m))
    return session_folder(dest)


def md(df, index=False):
    return df.to_markdown(index=index) if len(df) else "(none)"


def review(folder: Path):
    meta = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    exp = json.loads((folder / "experiment.json").read_text(encoding="utf-8")) if (folder / "experiment.json").exists() else {}
    state = json.loads((folder / "state.json").read_text(encoding="utf-8")) if (folder / "state.json").exists() else {}
    groups = {m["id"]: m.get("group", "head") for m in exp.get("motions", [])}
    cue_files = sorted(folder.glob("cues*.csv"))
    cues = pd.concat([pd.read_csv(f) for f in cue_files], ignore_index=True) if cue_files else pd.DataFrame()
    segs = sorted(folder.glob("stream_*.csv"))
    st = pd.concat([pd.read_csv(f).assign(segment=f.stem) for f in segs], ignore_index=True) if segs else pd.DataFrame()
    name = meta.get("session", folder.name)
    L = [f"# Review: {name}", "",
         f"Made by `algorithm/scripts/review_session.py` from `{folder.name}`.", ""]

    # 1 who / what
    info = {"participant": meta.get("participant"), "AirPods": meta.get("device"),
            "experiment": f"{meta.get('experimentName')} ({meta.get('planVersion')})", "app": meta.get("appVersion"),
            "platform": meta.get("platform"), "status": meta.get("status"), "time budget (min)": meta.get("budgetMin"),
            "core blocks done": ", ".join(meta.get("coreBlocksDone", [])) or "none",
            "modules done": ", ".join(meta.get("modulesDone", [])) or "none",
            "earbud switches": meta.get("earbudSwitches"), "data gaps": meta.get("gaps"),
            "can't do": ", ".join(state.get("cantDo") or []) or "none"}
    L += ["## 1. Session", "", md(pd.Series(info).to_frame("value"), index=True), ""]
    notes = folder / "notes.csv"
    if notes.exists():
        n = pd.read_csv(notes)
        L += ["Experimenter notes and app events:", "", md(n[["note"]].tail(25)), ""]

    # 2 stream
    if len(st):
        rows = []
        for s, g in st.groupby("segment"):
            t = g.sensor_ns.to_numpy(np.int64)
            dt = np.diff(t) / 1e9
            rows.append({"segment": s, "samples": len(g), "minutes": round((t[-1] - t[0]) / 6e10, 1),
                         "rate Hz": round(1 / np.median(dt), 1) if len(dt) else 0,
                         "gaps > 0.1 s": int((dt > 0.1).sum()), "longest gap s": round(float(dt.max()), 2) if len(dt) else 0,
                         "earbud": "/".join(g.sensor_location.astype(str).unique()),
                         "|g| median": round(float(np.linalg.norm(g[["gravX", "gravY", "gravZ"]].to_numpy(), axis=1).mean()), 2)})
        L += ["## 2. Stream", "", md(pd.DataFrame(rows)), ""]

    if not len(cues):
        L += ["No cues.csv: nothing more to review."]
        return name, L
    trials = cues[cues.kind.isin(["rounds", "practice", "commands"])].copy()
    for c in ["flags", "check_vote", "check_rule", "check_model", "check_dtw", "peak_rot", "live_verdict", "shown_sensor_ns", "note"]:
        if c not in trials:
            trials[c] = np.nan
    trials["flags"] = trials["flags"].fillna("").astype(str)

    # still level (calibration still cues) for signal x quiet
    st_ns = st.sensor_ns.to_numpy(np.int64) if len(st) else np.array([], np.int64)
    spd = np.linalg.norm(st[["rotX", "rotY", "rotZ"]].to_numpy(float), axis=1) if len(st) else np.array([])

    def window(a, b):
        i, j = np.searchsorted(st_ns, a), np.searchsorted(st_ns, b)
        return i, j

    still = cues[(cues.kind == "calibration") & (cues.motion == "still")]
    q = []
    for _, r in still.iterrows():
        i, j = window(int(r.sensor_ns_est), int(r.sensor_ns_est + r.window_s * 1e9))
        if j - i > 20:
            q.append(np.median(spd[i:j]))
    quiet = float(np.median(q)) if q else np.nan

    # 3 trials per motion
    rows = []
    for m, g in trials.groupby("motion"):
        done = g[g.status == "done"]
        first = done[done.attempt == 1] if "attempt" in done else done
        peaks = []
        for _, r in done.iterrows():
            a = int(r.shown_sensor_ns) if "shown_sensor_ns" in r and pd.notna(r.shown_sensor_ns) else int(r.sensor_ns_est)
            i, j = window(a - 300_000_000, int(r.sensor_ns_est + r.window_s * 1e9))
            if j > i:
                peaks.append(spd[i:j].max())
        fl = pd.Series([f for x in done["flags"] for f in x.split(";") if f]).value_counts()
        rows.append({"motion": m, "group": groups.get(m, "?"), "done": len(done),
                     "skipped": int((g.status == "skipped").sum()), "can't do": int((g.status == "cant_do").sum()),
                     "retakes": int((done.note.fillna("").str.contains("retake")).sum()),
                     "count ok": f"{(first.live_verdict.fillna('').str.startswith('✓')).mean():.0%}" if len(first) and first.live_verdict.notna().any() else "-",
                     "mismatch": int(fl.get("mismatch", 0)), "too small": int(fl.get("too_small", 0)),
                     "posture jump": int(fl.get("posture_jump", 0)),
                     "peak rot x still": round(float(np.median(peaks)) / quiet, 1) if peaks and quiet == quiet else "-"})
    L += ["## 3. Trials per motion", "",
          f"Still level (median rotation during the calibration still poses): {quiet:.3f} rad/s. "
          "'peak rot x still' = median peak rotation in the cue window / still level (head motions are usually 30-100x, "
          "face motions 1-5x). 'count ok' = first attempts where the app saw the expected number of motions.", "",
          md(pd.DataFrame(rows)), ""]
    v = trials[trials.check_vote.notna() & (trials.check_vote != "")]
    if len(v):
        cm = pd.crosstab(v.motion, v.check_vote)
        L += ["App's 3-way check (rules / model / own templates) per motion:", "", md(cm, index=True), ""]

    # 4 order
    seq = trials[trials.kind == "rounds"].motion.tolist()
    if len(seq) > 3:
        runs = 1 + sum(a != b for a, b in zip(seq, seq[1:]))
        L += ["## 4. Recording order", "",
              f"{len(seq)} round trials in {runs} runs of the same motion "
              f"({'mixed, good' if runs > 0.6 * len(seq) else 'BLOCKED: posture/time can stand in for the motion'}).", ""]

    # 5 quick classifier
    use = trials[(trials.kind == "rounds") & (trials.status == "done")]
    X, Xr, P, y, order = [], [], [], [], []
    for _, r in use.iterrows():
        a = int(r.shown_sensor_ns) if pd.notna(r.get("shown_sensor_ns")) else int(r.sensor_ns_est)
        i, j = window(a - 300_000_000, int(r.sensor_ns_est + r.window_s * 1e9))
        if j - i < 20:
            continue
        w = st.iloc[i:j][CH].astype(float).reset_index(drop=True)
        f = of.event_features(w, 50)
        X.append([f[k] for k in OUR])
        Xr.append(receiver_96(w))
        gm = w[of.GRAV].to_numpy().mean(0)
        P.append(list(gm / np.linalg.norm(gm)) + list(w[["yaw", "pitch", "roll"]].mean()))
        y.append(r.motion)
        order.append(r.trial)
    y = np.array(y)
    if len(y) and pd.Series(y).value_counts().min() >= 3 and len(set(y)) >= 2:
        from sklearn.ensemble import RandomForestClassifier
        D = pd.DataFrame({"y": y, "o": order})
        frac = (D.sort_values("o").groupby("y").cumcount() / D.groupby("y").y.transform("size")).reindex(D.index).to_numpy()
        tr, te = frac < 0.6, frac >= 0.6
        res, per = [], {}
        for nm, M in [("ours 25", X), ("receiver 96", Xr), ("ours + 96", np.hstack([clean(X), clean(Xr)])),
                      ("POSTURE ONLY", P)]:
            M = clean(M)
            pr = RandomForestClassifier(300, random_state=0, n_jobs=-1).fit(M[tr], y[tr]).predict(M[te])
            res.append({"features": nm, "accuracy (later trials)": round(float(np.mean(pr == y[te])), 2)})
            per[nm] = pd.Series(pr == y[te]).groupby(y[te]).mean().round(2)
        L += ["## 5. Same-person classifier on the cue windows", "",
              f"{len(y)} trials, {len(set(y))} motions, chance {1 / len(set(y)):.2f}. Train on each motion's first 60 % "
              "of trials, test on the rest. Trust it only where it beats POSTURE ONLY clearly.", "",
              md(pd.DataFrame(res)), "", "Per motion:", "", md(pd.DataFrame(per), index=True), ""]
    else:
        L += ["## 5. Classifier", "", "Not enough trials yet (needs 3 per motion).", ""]
    return name, L


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    OUT.mkdir(parents=True, exist_ok=True)
    for arg in sys.argv[1:]:
        folder = session_folder(Path(arg))
        name, L = review(folder)
        out = OUT / f"{name}.md"
        out.write_text("\n".join(L), encoding="utf-8")
        print("\n".join(L))
        print(f"\n-> {out}")
