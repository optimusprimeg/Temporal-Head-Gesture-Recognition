# Our features, for the receiver code

One file: [`our_features.py`](our_features.py). It needs only numpy, pandas and scipy. It reads the same sample keys as `secret_receiver_*.py` (`rotX..`, `accX..`, `gravX..`). The numbers are identical to our pipeline (`ours/algorithm/gesturekit`, checked: max difference 0).

## The idea in 3 lines

1. **Turn the motion into head axes first.** Z = up (from gravity just before the motion). X = the person's nod axis (from 3 calibration nods). Y = the third axis. After this, "rotation about X" means a nod for everyone, whatever the earbud angle, ear, posture or device.
2. **Describe the shape, not the size.** Use the share of rotation about each head axis, how circular the path is, and the sign of the first swing. A small slow nod and a big fast nod give the same numbers, so they should carry over to a new person.
3. **No yaw / pitch / roll and no raw gravity means.** Those record where the person faced when the stream started and how the earbud sits. That is person, not gesture. In the 96 receiver features, 73 of 96 vary more with person + style than with gesture.

## Plug it in

Receiver (`classify_event`), in place of `extract_live_features`:

```python
from our_features import event_features, features_frame, rule_classify, calibrate_heading

heading = calibrate_heading([nod1, nod2, nod3])   # once per wear: 3 single nods, chin down first (optional)
f = event_features(samples, fs=50, heading=heading)
print(rule_classify(f))                           # no training needed: nod_down / tilt_left / ... / none
X = features_frame(samples, 50, heading, columns=FEATURE_LIST)   # or feed a trained model
```

Training (`train_model.py`): one `event_features(...)` row per take or event, then fit as before. Test with `GroupKFold(groups=subject_id)`, not `session_id`. Grouping by take puts the same person in both train and test.

## The features

Calibration column: whether the feature needs the 3 calibration nods. "gravity" means it works with gravity only, no calibration.

| Set | Feature | Meaning | Calibration | Person or gesture |
|---|---|---|---|---|
| core | `share_x`, `share_y`, `share_z` | share of rotation about the nod / tilt / up axis (sums to 1) | x, y: nods; z: gravity | gesture |
| core | `linearity` | 1 = one fixed axis; lower = circle or wobble | gravity | gesture |
| core | `abs_loop_xy/xz/yz` | how circular the rotation path is (1 = circle) | gravity | gesture |
| direction | `first_lobe_x` | + = chin down first (nod down vs look up) | nods | gesture |
| direction | `first_lobe_y` | + = tilt left first | nods | gesture |
| direction | `first_lobe_z` | + = turn left first | gravity | gesture |
| direction | `loop_xz` (and xy, yz) | + = clockwise circle | nods | gesture |
| timing | `rot_peaks`, `rot_peak_gap_s` | rotation-speed peaks and their spacing (single vs double) | none | mixed |
| timing | `acc_peaks`, `acc_peak_gap_s`, `acc_hf_rms`, `acc_hf_per_rot` | sharp acceleration without turning (taps, jaw) | none | mixed |
| magnitude | `peak_rot`, `rms_rot`, `duration_s`, `cycles_per_s`, `n_cycles`, `acc_per_rot` | speed, size, length | none | **person**: use with care |

Without calibration, `share_z`, `first_lobe_z` (turn L/R), `linearity`, `|loop|`, timing and magnitude still work. Nod vs tilt and their directions need the nods. If the default heading is off by θ, `sin²θ` of the rotation leaks between the X and Y shares: 20° gives 12% leak, 45° gives 50%.

The live rules (`rule_classify`) work like this:
- If the largest share is 0.6 or more, the motion is a nod, tilt or turn.
- Otherwise, if any |loop| is 0.15 or more, it is a circle.
- Otherwise it is none.
- The direction comes from one sign.

These thresholds were set on one person (P01). They are development values, not final.

## Test on the old AirPods takes (4 people, 938 takes, random forest, same as the receiver)

| Features | How many | Same person seen | New person (LOSO) | New P1 / P2 / P3 / P4 |
|---|---|---|---|---|
| receiver 96 | 96 | 0.88 | 0.60 | 0.81 / 0.50 / 0.54 / 0.56 |
| ours core + direction + timing, gravity only | 19 | 0.79 | 0.58 | 0.70 / 0.59 / 0.59 / 0.45 |
| ours core + direction + timing, 3-nod calibration | 19 | 0.77 | 0.57 | 0.68 / 0.59 / 0.53 / 0.46 |
| ours, all 25, 3-nod calibration | 25 | 0.80 | 0.61 | 0.76 / 0.66 / 0.53 / 0.49 |

All 8 old classes are included (idle, jaw single/double, tilt L/R ×2, nod ×2, circle cw/ccw). The 3 nod takes used for calibration are left out of the test.

**What this shows:**
- **On a new person, ours gives the same accuracy with a quarter of the features.** It does not beat the 96 here.
- **Ours memorises the person less.** The drop from seen to new is 0.19 for ours vs 0.28 for the 96.
- **The 96 do better only on the people already seen.** That is the person-dependent part.
- **Both are about 0.6 on a new person.** Per-soldier enrollment would hide this, and a demo with a new person would show it.

**Why ours is not higher on this data:**
- **The old takes are not clean single-axis motions.** Within one person, the axis of a nod varies by about ±25°.
- **"tilt left" and "tilt right" sit on different axes.** Subject 2: 31° vs 140°; they should be the same axis with opposite sign. So those tilts were partly nods or turns.
- **Calibration does not help here.** Calibrating from double-nod takes on this data is unreliable.
- **Every old gesture is a double.** Our pipeline is built for single motions, found by its own detector.
- **Jaw clench is about 10× weaker than head motion.** No head-motion feature helps it.

The real test is the pilot data: P02 onward, single motions, calibration nods, AirPods Pro 2 + AirPods 5.

## Not covered

- Jaw, face and other micro-gestures. On EarSet, only mouth stretch rises clearly above still noise. Wink left vs right is near chance from one ear.
- The detector (when an event starts and ends). Our causal detector is `ours/algorithm/gesturekit/detect.py`. The receiver's own START/KEEP/END detector works with these features as they are.

Data for the table: `prior_work/gesture_lab/data/raw/subject1-4.csv` (local only, not in git). Each take is used whole, gravity from its first 0.5 s, random forest with 300 trees.
