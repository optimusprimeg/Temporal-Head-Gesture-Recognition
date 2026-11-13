# Gesture Collector (Mac + iPhone app, v3.7)

The data-collection app from `../APP_V2_PLAN.md`, **build step 1**. It replaces collector v3 + Sensor Logger:
one Mac with AirPods runs the whole session. It explains the motions, gives spoken cues through the AirPods,
records continuously, and resumes after a crash.

**Status:** written on Windows; it must compile on GitHub (macOS runner) and be tried on a Mac before real
participants. The live head's left/right signs are still to be checked.

## v3.7.1: crash fix (camera preview)
- v3.7.0 crashed on macOS 27 (M1) inside SwiftUI's hit testing of a trackpad pressure event, with the camera on
  (crash report: EXC_BAD_ACCESS in MainActor.assumeIsolated <- NSViewResponder <- NSHostingView.hitTest). The
  camera preview is now a normal layer-backed view with the preview as a sublayer that never takes clicks, and the
  preview and 3D heads are `allowsHitTesting(false)` (display only).

## New in v3.7: counting fixes, one earbud either side, Pause on top, optional scene video
Fixes to v3.4-3.6 design mistakes (found in an audit of the code and P01's data):
- **AirPods model no longer changes by itself.** The start screen used to pick the model by the old two-model
  crossover (odd/even participant number, then the other model). Counts are per model, so a silent switch showed
  "done 0" and a full new plan. Now: the model this person used last; an orange note if you pick another one.
- **A trial counts once.** v3.6 counted every "done" row, so a failed check + its retake counted 2 good reps
  (P01: 11 of 91 gestures were retakes). Now one planned trial (rounds block, round, motion) = at most one good rep;
  it is good when its last try is done (a "marked wrong" with no redo = 0). Same rule in the end-of-session table and
  in `scripts/cut_scene_clips.py`.
- **One earbud, either side.** `"earbud": "one"` (v5, v5_plus): wear ONE AirPod, any side; it is logged
  (session.json `earbudSide`, and every stream row's `sensor_location`), never required. v3.5 wrongly required the
  RIGHT one. Old files with `"right"` are read the same way (no warning).
- **v5 and v5_plus share counts** (`"family": "v5"`): a gesture recorded under one counts under the other.
- **"Can't do" is remembered** for the person (roster.json `cantDo`, per family), so that gesture no longer stays
  "missing" forever; "Allow again" on the start screen.
- **Same checks in every session:** the DTW match (templates from practice, which only session 1 has) is still
  logged in `check_dtw` but no longer votes; retakes depend on the rules + model only. (Face/micro gestures never
  got retakes or "looked like" feedback: those need a head motion check.)
- **Targets:** type the number (box) or use - / +; one box sets every gesture that is on; "Reset to defaults".
- **Time left in total:** the gestures header and the plan screen show what ALL of this person's missing reps would
  take, besides this sitting's budget (the old screen only showed the budget, e.g. "45 min" again and again).
- **Run screen:** a big **Pause / Resume** at the top ("Pausing after this step..." until the current step ends);
  "Last one (nod down) was wrong" names the trial and only works right after a gesture (not across a break or
  calibration); the end screen says "Stopped after a round" vs "Session ended" (`endedBy` in session.json).
- **Data folder guard (Mac):** "Change..." refuses a folder inside a data folder (experiments, media, a session,
  removed, video): that is how a second roster.json appeared and sessions looked lost.
- **Optional scene video (webcam, no audio).** Needs the person's video consent (new participant form, or "Fix or
  remove" for existing ones) and the session switch "Record scene video". The device check shows the camera to aim
  it. Files: `<data folder>/video/<session folder>/scene_NNN.mp4` (H.264 720p, one per segment, OUTSIDE the session
  folder so the zip never carries faces) and `<session folder>/scene_NNN_frames.csv` (frame, video_s, sensor_ns on
  the cues.csv clock). `python scripts/cut_scene_clips.py <session folder> [--label]` (from ours/algorithm, needs
  ffmpeg) cuts one clip per kept trial into `clips/<motion>/`: real demos for later pilots, and label checks.
  Videos are gitignored; share only with consent.
- **Video size:** HEVC (H.265; H.264 where there is no HEVC encoder), 15 fps, no audio. "Small" 480p is about
  0.25 GB per hour (default), "Normal" 720p about 0.5 GB per hour (choice remembered, saved as `videoQuality`).
- **Presets:** v5 now has All v5 / Micro only (face + combos) / Head only / Face only / Combos only / Weak ones;
  v5_plus adds 1x + 2x / Extras pilot / Face + face extras / Touch only / Near-miss.
- Sessions saved before v3.7 (no `family` in their experiment.json) still count: the shipped v5 / v5_plus names
  map to family v5.
- Removed the unused v3.4 round-counting code.

## New in v3.6: choose gestures and target reps per person
- Start screen, under the chosen person: **"Gestures for this session"**. Presets from the experiment file
  (`"presets"`: v5 has All v5 / Micro only / Head only / Weak ones; v5_plus adds 1x + 2x / Extras pilot / Near-miss),
  then tick / untick single gestures (idles too) and the long idles, and set each gesture's **target** = good reps
  this person should have in total. Default target: the motion's `"target"`, else core rounds / `every`.
- **Top-up per gesture:** the app counts this person's good reps per gesture (rounds trials done, minus those marked
  wrong) in earlier sessions of the same experiment on the same AirPods, and plans only what is missing. A gesture
  with n reps missing is spread evenly over the rounds, so a session cut short keeps every gesture's share.
- The choice is remembered per person (roster.json `selections`) and saved in session.json (`targets`,
  `longIdle`); the session's `experiment.json` holds only the chosen gestures.

## New in v3.5: experimenter tools
- **Right earbud only** (`"earbud": "right"` in v5 / v5_plus, as collector_v5): the device check and the run screen
  warn when the other AirPod streams. Left vs right flips tilt/turn signs, so mixed sides would not merge.
- **Fix or remove a participant** (start screen, under the chosen person): fix the first name; change the number
  only before any recording; Remove moves their session folders to `<data folder>/removed/<code>_<time>/` with
  `participant.json` (nothing is deleted).
- **"Last one was wrong: redo"** (experimenter box): adds a `marked_wrong` row for the last gesture trial to
  `cues.csv` (note: which trial) and repeats it right after. `app_to_v5_csv.py` marks that take
  `bad:experimenter: wrong motion`.
- **Done screen:** per gesture good / flagged / marked wrong / "Confused?" clicks, and participant feedback per
  gesture group (easy to do, OK in public, 1-5, plus the hardest gesture in their words) saved as `feedback.json`.
- v5 experiments: a short break every 3 rounds.

## New in v3.4: continue a person, built-in experiments and clips, "Confused?" button
- Rounds already recorded in a person's earlier sessions (same experiment, same AirPods) are not planned again.
- `v5.json`, `v5_plus.json` and the demo clips ship inside the app; edited copies are never overwritten.
- "Confused? See real people do it" opens a GIPHY/YouTube search (the motion's `ref` link); clicks go to notes.csv.

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
