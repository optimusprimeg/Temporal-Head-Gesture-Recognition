# algorithm: gesturekit

The recognition pipeline as a modular Python package, plus the R analysis. Built 2026-11-06, before real
collector-v3 data exists; tested on simulated sessions and on EarSet. Exploration history stays in `../phase0/`.

```
earbud IMU stream
  └─ io.load_session / load_earset / load_old_takes   -> Recording (one format, SI units, gaps marked)
       └─ qc.check_recording                           -> pass/fail table
       └─ Pipeline
            ├─ calibration: detect.quiet_from (still pose) + frames.calibrate (3 nods, chin down first)
            ├─ detect.detect          causal, variable length, hysteresis; optional return-to-neutral split
            ├─ frames.to_head         gravity up + calibrated heading, signed
            ├─ features.event_features   sets: axis / signed / timing / magnitude
            ├─ classify (registry)    logreg on features | minirocket on signals (optional, needs aeon)
            ├─ decode.gate            not 'none', min probability, min margin
            └─ decode.PairDecoder     (first, second) within 1.5 s -> command; lone motion dropped
  └─ label.label_events            cue log -> ground truth per event (rules: ../experimental_design.md 6b)
  └─ evaluate                       detection, false alarms per hour, commands
  └─ simulate.simulate_session      synthetic collector session (old takes, batching, clock offset, dropouts)
```

All parameters live in `gesturekit/config.py` (dataclasses). To change a stage, change its config or register a new
function/class: feature sets in `features.FEATURE_SETS`, classifiers in `classify.CLASSIFIERS`. Stages only talk
through `Recording`, `Event`, `Motion`, `Command`.

## Use

```
cd ours/algorithm
python -m pytest tests -q                                  # 20 tests: synthetic signals + end-to-end
python scripts/process_session.py <session folder>         # after every recording: events.csv, cue_report, qc.md
python scripts/simulate_session.py <out folder> [subject] [seed]   # fake session to try things
python scripts/eval_earset.py                              # full pipeline on EarSet -> results/earset_pipeline.md
"C:\Program Files\R\R-4.6.1\bin\Rscript.exe" r/variance_components.R results/earset_events.csv 100
```
Python 3.15 with numpy, pandas, scipy, scikit-learn, tabulate, pytest. R 4.6.1 with lme4.

## Results so far

**Full pipeline on EarSet, 30 people, leave one person out** (`results/earset_pipeline.md`). Causal detector →
head frame → 16 features (axis + signed + timing) → logistic regression → gate → pair rule. Worst case: every pair
of two different motions is a command. Detector quiet level = still pose × `quiet_scale` (3.0 since 2026-11-07;
chosen on the Mac AirPods test, not on EarSet; the 1.0 numbers are kept for comparison).

| gate (min probability, margin) | head gestures recognised | false single motions / h | **false commands / h** | (with quiet_scale 1.0) |
|---|---|---|---|---|
| 0.5, 0.1 | 0.96 | 39 | 0.20 | 0.91, 120, 1.5 |
| 0.7, 0.3 | 0.93 | 28 | 0.07 | 0.87, 72, 0.6 |
| 0.9, 0.6 | 0.85 | 11 | 0.00 | 0.68, 17, 0.0 |

The less sensitive detector helps on every measure: 6439 events instead of 9883, cleaner event boundaries
(event accuracy before the gate 0.77 → 0.89), and fewer small motions from talking reach the classifier.

What this shows, and what it does not (revised after an independent review, Gemini via `agy`):

- **False commands only.** The pair rule cuts false outputs from about 39 single motions to about 0.2 commands
  per hour (with quiet_scale 1.0: 120 → 1.5). They come from talking and walking (2/h while speaking, 1/h
  walking). About 60 % of the non-gesture files are cued face motions, not daily life, so this is not "random
  head movement".
- **Command recall is not measured.** EarSet has no two-motion commands (each file repeats one gesture), so
  "head gestures recognised" is single-motion recall. Do not plot it against false *commands* as if it were one
  operating point: the real trade-off curve (command recall vs false commands per hour) needs our cued commands.
  On EarSet, report false commands per hour against gate strength only.
- **Speed/size features help on new people within one device.** Adding magnitude features (still leave one
  person out, so the test person is unseen): event accuracy 0.89 → 0.95, false single motions 39 → 14 per hour
  (false commands 0.2 either way; with quiet_scale 1.0: accuracy 0.77 → 0.92, false commands 1.5 → 0.4). A
  likely reason: head gestures are much faster than face and talking motion (1.6-3.5 vs 0.27-0.69 rad/s), so speed
  separates *gesture from non-gesture* for everyone, even though it is person-specific *among* gestures.
- **Across devices they are unstable, not simply harmful.** Phase 0, nod / tilt / none, head frame: EarSet →
  AirPods 0.95 (axis) vs 0.85 (with speed/size), but AirPods → EarSet 0.80 vs 0.84. Nod vs tilt was 1.00 either way;
  the whole drop was in recognising "none" (0.96 → 0.70), where the two datasets' non-gesture data differ. So: use
  them, but normalised per person/device, and test both directions.

**Variance components in R** (`results/variance_components.md`, 2035 gesture events, 30 people, 95 % bootstrap
CI, quiet_scale 3.0): which-axis features are 90-98 % gesture and ≤ 6 % person + personal style; speed, size and
peak counts are 34-67 % person + style (with quiet_scale 1.0: 85-91 % and 30-56 %). Limits: only gesture events are modelled, so this answers "which gesture",
not "gesture or not" (where speed/size help); with three gestures on three different axes, the axis features'
high share is partly built in; direction features cannot be judged without direction pairs. The screening rule
(`r/SCREENING_RULE.md`) was written after seeing these EarSet results and is fixed before our own data.

**First real Mac + AirPods data** (`data/internal GG 01`, 1 person, 2026-11-07). Logistic regression trained only on
EarSet (30 people, other earbud), tested on this person's head-frame events: axis features **32/32 correct**
(nod / turn = shake / tilt). Adding signed + timing features drops to 0.84 (4 nods called "none"): those nods were
held at the bottom and split into half-nods, and EarSet has no direction pairs, so its signed-feature weights mean
little. In the head frame the first swing separates directions perfectly: tilt L 6/6 positive, tilt R 5/5
negative, turn L 7/7 positive, turn R 5/5 negative (first_lobe_y / first_lobe_z). One person: a sanity check, not
a result.

**First Gesture Collector app session** (P01, AirPods Pro 2, 6.3 min partial: calibration, practice, 2 rounds;
`results/p01_airpods_report.md`, `scripts/person_report.py`). The participant started 61 % of motions before the
GO beep (median −0.43 s), so for app v2.0 sessions motion windows open 1.5 s early, and the labeller now takes the
**largest** event in a window as the motion (`LabelConfig.pick`). With that: 28/29 motion cues found; all four
direction pairs separated by one sign (nod/look up 3/3 + 4/4, tilt 4/4 + 4/4, turn 3/3 + 3/3, circle loop_xz
3/3 + 4/4); EarSet-only model on axis features 21/21; within session (8 motions, leave one out) 26/28; earlier Mac
recording → app session (re-worn, 5 motions) 17/17. Weak spots: circle ccw (2/4, slow and small), motions repeated
inside one window (11 of 29 cues), and talking without a 'none' class (348 gated single gestures/h). One person.

**Simulated sessions** (`tests/test_end_to_end.py`): cue clock error about 50 ms; ≥ 90 % of single cued motions
found; quality checks pass; the cue log labels events correctly.

## Open problems (to settle on pilot data)

1. **Back-to-back motions**: in simulated commands only 50 % of the motions are found separately; two motions
   with a short pause merge into one event. `DetectorConfig.split_returns` (split where the head is back at its
   start pose and still) exists but is off: the simulation uses the old double gestures, which it rightly cuts
   in two, so it cannot be judged until we have single motions. Also try a shorter `end_s`.
2. **Signed features** (left/right, cw/ccw) cannot be screened on EarSet, which has no direction pairs. Phase 0
   showed they work on AirPods (tilt L/R 0.91, circle 0.94); confirm on pilot data.
3. **MiniRocket** needs `aeon`, which has no build for Python 3.15; run it from a Python 3.12 environment to compare.
4. **Live use**: the detector is causal and reports latency (about 0.4 s after the motion ends), but there is no
   live runner wired to the collector's HTTP stream yet.
5. EarSet cannot measure command *recall* (its files repeat one gesture); that needs our cued commands and the
   self-paced block.
6. Direction features on the old 4-person AirPods data: tilt L/R 0.52 → 0.94 and circle cw/ccw 0.54 → 0.97 when
   signed features are added (even on raw sensor axes). The stand-in calibration nods there (first 3 nod takes)
   assume everyone swung chin-down first, which was never checked; check it before quoting signed features.
