# Experimental design (draft v0.1, 2026-11-06)

Goal: record **once**, in a way that lets us compare all the algorithms we care about and test our hypotheses,
so we do not have to go back to the participants. Everything below is a proposal for discussion.

---

## 1. Hypotheses (what the data must be able to test)

| # | Hypothesis | Needs from the data |
|---|---|---|
| H1 | Rotating every gesture into a calibrated **head frame** removes most person, posture and device bias: features vary much less between people/devices than between gestures. | calibration at session start, several people, both devices on the same people, takes done with the head already tilted |
| H2 | A **compositional vocabulary** (few primitives, commands = short sequences) reaches high command accuracy on a new person **without** personal training. | primitive takes + recorded command sequences, many people |
| H3 | **Variable-length** event detection beats fixed windows, for gestures lasting 0.5 to 4 s. | continuous stream, gestures at slow / normal / fast speed |
| H4 | **Small (covert)** versions of the gestures keep most of their accuracy. | small-size takes of every primitive |
| H5 | A few **physics features chosen by statistics** (gesture effect large, person effect small) generalize to new people as well as a learned model (MiniRocket). | same as H1, enough people for mixed models (≥ 15) |
| H6 | False alarms in normal life stay under N per hour. | 8-10 min of no-gesture activity per session |

## 2. Algorithms the data must support

| Algorithm | Role |
|---|---|
| Detector (rotation + acceleration hysteresis) → resample → MiniRocket | strong learned baseline |
| Detector → physics features (R-selected) → LDA / logistic regression | our interpretable model (H5) |
| Detector → DTW 1-NN on enrollment templates | personalization baseline |
| Streaming: subsequence DTW (SPRING) or leaky ESN | detector-free comparison (H3) |
| Primitive classifier + sequence decoder (timing grammar, HMM/Viterbi) | command level (H2) |
| Normalisation variants: none / gravity-only / full head frame / per-session z-score | H1 |

## 3. Vocabulary: primitives, not 20 separate gestures

Decided: 6-8 **single** motions (no doubles, no counting); commands = ordered pairs (first, then); 6 motions give
36 pairs, minus same-same and natural pairs, keep the 20 most distinct. A lone motion times out (~1.5 s) and is
discarded.

Two rounds:
1. **Pilot (the 5 of us, `collector_v3.py --plan pilot`)**: 9 candidate single motions: nod down, look up,
   tilt L, tilt R, turn L, turn R, circle cw, circle ccw, jaw clench; plus small and slow versions and
   back-to-back pairs. Keep a candidate only if: (a) separable from the others on a left-out person, (b) rare in
   the no-gesture block, (c) small version still works, (d) splits cleanly from the next motion.
2. **Freeze** the motions and the 20 pairs (`collector/config.py`: MAIN_MOTIONS, COMMANDS), then the main round.

## 4. Participants

| Group | n | Role |
|---|---|---|
| Us (team) | 5 | pilot + main; analysed separately too, since we know the gestures too well (expert bias) |
| Others | 15 | main round; **main results reported on these** (naive users) |

Record heterogeneity on purpose and write it down (session.json): sex, age band, glasses, long hair over the ears,
ear tip size, dominant hand, AirPods experience. Aim for a spread, not a quota.

Unit of analysis is the **person**: all accuracy claims are leave-one-person-out.

## 5. Devices: 2×2 crossover

Each person does **two sessions on different days**, one per device. Half the people do Pro 2 first, half the
other device first (assigned at random, balanced). This separates the device effect from the day/practice effect
(standard AB/BA crossover). Mid-session the AirPods are taken out and put back once (re-wear effect).

TODO: confirm the second device's model, its sample rate and axis convention (first recording: 1 min still + 3 nods
on both devices, compare).

## 6. One session (one device; `collector_v3.py --plan main`, see `collector/config.py`)

Continuous recording the whole time; a cue log says what was asked and when. Gestures are **not** cut by a timer:
the cue opens a window, the person performs at their own pace, labels come from the cue + detector.
One cue takes about 9 s (0.8 s ready, beeps, 4 s window, random 2.5-5 s gap); a round = every motion once + idle
twice, so 10 cues ≈ 1.5 min with 8 motions (≈ 1.2 min with 6).

| Block | Content | Time (8 motions) |
|---|---|---|
| Setup | metadata, fit check, stream at 50 Hz | 3 min |
| Calibration | still 4 s, 3 nods (chin down first), look left then right | 0.5 min |
| Enrollment | 3 rounds, slow and clear (never used as test data) | 4.5 min |
| Main rounds A | 8 rounds, sitting, random order | 12 min |
| Re-wear | take out, put back, calibrate again | 1 min |
| Main rounds B | 8 rounds, sitting | 12 min |
| Posture | 2 rounds standing, 2 walking in place, 2 with head already tilted/turned | 9 min |
| Speed / size | 1 round slow, 1 fast, 1 small (covert) | 4.5 min |
| Commands | 10 cued two-motion commands | 2 min |
| Self-paced | 2 lists of 5 commands, no beeps, own pace | 2-3 min |
| Negatives | no gestures: talk 2, listen and nod along 1, chew 2, drink 1, walk 1, phone 1 | 8 min |
| Breaks | every 5 rounds | 3-5 min |

Total ≈ 60 min with 8 motions, ≈ 50 min with 6 (cue time measured in simulated dry runs: 52 min for 8 motions,
without setup and breaks). If 8 motions survive the pilot, cut main rounds to 7 + 7.

Per motion per person: 3 enrollment + 16 sitting + 6 posture + 3 speed/size = **28 per session, 56 over two
sessions** (32 plain sitting). With 20 people and 6 motions: about 6,700 gesture takes, 400 cued + 400 self-paced
commands, about 5 h of negatives.

## 6b. From recording to labels (time is never fixed for the motion)

Recording is continuous (`collector/collector_v3.py`). The cue fixes only **when to start looking**; how long
the motion takes is free and is measured by the detector.

0. Put cues and samples on one clock. Sensor Logger sends samples in batches, so a sample's PC arrival time
   (`host_ns`) is late by up to one batch. Use the phone clock: each cue row has `sensor_ns_est` = cue time
   converted with the stream's clock offset (minimum of host_ns − sensor_ns, i.e. the fastest-arriving batch).
   Cue times are taken at the **start** of the GO beep.
1. Run the motion detector over the whole stream (head frame). It fires on everything: gestures, scratching,
   talking. Its quiet level comes from the calibration still pose (Phase 0: a per-recording quiet level hides
   continuous motion such as walking and chewing).
2. Match each detected event to the cues:
   - event **starts** within [GO beep, GO beep + 4 s] of a motion cue -> that motion. It may **end** after the
     window (slow gestures); events longer than 4 s are flagged.
   - event in an idle cue's window, in a gap, or in the no-gesture block -> `none`
   - event starting within 0.5 s of a motion window's edges but not inside -> ignored (half motions)
3. QC: motion cue with no event -> dropped (missed); two events -> flagged and plotted; ~10 % checked by eye.
4. Reaction time (beep -> motion onset) and motion duration are recorded per take, so speed is measured, not
   imposed. Speed variation is also requested explicitly (slow, fast blocks) and the random 2.5-5 s gaps stop
   people from falling into a rhythm.
5. Self-paced block: no beeps, only the order of 5 commands is known. Scored at sequence level (commands found,
   in order, edit distance), the closest test to real use.

Data sets cut from one session: calibration (head frame only), enrollment (personalisation only, never test),
gesture/none events (classifier), full streams with per-sample labels (detector, false messages per hour),
commands + self-paced (decoder). All splits are by person, device or session, never by take.

## 7. Factors (for the R analysis)

| Factor | Levels | Type |
|---|---|---|
| person | 20 (15 naive + 5 team) | random |
| motion | 6-8 (after pilot) | fixed, within |
| device | Pro 2, newer Pro | fixed, within (crossover) |
| period (session order) | 1, 2 | fixed, within |
| wear | before / after re-insertion | fixed, within |
| condition | sitting, standing, walking, pre-tilted head | fixed, within |
| speed / size | slow, normal, fast, small | fixed, within |
| round | 16 per session (sitting) | blocking factor |

Randomisation: order of motions inside every round is random; gap length random 2.5-5 s; device order balanced.

## 8. Analysis plan

1. **Feature screening (R)**, inside each leave-one-person-out fold:
   `feature ~ primitive + (1 | person) + (1 | person:primitive) + (1 | device)`; keep features with a large
   gesture effect relative to person + style and device variance. Rule fixed in `algorithm/r/SCREENING_RULE.md`
   (v2): run over all motions **and** per confusable pair (tilt L/R, turn L/R, circle cw/ccw), ≥ 500 bootstrap
   draws for the paper. It judges "which gesture" only; gesture-vs-none features (speed/size) are judged by the
   person and device tests in step 2. Pairwise separability matrix between primitives.
2. **Classifiers** (Python): accuracy on a new person, a new device (train on one, test on the other), a new session.
3. **Streams**: events found and named, false alarms per hour (negatives block), latency.
4. **Commands**: command accuracy, commands per minute.
5. **Statistics (R)**: `correct ~ method * device + condition + (1 | person)` (logistic mixed model);
   McNemar between pairs of methods; report effect sizes with confidence intervals.

## 9. Before any recording (can do now, from home)

- Phase 0 on existing data: our 4 old subjects + the public EarSet dataset (30 people, nods/tilts/shakes,
  6-axis IMU in both ears, custom earbud; https://zenodo.org/record/8142332). Use it to try the feature screening
  and the head-frame idea before we record.
- Write `collector_v3.py`: continuous stream, shuffled rounds, audio cues, cue log, session.json.
- Write the QC script (sample rate, gravity, cue coverage, direction sanity).

## 9b. Phase 0 results that change this design (`phase0/README.md`)

(Numbers revised 2026-11-06 after two independent reviews; see `phase0/README.md`.)

- Calibration nods are essential, not optional: head frame 0.97 vs gravity-only 0.91 (raw axes 0.95) on new people,
  worst person 0.82 vs 0.56 (0.71). Keep them at start and after every re-wear; consider 5 nods instead of 3.
- Primitives must differ by rotation axis/direction, not by speed, size or repeat count (those are mostly person).
  Single vs double needs timing rules or enrollment; test it explicitly in the pilot.
- Drop face gestures (brow, wink, eyes, lip, chin) from the candidate pool: weaker than speaking.
- Cross-device: trained only on EarSet (other earbud), the head-frame model with axis features gets 0.95 on AirPods
  people for nod / tilt / none (raw axes 0.80; head frame with speed/size features 0.85, but 0.84 vs 0.80 *with*
  them in the other direction; the difference is all in the "none" class, whose data differ between the two).
  So public data can be pooled with ours in the head frame, using axis/direction features; speed and size
  only after per-person/per-device normalisation. Within one device they help on unseen people (EarSet: false
  commands 1.5 → 0.4 per hour), mainly by separating gestures from talking and face motion.
- EarSet cannot measure command recall (no two-motion commands in it); its pair-rule result is false commands
  only. The recall vs false-commands trade-off curve needs our cued commands.
- Hard cases (AirPods, 4 people, fixed setup): direction pairs work with signed features (tilt L/R 0.91, circle
  cw/ccw 0.94). Jaw single vs double is at chance (0.54) and jaw vs idle only 0.68. Proposed primitive pool:
  nod, tilt L, tilt R, circle cw, circle ccw, plus turn L/R and look up to test in the pilot; at most one jaw
  primitive, and only if the pilot shows it survives talking. The calibration nod must define the sign of the
  head frame (first swing = chin down), so instruct it the same way for everyone.
- Negatives: with talking, walking, chewing and face motion in training, about 6 % of non-gesture bouts still
  become a message: about 38 per hour while talking, 14-17 walking/running (offline, single motions, no pair rule;
  lower bounds; the earlier 127/h was wrong: the detector hid continuous motion and the exposure was miscounted).
  Realistic negatives in training are what keep it down, so the negative block is essential; add "talking while nodding along"; the pair rule and a confidence threshold come on top.

## 10. Decisions (2026-11-06)

- 20 **commands**, each an ordered pair of single motions (first, then); a lone motion times out after ~1.5 s
  and is discarded. No double gestures, no counting.
- 2 × 50 min per person is fine for the 15 others.
- R 4.6.1 is installed at `C:\Program Files\R\R-4.6.1\bin` (not on PATH); lme4 available.
- Recording changes from timed cut takes to continuous recording + cue log (below).

## 11. Open questions

- Exact second device model; does Sensor Logger expose the same 16 channels at 50 Hz on it?
- Is a 1-2 min personal enrollment acceptable in the final system?
