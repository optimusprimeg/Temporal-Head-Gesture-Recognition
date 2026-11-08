# ours

The active CS724 project. Start with `../README.md` (overview, direction, map), then `WHY_WE_CHANGED.md` and
`experimental_design.md`.
The older folders (`../prior_work/teammates_repo/`, `../prior_work/gesture_lab/`) are prior work: we read their
results but do not build on their code blindly.

## Status (2026-11-08)

Pipeline built and checked on EarSet and P01; Gesture Collector v3 (Mac + iPhone) released; pilot next.

## Files

| File | What |
|---|---|
| `WHY_WE_CHANGED.md` | the earlier clip-based pipeline vs ours, with the numbers (for the team) |
| `experimental_design.md` | current design (v3): hypotheses, session, labels, analysis plan, stages |
| `PROJECT_REVIEW.md` | full review: gaps, real-world use, related work, decisions |
| `data/external/earset/` | public EarSet dataset (30 people, in-ear IMU, nod/shake/tilt, face, negatives); git-ignored |
| `data/external/EARSET_NOTES.md` | what EarSet contains, units, and its caveats |
| `sensor/AIRPODS_DATA.md` | what each AirPods column is, its unit and frame (checked on our data); Android: no |
| `archive/` | superseded: `collector_v3/` (Sensor Logger era cue script), `experimental_design_v0.md` |
| `algorithm/` | **gesturekit**: modular pipeline (load, QC, calibrate, detect, features, classify, gate, pair decoder), labeller, simulator, tests, R variance-component analysis |
| `mac_app/` | macOS app that reads AirPods motion (built on GitHub, branch `mac-app`); `APP_V2_PLAN.md` = plan for the full data-collection app; `GestureCollector/` = that app, v3 (Mac + iPhone, experiment files, live recogniser); `PILOT_GUIDE.md` = how to run the pilot |
| `website/` | explainer site for readers: commands, data collection, features + R, real-world problems, status and the independent check. Open `website/index.html`, or serve the folder (`python -m http.server --directory website`) |
| `phase0/` | Phase 0 on EarSet: head frame vs raw axes, which features are gesture vs person, false alarms |

## Decisions so far

- No fixed time window: detect variable-length events, then classify.
- No hand-picked "214 feature" Random Forest. Features are physically motivated and selected by statistics
  (R, mixed models) for "separates gestures, not people".
- Vocabulary: a few robust primitives combined into commands, instead of 20 independent gestures (proposal).
- Two devices: AirPods Pro 2 + AirPods 5 (crossover), recorded on a Mac or an iPhone.
- About 20 participants: 5 of us + 15 others, 40-50 takes per gesture each.
