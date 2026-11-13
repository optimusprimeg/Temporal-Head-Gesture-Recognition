# Findings and intuitions (running log)

Everything we have learned so far, in one place, so it survives between chats. **Update this file whenever a new
result or insight comes in** (add a new F-number; edit an old one if new data changes it, and say what changed).

How to read each entry:
- **Seen**: the result, with numbers and where they come from.
- **Why**: our explanation (intuition, not yet proven unless stated).
- **Can claim / cannot claim**: what the evidence supports today.
- **Paper**: whether it goes into the report, and where.

Status labels: **SOLID** (several people/datasets, repeatable), **LIKELY** (consistent but small data),
**HINT** (1-3 people, direction only), **OPEN** (not tested yet).

---

## Where we stand (2026-11-13)

- **Data**: 9 people of older recordings, the EarSet public set (30 people, nod/shake/tilt), P01's app sessions,
  and the teammates' v5 collector files S03 (20 reps, AirPods 5), S8 (5 reps, AirPods Pro 2), S9 (micro only,
  about 5 reps, AirPods Pro 2). More v5 people are coming.
- **Tools**: teammates' `collector_v5.py` (Sensor Logger, 3 s takes, by-gesture blocks) and our Gesture
  Collector app v3.4 (Mac/iPhone, continuous stream, mixed rounds, `v5.json` = same 23 gestures + idles).
- **Main open question for the paper**: which micro-gestures work for a new person without training, which need
  a few personal reps, and how this changes as the number of training people grows (F12-F15).

---

## A. Problem framing (why the pipeline is built this way)

### F1. Clip accuracy hides the real problem: a live system must find gestures in a continuous stream. SOLID
- **Seen**: the old pipeline scored 0.72 on cut clips but found and named only 0.39-0.43 of gestures in a
  stream, with 6-16 false alarms/hour; sliding 2 s windows gave 130-240 false alarms/hour
  (`WHY_WE_CHANGED.md`, from prior_work `08_analysis_and_plan.md`).
- **Why**: a clip test only asks "which gesture?"; live use also asks "is there one?" and "where?".
- **Can claim**: clip accuracy alone overstates live performance. **Cannot claim**: our live numbers on new
  people (not measured at scale yet).
- **Paper**: motivation section.

### F2. Training on whole takes misses most live gestures; train on detector cuts. LIKELY
- **Seen**: stitched-stream test, 5 people: whole-take training finds 10-14 % of gestures, detector-cut training
  17-29 %, 0 false alarms/min of idle (`algorithm/results/stitched_stream_test.md`).
- **Why**: the live model sees what the detector cuts out, which is shorter and placed differently than a 3 s take.
  Train on the same kind of window you test on.
- **Can claim**: train/test window mismatch roughly halves recall. **Cannot claim**: absolute live recall
  (detector still misses most; quiet thresholds need tuning).
- **Paper**: method + limitations.

### F3. Block recording lets a model cheat on posture; mixed rounds remove it. LIKELY
- **Seen**: P01's app session with gestures in random mixed rounds: posture-only model 0.14 vs our features 0.88
  (`results/P01_s1_airpods5_20261113.md`). In block-recorded data a posture-only model scores much higher.
- **Why**: when all reps of one gesture are recorded together, the head sits slightly differently in each block,
  so "mean head angle" alone predicts the label.
- **Can claim**: our app's mixed rounds remove the posture shortcut. **Paper**: data collection design.

### F4. Single motions as commands fire constantly in daily life; doubles and a "none" class fix most of it. LIKELY
- **Seen**: P01: single head motions ~390 accidental fires/hour in no-gesture time; a trained "none" class + gate
  brings it to 0-29/hour. Tilt doubles never happened by accident, nod doubles did
  (`results/session_models_P01_airpods5_20261113.md`).
- **Why**: people nod and turn all the time; deliberate double tilts are rare.
- **Can claim** (one person): doubles of uncommon motions are safer commands. **Paper**: design of the command set.

### F5. Two motions back to back merge into one detected event unless there is a ~0.5 s pause. SOLID
- **Seen**: 84-89 % of real doubles (4 people) merged into one event; with a pause of 0.5 s or more about 9 in 10
  commands come out right (`results/pair_reliability.md`).
- **Why**: the detector needs ~0.4 s of stillness to end a motion.
- **So**: doubles should be recognised as one pattern (or with a split rule), and the app accepts 1 or 2 events
  for a double. **Paper**: method.

---

## B. Features and models

### F6. Direction-share features carry the gesture; magnitude/timing carry the person. SOLID
- **Seen**: EarSet (30 people), variance split per feature: share_x/y/z are 90-98 % gesture, ~0 % person;
  rms_rot, peak_rot, n_cycles, acc_hf are 26-44 % person (`results/variance_components.md`, R lme4).
- **Why**: everyone tilts in the same direction, but how hard and how fast is personal.
- **Can claim**: for head gestures, "which axis" is person-independent, "how strong" is not.
- **Paper**: feature design, a key figure. Explains F7 and F12.

### F7. Head gestures transfer to new people; our 25 features are best for them. SOLID
- **Seen**: all-data benchmark, new person (leave one person out): ours RF 0.92 vs teammates' 214 features 0.83 vs
  receiver 96 0.78 (`results/all_data_benchmark.md`). v5 two-person check: all 7 v5 head gestures 100 % within
  and 100 % across S03/S8 (F11). EarSet LOSO 0.98.
- **Can claim**: head gestures need no personal training. **Paper**: main result.

### F8. Rules without calibration fail; with a calibration heading they work. LIKELY
- **Seen**: rules 0.03-0.22 without calibration, 0.91 with it on P01; EarSet 0.61
  (`results/all_data_benchmark.md`, `session_models_*`).
- **Why**: rules need to know which way is "forward/down" for this person and earbud fit; the calibration nod
  gives that. This is why the app calibrates.
- **Paper**: method (why calibration exists).

### F9. Face/touch gestures: the teammates' features beat ours; combined is best overall. LIKELY
- **Seen**: on face/touch clips the receiver 96 features beat our 25; ours + 214 best overall (0.85)
  (`results/all_data_benchmark.md`).
- **Why**: our 25 features were designed for head rotation; face gestures are tiny vibrations and accelerations
  that the 96/214 statistics describe better.
- **So**: rerun feature selection per gesture family once all v5 data is in (planned).

### F10. Data quirks that silently break results (always check). SOLID
- Teammates' older collector files store gravity pointing UP (g units); the app, the Sensor Logger export and the
  new v5 collector files (S03/S8/S9) all store it DOWN in m/s² (checked 2026-11-13: app P01 gravZ -9.4, S03 -9.1,
  S8 -9.5, S9 -8.6). So app sessions and v5 files merge as they are; only the old collector files need the flip.
  Wrong sign flips left/right (rotate-left read 0/30 before the fix, 15/15 after).
- Earbud side: teammates record with the RIGHT AirPod only; left vs right flips tilt/turn signs. App v3.7 records
  either side (one AirPod) and logs it (`earbudSide`, `sensor_location`); check it before merging any session.
- **Retakes in app data (v3.1+):** when the app's check fails it asks for the trial again, and BOTH tries are
  "done" rows with the same block/round/motion (P01 pilot session: 11 of 91 gestures). `app_to_v5_csv.py` already
  marks the failed try `bad:` (its mismatch / count flag), so converted training data is fine; anything reading
  cues.csv directly must keep only the last try per trial. App v3.6 counted both toward targets (fixed in v3.7).
- Never open data CSVs in Excel and save (timestamps break).
- `app_to_v5_csv.py` before 2026-11-14 wrote an EMPTY `sensor_location` column (off-by-one in the copied
  columns). Re-convert any app session converted before that date. P06 (Yash, app v3.6) re-converted: LEFT bud,
  so its tilt/turn signs are mirrored vs the teammates' right-bud files.
- Some v5 gestures are ONE merged motion (rotate_*_chin_down, circles, jaw_shift_left_right, tilt_hold): never
  split or map them to single motions. Combos (X_then_Y) are two parts by design.

---

## C. The v5 gesture set and micro-gestures (teammates' data, 2026-11-13)

### F11. Full v5 set, two people (S03, S8): separable within a person, only head gestures transfer. HINT
- **Seen**: RF on 27 classes, within-person 0.86-0.88 (S03, 20 reps) and 0.73-0.78 (S8, 5 reps); train on one
  person, test on the other: 0.32-0.37. Head gestures 100 % both ways; face and combo gestures mostly 0 % across
  people, often predicted as `molar_tap_2x` (`scripts/v5_two_person_check.py`).
- **Also**: `idle_talk` 0-10 % and `idle_chew` 25-50 % within person, mistaken for face gestures, so talking or
  chewing could trigger face commands.

### F12. Micro-gestures: separable within a person, mostly personal across people. HINT (3 people)
- **Seen**: 15 face/combo gestures + idle still/swallow (18 classes, chance 6 %), S03 + S8 + S9
  (`scripts/micro_transfer_study.py`). Within person per gesture 0.65-0.97. New person 0.30.

| Group | Gestures (score on a new person, LOPO) |
|---|---|
| Transfers | idle_still 0.85, smile_2x 0.70, molar_tap_2x 0.61 |
| Partly | jaw_left_then_eyebrow 0.42, eyebrow_up_down_2x 0.40, jaw_shift_left_right 0.34, jaw_right_then_eyebrow 0.33 |
| Personal | mouth_open_2x, puff_cheeks_2x, jaw_clench_double, jaw_forward_2x, combos with mouth/puff (0.00-0.25) |
| Not separable even within a person | none |

- **Why (intuition)**: on a new person most errors go to `idle_swallow`: their gesture is weaker than what the
  model learned from others, so it looks like "almost nothing". The person changes the strength, not the shape,
  of the signal: the same story as F6 for head gestures, but for micro-gestures the shape signal is too weak
  to carry the decision on its own.
- **Cannot claim yet**: which gestures are person-independent in general (needs many more people).

### F13. More training people -> better on a new person (the "N curve"). HINT
- **Seen**: train on 1 other person -> 0.21 on a new person (range 0.13-0.35); on 2 -> 0.30 (0.23-0.39), averaged
  over every combination.
- **Intuition (user's plan)**: as N grows, the model sees enough different "styles" that a micro-gesture becomes
  person-independent. Plot accuracy vs N per gesture: gestures whose curve climbs high = person-independent;
  flat curves = need personalisation.
- **Cannot claim yet**: that it reaches a high level, or where it levels off. Only 3 points now; needs the full
  group (aim 15-20+ people). Do not state "20+ people" until they are recorded.
- **Paper**: main figure (curve A) once data is in.

### F14. A few personal reps recover most of it. HINT
- **Seen**: all other people + k reps of the new person per gesture: k=0 0.30, k=1 0.50, k=2 0.64, k=3 0.66.
- **Contrast**: on EarSet head gestures, personal reps add almost nothing (0.958 -> 0.973,
  `results/enrollment_curve.md`), because head gestures already transfer.
- **Can claim (direction)**: micro-gestures need a short personal calibration (~2-3 reps); head gestures do not.
- **Paper**: curve B (accuracy vs own reps), next to curve A.

### F15. Rescaling each person's features to their own range helps a bit, with no labels. HINT
- **Seen**: z-score each person's features over all their clips (no gesture labels needed): new-person accuracy
  0.30 -> 0.37 (ours + 214), 0.22 -> 0.29 (receiver 96).
- **Why**: removes the "how strong" difference (F6, F12) partly. A real system could do this from a minute of the
  person's normal use.
- **Paper**: a cheap personalisation method to compare with F14.

### F16. Swapped-order combos are hard to tell apart. HINT
- **Seen**: eyebrow_then_mouth_open vs mouth_open_then_eyebrow confuse each other even within one person
  (S8: 0.20), and across people they are near 0.
- **Why**: the parts are tiny and the order is only a ~1 s timing difference.
- **So**: either drop one of each swapped pair or treat the pair as one command.

---

## D. Data value

### F17. One person's extra data barely helps others; its value is as test data. LIKELY
- **Seen**: adding P01's 191 app clips changed the other people's leave-one-out accuracy by about +0.01
  (`results/ablation_p01.md`). Train on P01 only -> others 0.69; train on others -> P01 0.95.
- **So**: more different people help (F13) far more than more reps from the same person. New people also give
  live and false-trigger measurements.

---

## E. Ideas to test (OPEN)

- Curve A at full N, per gesture, with confidence intervals (bootstrap over people).
- Curve B (0, 1, 2, 3, 5 own reps) for each gesture family; compare with F15 normalisation.
- Feature selection per family (head / face / combo) with leave-one-person-out ranking.
- Does the merged rotate_*_chin_down behave as one class in live detection (1 or 2 events)?
- Double-pattern rule (two same singles within gap X) vs a window model for 2x gestures.
- Idle talk/chew false triggers for face commands, measured per hour on long idles.
- Head turn vs whole-body turn (gravity/heading) as a confound.
- **Left vs right earbud (2026-11-13):** teammates recorded RIGHT only; P01's right AirPod died, so P01's new app
  sessions are LEFT. Test: train on right-ear people, test on left (and back), raw vs head-frame features vs
  mirrored signs. Never merge sides blindly; keep `sensor_location` as a variable. Outcome = "works with either
  ear" or "needs a per-side model".
- Our extra gestures (smirk, tongue, earlobe, sniff, cheek/chin tap): keep only if a small pilot shows them
  clearly separable (few trials, every 3rd round in `v5_plus.json`).

---

## Change log
- 2026-11-13: file created from all work so far (F1-F17).
- 2026-11-13: F10 updated (gravity convention checked across app and v5 files; earbud side rule).
- 2026-11-14: F10: retakes in app data; earbud side now logged, not required (app v3.7).
- 2026-11-14: F10: converter sensor_location bug fixed; P06 converted to v5 format (dataset_P06.csv).

## Experiment-side notes (what the app records for the paper, v3.5-3.7)
- `feedback.json` per session: easy-to-do and OK-in-public (1-5) per gesture group + the hardest gesture in the
  participant's words -> a usability column next to accuracy.
- "Confused?" clicks (notes.csv) and experimenter "marked_wrong" rows (cues.csv) -> which gestures are hard to
  understand vs hard to perform.
- v3.7 optional scene video (consented people only): `scene_NNN_frames.csv` puts every video frame on the cues.csv
  clock, so `scripts/cut_scene_clips.py` cuts one clip per trial -> label checks by eye ("did they really do X?"),
  real demo clips for later pilots instead of online GIFs, and a figure of how each micro-gesture looks.
- Good reps per person are counted per planned trial (last try counts), per AirPods model, per experiment family
  (v5 + v5_plus); "can't do" is remembered per person -> report it as a per-gesture "could not perform" rate.
