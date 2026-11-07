# Gesture Collector (Mac + iPhone app, v3)

The data-collection app from `../APP_V2_PLAN.md`, **build step 1**. It replaces collector v3 + Sensor Logger:
one Mac with AirPods runs the whole session. It explains the motions, gives spoken cues through the AirPods,
records continuously, and resumes after a crash.

**Status:** written on Windows; it must compile on GitHub (macOS runner) and be tried on a Mac before real
participants. The live head's left/right signs are still to be checked.

## New in v3: experiment files, iPhone app, fixes from the independent check
- **Experiment files:** each protocol is a JSON file in `<data folder>/experiments/` (built in: `pilot.json` =
  Pilot v3, `selftest.json`), chosen per session on the start screen. Order rules live in the file:
  `counterbalance`, `requireOneOf`, `modulesPerDevice`, `fillModule`. New block kinds `free` and `message`.
  Broken files are listed with what is wrong. Each session saves `experiment.json`. Format: top of
  `Sources/Plan.swift`.
- **iPhone app:** the same sources build for iOS 16+ (`build_ios.sh`, unsigned `.ipa`; install with Sideloadly or
  Xcode). Platform differences are in `Sources/Platform.swift`.
- **Pilot v3:**
  - sitting and small blocks counterbalanced by participant number;
  - no-gesture time raised to 8 min and split early/late;
  - re-wear or posture required for everyone;
  - modules tracked per AirPods model;
  - pause instruction for commands.
- **Participant number** typed from the team sheet, because each device keeps its own roster.
- **Loop feature fixed:** enclosed area / circle at the peak radius, independent of length and sample rate. The live
  model was retrained (`live-v2`).
- How to run a pilot: `../PILOT_GUIDE.md`.

## New in v2.2: live recognizer + pilot plan changes
**Live recognizer** (start screen → "Live recognizer: try commands"; not part of a session):
1. **Calibrate:** 3 s still, then nod down 3 times, chin down first. This gives the quiet level and the head frame.
2. **Do commands:** each finished motion goes through the head frame, the features and the decision. Two
   accepted motions within 1.5 s make a command from the plan's dictionary, which is spoken and shown.
3. **Rules / Model switch:**
   - **Rules:** dominant rotation axis (≥ 0.6 of the energy) → nod, tilt or turn; else a loop → circle.
   - **Model:** logistic regression from `live_model.json` (EarSet + P01), with a "not a gesture" class and a
     50 % confidence gate.
   - In both modes the direction comes from one sign (first swing, or the loop for circles).
   - **Both answers are logged for every event**, whichever mode is chosen.
4. **"Wrong" button** on each event: logged, for retraining.
5. **Files:** `live/live_<stamp>.csv` (one row per event) and `live/live_<stamp>_stream.csv` (raw samples).
6. **Model file:** a `live_model.json` in the data folder replaces the built-in one, so a retrained model needs no
   rebuild. Make it with `algorithm/scripts/export_live_model.py`; its results are in
   `algorithm/results/live_model.md`.

The Swift code is checked against Python on 14 real P01 events in the GitHub build (`Tests/main.swift`).

**Pilot plan (plan v2.2):**
- **Module D is real walking** around the room with corners (not walking in place). It adds 10 commands while
  walking slowly, and walking without gestures including turning around.
- **Core no-gesture block:** three hard negatives (look behind with the whole body, look around, stand up and
  sit down), about +2 min.

Why: PROJECT_REVIEW.md section 8.

## New in v2.1 (after the first real session, P01)
- **Cue flow:** the motion is shown and spoken, then the GO beep. The separate ready beep is gone, because people
  moved on the name anyway (P01: 61 % before GO). The **announce time** is logged (`shown_sensor_ns`), and
  gesturekit opens the motion window there.
- **One-motion check after every trial:** a Swift port of gesturekit's detector counts the motions in the window
  and shows feedback: "✓ one motion", "We saw 2 motions: do it ONCE", "No motion seen", "Too long". It is logged as
  `live_events` and `live_verdict`. There are no automatic retakes yet. Checked against gesturekit on P01's data:
  63 vs 63 events, 55 identical within 0.15 s.
- **Two 3D heads** while running (SceneKit, built from basic shapes): **DO THIS** (demo) and **YOU** (live mirror).
- **Full AirPods list** (Pro 2, **AirPods 5**, Pro 3, Pro 1, AirPods 4 / 4 ANC, AirPods 3, Max). The crossover
  pair is AirPods Pro 2 + AirPods 5. The connected model's name, product ID and firmware are read from macOS and
  saved in `session.json`. 25 Hz models are accepted.
- Fixed: two idle cues in one round were logged as attempt 2.

## What v2.0 does
- **Start screen**
  - **New participant:** first name, which becomes the next number (P01, P02…), plus a short profile and consent.
  - **Continue participant:** a dropdown showing what each person has done.
  - **Unfinished sessions:** a list of crashed or closed sessions, each with **Resume**.
- **Device check**
  - Shows rate, |g| and the streaming earbud.
  - A **live cartoon head** mirrors the participant (press "Set front" first).
- **Plan review**
  - The participant's **time available** decides what is planned:
    - the core, once per AirPods model, is never cut;
    - then the optional modules A–F in the person's rotated order (Williams Latin square by number), only whole;
    - then extra sitting rounds (G) to fill the time.
  - The AirPods model is suggested by the crossover order.
- **Run**
  - Each cue: the motion name on screen, an animated head showing the motion, the name spoken through the
    AirPods, a ready beep, then the GO beep.
  - Random gaps between cues; motions shuffled inside every round.
  - The state is saved after every step.
  - **Earbud switch or data gap:** a banner appears, the app recalibrates, then repeats the disturbed trial.
  - **Experimenter controls:** pause, skip, calibrate again, add a note, end the session.
- **Done**
  - A summary, plus **Export zip** for AirDrop, WhatsApp or a pen drive.
  - Unfinished modules are planned again next time (a module is always redone whole).

**Not yet** (later build steps): Google Drive upload, the live trial checker and its retake queue, the iPhone version.

## Files (one folder per session, inside the data folder)
The data folder defaults to `~/Documents/GestureCollector`; change it on the start screen.

```
roster.json                      first names + numbers + progress
plan.json                        the study plan (edit to change motions/commands; invalid -> built-in plan)
P05_riya_s1_airpodspro2_20261120_141000/
  session.json   participant number + first name, device, plan version, seed, modules planned/done, status, OS, Mac model
  state.json     every planned step + how far it got (resume)
  stream_000.csv samples: sensor_ns, host_ns, 16 channels (m/s², rad/s, rad), sensor_location; one per segment
  cues.csv       collector-v3 columns + module, attempt, status (done / skipped / disturbed / start / end),
                 shown_sensor_ns, live_events, live_verdict (v2.1)
  notes.csv      experimenter actions and notes
```
Cue times are on the same clock as the samples (boot time + uptime), so no clock alignment is needed.
`gesturekit.io.load_session(<session folder>)` reads it directly; the labeller ignores practice, re-wear, skipped
and disturbed cues.

## Build
GitHub builds it on every push to the `mac-app` branch (release `gesture-collector`). On a Mac:
```
cd ours/mac_app/GestureCollector
bash build.sh
open GestureCollector.app
```
First start of a downloaded copy: right-click → Open, or System Settings → Privacy & Security → Open Anyway.
Allow **Motion & Fitness** when asked.

## Code
| File | What |
|---|---|
| `Sources/Plan.swift` | experiment file format, validation, built-in experiments (pilot, selftest) |
| `Sources/Platform.swift` | Mac / iPhone differences (sounds, zip, files, headphones, screen on) |
| `Sources/Planner.swift` | time budget → step list; Latin square module order; device crossover; time estimates |
| `Sources/Roster.swift` | participants, sessions, what is done per device |
| `Sources/Recorder.swift` | AirPods motion → segment files; rate, earbud, switches, gaps |
| `Sources/Session.swift` | runs the steps: speech, beeps, cue log, state saving, resume, recalibration, zip export |
| `Sources/HeadView.swift` | cartoon head: motion demos and live mirror |
| `Sources/LiveDetector.swift` | live motion detector (port of detect.py): one-motion check, and events for the live recognizer |
| `Sources/LiveRecognizer.swift` | live recognizer logic, Foundation only: head frame, features, rules, model, pair decoder |
| `Sources/LiveScreen.swift` | live mode: engine (motion queue), session (switch, commands, logs), screen |
| `live_model.json`, `Tests/` | built-in model; Swift-vs-Python parity test |
| `Sources/Views.swift`, `AppModel.swift`, `App.swift` | screens and app flow |
