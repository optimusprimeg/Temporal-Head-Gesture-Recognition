# Temporal Head-Gesture Recognition

**CS724, IIT Kanpur, Group 6.** Silent team commands from small head motions, read by ordinary AirPods.

A team member tilts left, then nods down; the AirPods' motion sensor picks it up, the phone or Mac recognises the
command, and teammates hear "Alpha 2: enemy left", without anyone speaking or raising a hand. The system works on
the **continuous** motion stream: it finds each motion by itself (any length, 0.3-4 s), names it, and turns two
motions in a row into a command, while ignoring everyday movement.

## Where we are (8 Nov 2026)

| | State |
|---|---|
| Recognition pipeline (detector, head frame, features, rules/model, pair decoder) | built in Python; the same logic in Swift, checked equal in every build |
| Single motions, 30 other people (EarSet, nod/turn/tilt) | 0.96 of head gestures recognised, about 0.2 false commands per hour overall (2-3 while speaking) |
| Our AirPods, new device + new person | trained only on EarSet, 21/21 of P01's motions right (axis features). One person |
| Two-motion commands | about 0.88 right with a ≥ 0.5 s pause between the motions (offline, P01's motions); without a pause they merge |
| Data-collection app | **Gesture Collector v3**, Mac + iPhone, experiment files, live recogniser ([download](https://github.com/optimusprimeg/Temporal-Head-Gesture-Recognition/releases/tag/gesture-collector)) |
| Pilot (5 people × 2 sessions) | ready to run: `ours/mac_app/PILOT_GUIDE.md` |
| Team hub (central platform) + demo | planned |

**Are we on the right path?** Yes, for three measured reasons:
1. The earlier clip-based pipeline scored 0.72 on cut clips but found and named only **0.39-0.43** of the gestures
   in a stream. That is why we work on streams.
2. It fell from 0.91 to **0.61** on a new person. Our head frame plus R-screened features transferred from 30
   strangers on another earbud to our AirPods.
3. It had no false-alarm measurement. Ours is measured per hour of real no-gesture time.

What is **not** shown yet: command accuracy on new people, walking, real conversation, covertness. The pilot measures
these. Full reasoning for the team: [`ours/WHY_WE_CHANGED.md`](ours/WHY_WE_CHANGED.md).

## Direction

1. **Self-test on P01** with the data read live on the analysis PC (`selftest.json`): shortest pause, cutting merged
   pairs where the rotation axis changes, walking cues.
2. **Freeze all analysis settings** (git tag), then the **pilot**: P02-P06, Pilot v3, Mac and iPhone.
3. From the pilot: final motions and 20 commands, R screening on our own data (per direction pair), baselines on the
   same splits (old random forest, MiniRocket, DTW).
4. **Main round**, 20 people, frozen `main.json`.
5. **Team hub + demo**: the Mac recognises, teammates' phones hear the command and acknowledge; then the private
   chime with a head-shake cancel, and gating while walking or running.
6. Paper: rewrite `paper/` (the skeleton is still titled "Tongue/Face Gestures").

## Experimental design in one paragraph

20 people (5 team + 15 others), each on both AirPods Pro 2 and AirPods 5 (crossover). One session: calibration and
practice, then a core (enrollment, sitting rounds, small covert rounds, commands, own-pace commands, 8 min of
no-gesture activities, counterbalanced) and rotated optional modules (re-wear, speed and size, posture, walking with
corners, pairs at set pauses, daily-life no-gesture time), fitted into the time available. Six hypotheses: head frame
(H1), two-motion commands (H2), variable-length detection (H3), small motions (H4), statistically chosen features
(H5), false commands (H6). Analysis: leave one person out and cross-device, mixed models, settings frozen before
P02. Details: [`ours/experimental_design.md`](ours/experimental_design.md).

## How data collection evolves

The protocol is an **experiment file** (JSON) the app reads, not code. Changes happen only between stages, and every
session stores the exact file it ran:
**self-test → pilot (`pilot.json`) → main round (`main.json`, frozen)**. A rebuild is needed only for a new kind of
block or a new algorithm.

## Repository map

```
README.md                 this page
ours/                     the active project
  WHY_WE_CHANGED.md       old pipeline vs ours, with the numbers (for the team)
  experimental_design.md  current design (v3)
  PROJECT_REVIEW.md       full review: gaps, real-world use, related work, decisions
  algorithm/              gesturekit (Python pipeline), r/ (screening), scripts/, results/, tests/
  mac_app/                GestureCollector (Mac + iPhone app), AirPods check app, APP_V2_PLAN.md, PILOT_GUIDE.md
  website/                explainer site (open website/index.html)
  phase0/                 first analyses on EarSet and the earlier data
  sensor/                 what each AirPods column means (units, axes)
  archive/                superseded: collector v3, design draft v0
  data/                   recordings (NOT in git)
paper/                    LaTeX skeleton for the report (to rewrite)
prior_work/               the earlier pipeline and its data (NOT in git, read only)
```

## Quick start

From the repository root:

```bash
python -m pytest -q ours/algorithm/tests
```
```bash
python ours/algorithm/scripts/eval_earset.py
```
```bash
python ours/algorithm/scripts/process_session.py "ours/data/<session folder>"
```
```bash
python -m http.server 8765 --directory ours/website
```

The first runs the pipeline tests, the second the EarSet evaluation (`results/earset_pipeline.md`), the third
turns one recorded session into labels, features and a QC report, the last serves the explainer site at
http://localhost:8765.

Recordings and the earlier pipeline's data are kept out of git; ask Ghanshyam for access.
