# Experimental design (v3, 2026-11-08)

The current design. It replaces the first draft (`archive/experimental_design_v0.md`, 2026-11-06), which
described a 60-minute collector-v3 session. The protocol itself is the experiment file `pilot.json` (built into the
Gesture Collector app, `mac_app/GestureCollector/Sources/Plan.swift`). This document explains what it collects,
why, and how it will be analysed. Changes from the independent review of 2026-11-08 are marked **(review)**.

## 1. Research question and hypotheses

Can a team member send silent commands with small head motions picked up by ordinary AirPods, recognised on a
continuous stream, for **new people and new devices without per-person training**, with few false commands?

| | Hypothesis | Main measure | Data |
|---|---|---|---|
| H1 | The **head frame** (gravity + 3 calibration nods) removes most person, posture, fit and device differences | accuracy with vs without the head frame, across people (leave one person out) and across devices (both directions) | core sitting rounds, both devices; module A (re-wear), C (posture) |
| H2 | **Commands built from two motions** reach high accuracy on a new person without personal training | command accuracy on unseen people | core commands + own-pace list; modules D, E |
| H3 | **Finding motions of any length** beats fixed windows | events found and named + false alarms per hour, detector vs 2.5 s windows on the same stream | continuous stream; module B (slow / fast); module E (set pauses) |
| H4 | **Small, covert** motions keep most of their accuracy | accuracy against the measured angle of each trial | core small rounds; module B |
| H5 | A few **statistically chosen physics features** transfer to new people as well as a learned model | leave-one-person-out and cross-device accuracy, ours vs MiniRocket vs the old random forest | everything; ≥ 15 people for the mixed models |
| H6 | **False commands** in normal life stay rare | false commands per hour per activity (with a confidence bound) | no-gesture blocks; modules D (walking), F (daily life) |

Secondary: the **enrollment curve** (accuracy with 0-5 of a person's own trials), the shortest **pause** that keeps
two motions apart, **body turn vs head turn** while walking, and **covertness** (can observers tell a command was
sent; command size vs everyday movement).

## 2. Vocabulary

8 single motions (nod down, look up, tilt left/right, turn left/right, circle cw/ccw), each one smooth go-and-return.
A command is an ordered pair of two **different** motions; the second must start within 1.5 s after the first ends.
The 20 commands are placeholders until the pilot: the final 20 are the pairs everyday movement produces least
often (measured on the no-gesture recordings), avoiding same-family pairs where possible (tilt L → tilt R stays on
one axis and needs a pause). If circles stay the weakest motion, the 6 one-axis motions still give 30 pairs.

## 3. Participants and devices

- **20 people**: 5 team members + 15 others. Numbers come from a shared team sheet because every phone and Mac keeps
  its own roster. **P01 (the developer) is development data only** **(review)**: settings were tuned on P01.
- **Devices**: AirPods Pro 2 and AirPods 5, each person on both (crossover: odd numbers start with the Pro 2, even
  with the AirPods 5). Recording on a Mac or an iPhone (same app, same files); the platform is logged.
- Where a person has only one model, the device is confounded with the person for them; this is logged and those
  sessions are left out of the device-transfer analysis.

## 4. One session (Pilot v3)

| Part | Content | ≈ min |
|---|---|---|
| Setup | device check; calibration (4 s still, 3 nods chin down first, look left/right/front); practice 2 per motion (1 later) | 5 |
| Core | enrollment 2 rounds; sitting 6 rounds; no gestures (1); small 2 rounds; 10 commands; 5 commands at own pace; no gestures (2) | 28 |
| Optional modules | A re-wear, B speed and size, C posture, D walking, E pairs and pauses, F daily-life no-gesture; G extra rounds fill leftover time | 5-8 each |

A round = all 8 motions + 2 "nothing" cues in random order, random 2.5-5 s gaps. Each cue: the motion is shown and
spoken, a GO beep, a 4 s window (6 s for commands), a live one-motion check shown to the participant (feedback only,
never a forced retake). Commands are instructed with **a short still pause between the two motions** **(review)**.

Planned in the experiment file:
- **Counterbalancing (review):** sitting and small rounds swap order by participant number; no-gesture time is
  split into an early and a late block (8 min in total, up from 5).
- **Module order:** Williams Latin square over A-F by participant number (re-wear never last). **Re-wear or posture is
  required** for everyone **(review)**, so H1's robustness is tested on all participants.
- **Per-device tracking (review):** optional modules are tracked per AirPods model, so a module is not done on only
  one device.
- **Time budget:** the core is never cut; modules are added only whole and only if they fit. About 33 min for setup +
  core **(review: not 25)**; 60 min recommended.
- A session that is interrupted resumes after recalibration; a trial disturbed by an earbud switch or data gap is
  repeated and flagged.

## 5. Labels

The detector (the same one used live) finds events in the stream; the cue log names them. A motion window opens
0.3 s before the motion is announced and closes 4 s after GO; the largest event in a window is the motion, smaller
ones are "extra". No-gesture blocks and "nothing" cues give "none". Calibration, practice, re-wear steps, and cues
marked skipped or disturbed are excluded from training. **Failed or disturbed trials are never dropped from the
evaluation** **(review)**.

## 6. Analysis plan

All settings (detector, labeller, feature definitions, rules) are **frozen with a git tag before P02** **(review)**.

1. **Feature screening (R, lme4).** `feature ~ motion + (1 | person) + (1 | person:motion)` on z-scored features,
   device as a **fixed** effect on main-round data **(review: 2 levels cannot be a random effect)**, ≥ 500 bootstrap
   draws. Keep rule (`algorithm/r/SCREENING_RULE.md`): gesture share ≥ 0.30, ≥ 2 × (person + style), and its lower
   CI above the upper CI of person + style. Run over all motions **and per confusable pair** (tilt L/R, turn L/R,
   circle cw/ccw); refit inside every cross-validation fold. Today only the three axis shares pass (on EarSet).
2. **Recognition.** Leave-one-person-out and cross-device (Pro 2 → AirPods 5 and back). Methods on the same splits:
   ours (Rules and Model), MiniRocket, the old random forest on 96 statistics, DTW. Ablations: head frame on/off,
   feature sets, detector vs fixed windows.
3. **Streams.** Events found and named, false alarms and false commands per hour per activity; with zero events,
   report the upper bound (rule of three: total no-gesture hours give the bound) **(review)**.
4. **Commands.** Command accuracy on unseen people, by pause length and condition (sitting, walking); latency.
5. **Statistics.** `correct ~ method * device + condition + (1 | person)` (logistic mixed model), effect sizes with
   confidence intervals. **No McNemar** (trials are clustered within people) **(review)**.
6. **Enrollment curve.** Train on others + k of the person's own early trials (k = 0..5, from the enrollment and first
   sitting rounds), test on their later rounds.
7. **Covertness.** Observers judge short clips (some with a command, some without): detection accuracy vs chance
   (d′). From the data alone: command angle, speed and duration vs everyday movement.

## 7. How the protocol changes over time

Changes are made **only between stages**, by editing the experiment file (no app rebuild); every session saves the
file it ran (`experiment.json`) and its version.

| Stage | Who | Experiment file | Decides |
|---|---|---|---|
| 0 (done) | EarSet, earlier 4-person data, P01 Mac recordings | n/a | pipeline, head frame, feature screening, detector settings |
| 1 | P01 self-test, data read live on the analysis PC | `selftest.json` | shortest pause, axis-change cut, walking cues |
| 2 | Pilot, P02-P06, 2 sessions each | `pilot.json` (Pilot v3) | final motions and 20 commands, enrollment rounds, module changes |
| 3 | Main round, 20 people | `main.json` (made from the pilot, then **frozen**) | the paper's results |

## 8. Known limitations

- P01 numbers are development numbers; EarSet "style" absorbs wear and fit (one recording per person and gesture).
- Direction features (left/right) are supported by physics and P01's few trials, not yet by the R rule (EarSet has no
  direction labels).
- No-gesture time is acted and seated except modules D and F; real-life false commands need longer timelines.
- Walking is indoors and slow; running, helmets and stress are out of scope beyond one cap session.
