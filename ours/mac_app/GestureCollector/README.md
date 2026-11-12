# Gesture Collector (Mac + iPhone app, v3)

The data-collection app from `../APP_V2_PLAN.md`, **build step 1**. It replaces collector v3 + Sensor Logger:
one Mac with AirPods runs the whole session. It explains the motions, gives spoken cues through the AirPods,
records continuously, and resumes after a crash.

**Status:** written on Windows; it must compile on GitHub (macOS runner) and be tried on a Mac before real
participants. The live head's left/right signs are still to be checked.

## New in v3.3: the teammates' 30 gestures, instruction cards, demo clips
- **Experiments for the v5 gesture set** (`../experiments/`, made by `algorithm/scripts/make_v5_experiments.py`):
  `v5.json` = collector_v5's 30 items with the same labels, in random rounds; `v5_plus.json` = those + 1x versions
  (half the reps) + our extra gestures + near-miss cues + modules. `algorithm/scripts/app_to_v5_csv.py` turns a
  session into collector_v5's dataset CSV, so app data and v5 data merge.
- **Instruction card:** a motion may have `how` and `avoid` lines (shown under the title in practice and rounds).
- **WATCH step:** before each motion's first practice, its demo loops with the card until Continue.
- **Demo clips:** `<data folder>/experiments/media/<motion id>.gif` plays instead of the 3D head (`Sources/Media.swift`).
  54 cartoon clips are in `../experiments/media/` (`algorithm/scripts/make_gesture_clips.py`); copy the folder
  next to the experiment files. Any GIF with the motion's id replaces one, with no rebuild.
- **3D demo sequences:** `"demo": "tilt_left,tilt_left"` plays the parts one after another.
- **`every`:** a motion with `"every": 2` is in every 2nd round only (1x versions, near-miss cues).
- **`check`:** the single head motion the rules know it as (`tilt_1x_left` -> `tilt_left`), for the trial check.

## New in v3.2: the name is the go
Text and voice start together and the motion window opens right away (people moved on the name anyway). A green
**NOW** bar fills for the window (planned window + speech time) and one short beep marks its end; there is no beep
before. In `cues.csv`, `sensor_ns_est` = `shown_sensor_ns` = the announcement and `window_s` = the whole window.

## New in v3.1: any session length, trial checks, Forest mode (one rebuild, then files only)
- **Any length:** the start screen has 10 / 20 / 40 min buttons. Rounds hold every motion once, so the planner
  cuts whole rounds (a rounds block's `minRounds` in the experiment file) and every motion keeps the same count.
  **End after this round** stops cleanly at any point; an unfinished person continues next time (resume as before).
- **Trial checks** (`Sources/Checks.swift`): after each cue, three opinions vote on whether the right motion was
  done: our rules, the live model, and DTW against the person's own practice trials. The majority disagreeing
  means `mismatch`. A mismatch or a wrong motion count gives **one retake**, never more. Other flags:
  `too_small`, `posture_jump`, `unsure`. Nothing is deleted; every attempt stays in `cues.csv`, with new
  columns `flags, check_rule, check_model, check_dtw, check_vote, peak_rot`. A session started by an older
  version continues in `cues_v31.csv`.
- **Can't do this motion** (experimenter button): skipped for this person from then on, logged as `cant_do`.
- **Motions in the experiment file** may say `"expect": 2` (a double, e.g. `tilt_2x_left`), `"expect": 0` (not
  counted, e.g. face motions), `"group": "head"|"face"|"touch"`, and `"demo": "tilt_left"` (which head animation to
  show). Face and touch motions are checked and flagged but never retaken for "no motion seen".
- **Forest live mode** (`Sources/ForestModel.swift`): the teammates' receiver approach (0.60 rad/s trigger,
  96 statistics, random forest) next to Rules and Model. It is trained the fixed way, on the windows its own
  detector cuts (`algorithm/scripts/export_forest_model.py`). `forest_model.json` in the data folder replaces the
  built-in one, so no rebuild is needed. Every forest decision is logged to `live/live_<stamp>_forest.csv`.
- **Experiment for the micro study:** `../experiments/micro_v1.json`. Copy it to `<data folder>/experiments/`;
  on the iPhone, use Files > On My iPhone > Gesture Collector > experiments.
- **Review on the PC:** `python algorithm/scripts/review_session.py <session.zip>` writes
  `ours/data/reviews/<session>.md`.
- **Checks on GitHub:** both parity tests (the live recogniser and the forest) run before the build.

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
