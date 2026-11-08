# Phase 0: what existing data tells us before we record

Data: EarSet (30 people, custom in-ear IMU, left ear, 2 min per motion; notes `../data/external/EARSET_NOTES.md`)
and our old AirPods Pro 2 takes (4 people, `../../prior_work/gesture_lab/data/raw`). Full numbers in `results/*_report.md`.

**Revision 2026-11-06 (after two independent reviews, Sonnet 5.5 and ByteAsk):** fixed the AirPods acceleration
unit (m/s², was treated as g), the bout detector's quiet level (now from the person's own still recording, so
walking/chewing are no longer hidden), false alarms per hour (now divided by the hours actually recorded), the
loop feature (now a closed path), and the hard-case headline (one setup fixed by rule instead of the best cell
of a 12-cell grid). All numbers below are after these fixes.

## Run

```
python build_bouts.py   # EarSet -> results/bouts.csv + recordings.csv, ~2 min
python analyse.py       # -> results/phase0_report.md
python airpods.py       # old AirPods data -> results/airpods_bouts.csv
python crossdevice.py   # EarSet <-> AirPods -> results/crossdevice_report.md
python hardcases.py     # tilt L/R, circle cw/ccw, jaw on AirPods -> results/hardcases_report.md
```
Needs numpy, pandas, scipy, scikit-learn, tabulate.

| File | What |
|---|---|
| `earset.py` | load a file: sort by time, split at time gaps, convert units, resample to 50 Hz |
| `segment.py` | cut a recording into bouts above the person's still level (variable length, long runs split at 12 s) |
| `frames.py` | R0 sensor axes, R1 gravity frame, R2 head frame (gravity + axis of 3 calibration nods), signed variant |
| `features.py` | 10 unsigned features + 6 signed + 6 timing features per bout |
| `build_bouts.py`, `analyse.py`, `airpods.py`, `crossdevice.py`, `hardcases.py` | the pipeline above |

## Findings

**1. Head frame helps, most for the hardest people (H1).** EarSet, leave one person out (29 → 1), logistic
regression on 10 features:

| frame | nod/shake/tilt | worst person | + "none" class | worst person | non-gestures called a gesture |
|---|---|---|---|---|---|
| R0 sensor axes | 0.95 | 0.71 | 0.92 | 0.76 | 8 % |
| R1 gravity only | 0.91 | 0.56 | 0.93 | 0.81 | 6 % |
| **R2 head frame** | **0.97** | **0.82** | **0.95** | **0.82** | **6 %** |

- R2 vs R0, paired over 30 people: 3 classes +0.02 (9 better, 3 worse, p = 0.14, not significant);
  4 classes +0.02 (21 better, 7 worse, p = 0.001). Six comparisons were run; uncorrected p-values.
- Within one device and one lab, raw axes are already good. The head frame's value is robustness: the gain is
  concentrated in a few badly fitting people (Sonnet review: correlation of R0 accuracy with gain −0.79), and it
  matters most across devices (finding 5).
- Gravity alone (R1) is worse than raw axes: it throws away heading, so nod and tilt mix. The calibration nods are
  what make it work.
- Caveat: R2's X axis is defined by the person's own nods, so "nod rotates about X" is partly true by construction
  (share_x 95 % gesture / 1 % person is inflated for that reason).

**2. Speed, size and repeat count belong to the person, not the gesture.** Variance share in the head frame:
which-axis features 89-95 % gesture, 1-5 % person; duration, number of cycles, cycles per second, peak speed:
60-71 % person, 6-26 % gesture. So gestures must differ by axis and direction, not tempo or count; single vs
double is the risky kind of difference; use speed/size only after per-person normalisation.

**3. Face gestures are weak and talking-like.** Peak rotation: head 1.6-3.5 rad/s, face 0.27-0.49, talking 0.69.
Face motions produced only 3-10 bouts per person against ~24 cues (mouth-stretch 22, but it is not covert).
→ No face gestures in the vocabulary.

**4. False messages (H6), offline estimate.** With "none" trained on talking, walking, running, chewing and face
motion, about 6 % of non-gesture bouts become a message. Per hour of each activity (single motions, no pair rule):
talking 38, brow/mouth face motions 24-36, running 17, walking 14, chewing 1. These are offline: bouts are cut from
whole recordings and continuous motion is split into 12 s pieces, so walking/running/chewing are lower bounds.
→ A gate (pair rule, confidence threshold, negatives in training) is still required; a live test is the real measure.

**5. Cross-device: EarSet-trained model on AirPods** (`crossdevice.py`), classes nod / tilt / none:

| features, frame | EarSet (30) → AirPods (4) | AirPods → EarSet | AirPods only, LOSO |
|---|---|---|---|
| all 10, R0 sensor axes | 0.80 | 0.67 | 0.92 |
| all 10, R1 gravity | 0.79 | 0.77 | 0.92 |
| all 10, R2 head frame | 0.85 | 0.84 | 0.94 |
| **axis features only, R2 head frame** | **0.95** | 0.80 | 0.94 |

- With axis features in the head frame, a model trained only on another earbud reaches 0.95 on AirPods people.
  Adding speed/size features gives 0.85 in that direction but *helps* in the other (AirPods → EarSet 0.80 → 0.84).
  Nod vs tilt is 1.00 either way; the whole drop is in recognising "none" (0.96 → 0.70), where the two datasets'
  non-gesture data differ (EarSet: face and daily-life motion; AirPods: idle takes). So speed/size are unstable
  across devices and protocols, not simply harmful. (Corrected after review; the earlier "costs 10 points" was
  one direction only.)
- Raw axes look fine for nod vs tilt alone (0.99) by luck: both earbuds put nod about their X axis. With a third
  class they drop to 0.80. A different mounting could break them; R2 does not depend on it.
- After the unit fix, acceleration per unit rotation matches across devices (nod 0.21 vs 0.21, tilt 0.25 vs 0.24).

**6. Hard cases on AirPods** (`hardcases.py`, 4 people, LOSO). Headline setup fixed by rule: signed head frame,
16 features without speed/size (`+timing`). The full 3 frames x 4 feature-set grid is in the report, exploratory.

| task | accuracy | key feature (gesture / person share of variance) |
|---|---|---|
| tilt left vs right | 0.91 | direction of the first swing about the roll axis (86 % / 2 %) |
| circle cw vs ccw | 0.94 | loop direction in the x-z plane (67 % / 4 %) |
| jaw (any) vs idle | 0.68 | rotation size, vertical-axis share (24-30 % / 2-6 %) |
| jaw single vs double | 0.54 (chance 0.50) | nothing: every count/timing feature under 10 % gesture |
| 6 classes, no jaw | 0.87 | |
| 7 classes, jaw merged | 0.76 | |
| 8 classes | 0.69 | MiniRocket on the same data: 0.72 (its test set also includes the 3 calibration nod takes) |

- Direction pairs are solved by signed features. Within one device, raw axes with signed features do just as
  well (tilt 0.94, circle 0.97 in the grid): the device's own axes already have a fixed sign. The signed head frame
  is needed for other devices and other mountings.
- Interpretable features are within a few points of MiniRocket (0.69 vs 0.72). With 4 people this is "close",
  not "equal".
- Jaw is the main source of errors; single vs double jaw is at chance.

## Caveats

- **Offline segmentation**: bouts are cut using whole recordings, so all accuracies assume a good detector; they do
  not test a live, causal detector on a mixed stream. That needs our continuous recordings.
- EarSet: one custom device, one lab, only 3 head gestures each about a different axis, no left/right, no doubles,
  no circles, no jaw. Cue count per file (~24) is read from plots, not stated by EarSet.
- AirPods: 4 people, one device, cued 2.5 s takes, no calibration block (first 3 nod takes stand in). Subjects 1 and
  4 have Excel-damaged timestamps, so 50 Hz is assumed for them.
- Gravity before a bout is taken from the 0.5 s before it; for 31 % of AirPods takes that window is too short and
  it falls back to the start of the motion (median error 0.4°, 95th percentile 6°).
- Statistics: few people, uncorrected multiple comparisons; treat p-values as descriptive.
