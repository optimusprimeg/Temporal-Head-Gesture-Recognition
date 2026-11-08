"""Figures that show how the algorithm works on real data -> results/figures/*.png

    python scripts/make_figures.py

1_timeline_p01.png       P01's app session: rotation speed over time, the detector's variable-length events,
                         and the label each event got from the cue log
2_examples_p01.png       one real event per motion in the head frame (x = ear-to-ear, y = nose, z = vertical)
3_axis_shares_p01.png    which axis each motion turns about (share of rotation), mean over P01's events
4_variance_earset.png    R variance components per feature on EarSet (gesture / person / style / repetition)
"""
import importlib.util
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "results" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
SESSION = (ROOT.parent / "data" / "internal GG 01" / "P01_ghanshyam_s1_airpodspro2_20261107_024251"
           / "P01_ghanshyam_s1_airpodspro2_20261107_024251")

# reference palette (dataviz skill, light mode)
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
MOTIONS = ["nod_down", "look_up", "tilt_left", "tilt_right", "turn_left", "turn_right", "circle_cw", "circle_ccw"]

plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False})

spec = importlib.util.spec_from_file_location("person_report", ROOT / "scripts" / "person_report.py")
pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr)


def timeline(rec, ev, df):
    cues = rec.cues[rec.cues.kind == "rounds"]
    t0, t1 = cues.t_s.min() - 3, cues.t_s.min() + 62
    a, b = rec.index(t0), rec.index(t1)
    g = np.linalg.norm(rec.rot[a:b], axis=1)
    lab = {round(r.t_start, 3): r.label for r in df.itertuples()}
    fig, ax = plt.subplots(figsize=(13, 4.2))
    ax.plot(rec.t[a:b] - t0, g, color=BLUE, lw=1.4, label="rotation speed |ω| (rad/s)")
    ymax = g.max() * 1.25
    for e in ev:
        if e.t_end < t0 or e.t_start > t1:
            continue
        name = lab.get(round(e.t_start, 3), "none")
        motion = name in MOTIONS
        ax.axvspan(e.t_start - t0, e.t_end - t0, color=AQUA if motion else GRID, alpha=0.35 if motion else 0.6, lw=0)
        ax.text((e.t_start + e.t_end) / 2 - t0, ymax * 0.93, name.replace("_", " ") if motion else name,
                ha="center", va="top", fontsize=8, color=INK if motion else INK2, rotation=90 if not motion else 0)
    for q in cues.itertuples():
        if t0 <= q.t_s <= t1:
            ax.plot([q.t_s - t0], [-0.15], marker="^", color=ORANGE, ms=8, clip_on=False)
    ax.plot([], [], marker="^", color=ORANGE, ls="", ms=8, label="GO beep (cue)")
    ax.fill_between([], [], color=AQUA, alpha=0.35, label="detected event, labelled with the cued motion")
    ax.fill_between([], [], color=GRID, alpha=0.6, label="detected event, not the cued motion (extra / none)")
    ax.set_ylim(-0.3, ymax)
    ax.set_xlim(0, t1 - t0)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("|ω| (rad/s)")
    ax.set_title("P01, real AirPods Pro 2: the detector cuts the continuous stream into events of any length "
                 f"(here {min(e.t_end - e.t_start for e in ev):.1f}–{max(e.t_end - e.t_start for e in ev):.1f} s)",
                 loc="left", fontsize=11)
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.16), fontsize=8, ncol=4)
    fig.tight_layout()
    fig.savefig(OUT / "1_timeline_p01.png", dpi=150)
    plt.close(fig)


def examples(rec, ev, df):
    fig, axes = plt.subplots(2, 4, figsize=(13, 5.6), sharey=True)
    by_start = {round(e.t_start, 3): e for e in ev}
    for ax, m in zip(axes.flat, MOTIONS):
        rows = df[(df.label == m)]
        ax.set_title(m.replace("_", " "), loc="left", fontsize=10)
        if rows.empty:
            continue
        if (rows.duration < 3.9).any() and not m.startswith("circle"):
            rows = rows[rows.duration < 3.9]          # a single motion, not one cut at the 4 s cap
        r = rows.iloc[int(np.argmin(np.abs(rows.duration - rows.duration.median())))]   # a typical one
        e = by_start[round(r.t_start, 3)]
        t = np.arange(len(e.rot)) / rec.fs
        for k, (c, n) in enumerate([(BLUE, "x: ear-to-ear (nod)"), (ORANGE, "y: nose (tilt)"), (AQUA, "z: vertical (turn)")]):
            ax.plot(t, e.rot[:, k], color=c, lw=1.8, label=n)
        ax.axhline(0, color=INK2, lw=0.8)
        ax.text(0.98, 0.04, f"{t[-1]:.1f} s", transform=ax.transAxes, ha="right", fontsize=8, color=INK2)
    for ax in axes[1]:
        ax.set_xlabel("time in event (s)")
    for ax in axes[:, 0]:
        ax.set_ylabel("rotation rate, head frame (rad/s)")
    axes[0, 0].legend(fontsize=8, loc="upper left", bbox_to_anchor=(0, 1.0))
    fig.suptitle("One real event per motion (P01): each motion turns about its own axis, and the first swing's sign "
                 "gives the direction", x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "2_examples_p01.png", dpi=150)
    plt.close(fig)


def shares(df):
    one = df[df.label.isin(MOTIONS)]
    g = one.groupby("label")[["share_x", "share_y", "share_z"]].mean().reindex(MOTIONS)
    n = one.groupby("label").size().reindex(MOTIONS)
    fig, ax = plt.subplots(figsize=(9, 4.4))
    y = np.arange(len(MOTIONS))[::-1]
    left = np.zeros(len(MOTIONS))
    for col, c, name in [("share_x", BLUE, "x: ear-to-ear"), ("share_y", ORANGE, "y: nose"), ("share_z", AQUA, "z: vertical")]:
        v = g[col].to_numpy()
        ax.barh(y, v, left=left, color=c, height=0.6, edgecolor=SURFACE, linewidth=2, label=name)
        for yi, l, w in zip(y, left, v):
            if w > 0.12:
                ax.text(l + w / 2, yi, f"{w:.0%}", ha="center", va="center", fontsize=8, color="white")
        left += v
    ax.set_yticks(y, [f"{m.replace('_', ' ')}  (n={k})" for m, k in zip(MOTIONS, n)])
    ax.set_xlim(0, 1)
    ax.set_xlabel("share of the event's rotation about each head axis")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, fontsize=9)
    ax.set_title("Which axis each motion turns about (P01, mean over events)", loc="left", fontsize=11, pad=28)
    fig.tight_layout()
    fig.savefig(OUT / "3_axis_shares_p01.png", dpi=150)
    plt.close(fig)


def variance():
    v = pd.read_csv(ROOT / "results" / "variance_components.csv").sort_values("gesture")
    fig, ax = plt.subplots(figsize=(10, 6.4))
    y = np.arange(len(v))
    left = np.zeros(len(v))
    for col, c, name in [("gesture", BLUE, "gesture"), ("person", ORANGE, "person"),
                         ("person_style", AQUA, "person × gesture (style)"), ("repetition", YELLOW, "repetition")]:
        w = v[col].to_numpy()
        ax.barh(y, w, left=left, color=c, height=0.7, edgecolor=SURFACE, linewidth=1.5, label=name)
        left += w
    ax.set_yticks(y, [f"{f}{'  ✓ kept' if k else ''}" for f, k in zip(v.feature, v.keep)])
    ax.set_xlim(0, 1)
    ax.set_xlabel("share of the feature's variance (lme4 mixed model, 30 people)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=4, fontsize=9)
    ax.set_title("EarSet: which features measure the gesture and which measure the person", loc="left",
                 fontsize=11, pad=28)
    fig.tight_layout()
    fig.savefig(OUT / "4_variance_earset.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    rec, p, ev, report, df = pr.session_events(SESSION, 1.5)
    timeline(rec, ev, df)
    examples(rec, ev, df)
    shares(df)
    variance()
    print("wrote", ", ".join(sorted(f.name for f in OUT.glob("*.png"))))
