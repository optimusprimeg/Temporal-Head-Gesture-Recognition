# Data-collection app v2: plan (not built yet)

Plan written 2026-11-07, after the first real Mac + AirPods test (`data/internal GG 01`). Goal: one app that a
participant can run with little help. It shows what to do and when, records continuously, checks each trial as
it happens, repeats only the failed trials (never the whole hour), survives crashes and earbud changes, and sends
the finished data to us automatically.

---

## 1. Platform

| | Mac app (now) | iPhone app (later, same code) |
|---|---|---|
| Sitting / standing blocks | yes | yes |
| Walking / running | only near the Mac (Bluetooth range about 10 m; treadmill next to it) | yes, phone in a pocket |
| Install on other people's devices | send the zip (ad-hoc signed, "Open Anyway") | needs Xcode sideload (free, 7 days) or TestFlight (paid Apple developer account) |

**Decision:** build it as one **SwiftUI multiplatform** project (macOS target first, iOS target added later).
The recorder, session engine, checker and uploader are shared code; only the screens differ. Apple's
`CMHeadphoneMotionManager` is the same on both.

## 2. What the participant sees (screens in order)

0. **Start**: new participant (first name → next free number) or continue one from the dropdown (section 3c).
1. **Welcome + consent**: what we record (head motion only, no audio or video); data files carry only the
   participant number, the first name is kept only in the roster to continue sessions; and a tick box.
2. **Profile** (asked once): age range, handedness, glasses yes/no, which AirPods model, how they normally wear
   them. Saved to `session.json`.
3. **Device check**: live rate (about 50 Hz), which earbud streams, |g| = 9.81, and a **live 3D head that follows
   their head**. "Nod and watch the head nod" tells them the connection works. It won't continue until all checks
   are green.
4. **Learn the motions**: one card per motion with
   - a **3D head animation** of the motion, looping: start at the front, move, come straight back, pause
     (no holding at the end);
   - one short sentence (from `INSTRUCTIONS`, e.g. "tilt left: left ear toward the left shoulder and straight back");
   - **practice**: they do it 3 times; the live head mirrors them and the checker (section 4) says
     "good" or "try again: come straight back to the front". Practice data is saved and labelled `practice`.
5. **Calibration**: still for 4 s, then 3 nods (chin down first, straight back). Repeated automatically after a
   re-wear or an earbud switch.
6. **Blocks** (the session plan, section 3). During a trial the screen shows the motion name and the animated head
   (small), a progress bar, and the remaining time for the block. **Cues are spoken through the AirPods** ("tilt
   left", then a beep), so walking and running blocks work eyes-free.
7. **Breaks** every few minutes, with "keep the AirPods in".
8. **Done**: a summary (trials OK, repeated, failed) and the upload status.

A hidden **experimenter panel** (keyboard shortcut / long press): pause, skip a trial, add a note, recalibrate,
end the block early. Every action is logged in the cue log.

## 3. Session plan and bias control

The plan is a **JSON file** (motions, instructions, blocks, counts), so the vocabulary can change after the pilot
without rebuilding the app. Same block kinds as `collector/config.py`: calibration, rounds, pairs, commands,
self-paced, re-wear, negatives.

Randomisation, all from a per-participant seed stored in `session.json`:
- motion order shuffled inside every round; idle cues mixed in;
- random gap between cues (2.5-5 s) so people cannot anticipate the beep;
- **block order counterbalanced** across participants (Latin square): sitting / standing / walking blocks and the
  speed/size blocks do not always come in the same order, so fatigue and learning do not line up with condition;
- **device order** (AirPods Pro 2 vs the newer model) assigned from the participant number (crossover);
- conditions done **while** something else happens (parallel activities): gestures while standing, walking (in
  place or treadmill), with the head pre-tilted, while listening to audio, right after talking;
- **negatives blocks** (no gestures) with random order of activities: read a text aloud (the app shows it), chat,
  chew, walk, run (iPhone or treadmill), watch a short video and **nod along naturally**, type. These give the
  false-alarm data (H6) and the "none" class.

## 3b. Time budget: short and long sessions without biasing the data

People have different amounts of time. The app takes the **time available** (e.g. 25, 40 or 60 min) and plans
the session itself. The danger is that "what gets cut" becomes tied to a condition, a motion or a type of
person, and the data can then no longer be analysed honestly. Rules that prevent this:

**What goes in the core is decided by the evidence so far** (what is already supported vs untested and central):

| Hypothesis | Evidence now | Needs from every person? |
|---|---|---|
| H2 commands work on a new person | **untested**: EarSet has no commands; back-to-back motions merged 50 % of the time in simulation | **yes**: it is the deliverable (20 commands) and the biggest risk |
| H4 small (covert) gestures | **untested**, and the ×3 detector setting makes small motions harder to detect | **yes**: "covert" is in the project title |
| H5 features vs MiniRocket, accuracy on a new person | needs balanced sitting data from all people | **yes** |
| H6 false alarms | EarSet offline 0.2/h, talking is the main source | talking: yes; other activities: optional |
| H1 head frame | already well supported (Phase 0, EarSet → AirPods 0.95-1.00) | robustness parts (re-wear, posture): optional |
| walking, extra repetitions | nice to have | optional |

**1. A fixed core that everyone does completely (about 25 min), once per device.**
- setup (consent, device check, learning + practice, calibration): about 6 min
- 2 enrollment rounds + 6 sitting rounds of all motions (H5, H1, accuracy on a new person)
- **2 small-size rounds** (H4)
- **10 cued commands, back to back, + 1 self-paced list of 5 commands** (H2, H3)
- 2 min talking + 1 min nodding along, no gestures (H6, the main false-alarm source)

Every participant gives the same core, so the main results use **all** participants with balanced data. The core
also gives each person's own **sitting baseline**, which every optional condition is compared against. A second
session with the other AirPods model repeats the core (needed for the device comparison), then continues the
modules.

**2. Optional modules, each self-contained (5-7 min), always done whole or not at all.**

| Module | Content | Tests | In rotation |
|---|---|---|---|
| A. Re-wear | take out, put back, recalibrate, 4 sitting rounds | H1 (wear) | yes |
| B. Speed + more small | 1 slow, 1 fast, 2 more small rounds | H4 | yes |
| C. Posture | 2 standing rounds, 2 rounds with the head already tilted/turned | H1 (posture) | yes |
| D. Walking | 2 rounds walking in place, 2 min walking without gestures | H1, H6 | yes |
| E. More commands | back-to-back pairs at set pauses (0.3 / 0.6 / 1.0 s), 10 more commands, 1 more self-paced list | H2, H3 | yes |
| F. Daily-life negatives | chew, drink, use the phone, read aloud, nod along to a video | H6 | yes |
| G. Extra sitting rounds | 4 more rounds | precision | **no**: only fills leftover time at the end |

**3. Each participant has a personal module order, rotated by participant number** (a Latin square over A-F; G
always last). A short session does the core plus the **first** modules of that person's order; a long one does
them all. So:
- across participants, every module is first for about 1 in 6 people: **coverage is spread evenly**, and the
  module order is counterbalanced (fatigue and learning do not always hit the same module);
- **which** modules a person misses depends only on their number, never on how they perform or who they are.
  In statistics this is a *planned missing data* design; mixed models (lme4) handle the uneven counts. What does
  depend on the person is *how many* modules they do: we report it and check it against accuracy.
- Exceptions to the rotation: re-wear (A) is never the last module; walking (D) needs the space ready, so the
  experimenter can move it by one place (logged).

**4. Planning and replanning.** Time per module is known (cues × (window + mean gap)) plus 10 % for retakes. Before
starting, the app shows the plan ("with 40 min you do: core + E + B + F") and the experimenter confirms. During the
session it re-estimates from the real pace (retakes, breaks). Before each module it checks whether the module still
fits; if not, it skips to the closing part (10 s still + upload). It **never cuts a round or a module in the
middle**. Faster pacing helps short sessions: with the live checker the next cue can come 1.5-3 s (random) after
the motion has ended, instead of always waiting the full 4 s window (about a third less time per trial).

**5. Balance on valid trials.** Inside a round every motion appears once in random order. Failed trials go back
into the queue (max 2 retries, section 4), so the **valid** count per motion stays balanced. Attempts are logged,
so we can also report how often each motion needed a retake.

**6. Minimum and continuation.** Under about 25 min the core does not fit: the app warns and labels anything
recorded as `incomplete` (kept, not used in the main analysis). A person can come back: see section 3c. The second
session uses the other AirPods model (device order also set by participant number, crossover).

**7. Coverage tracking.** Each module needs about 12 or more people to be analysable. A script on the PC
(`gesturekit`, to write) reads the uploaded sessions in the Drive folder and prints a coverage table (people per
module × device). If a module is falling behind, the experimenters can move it to the front of the next people's
order (an override, logged in `session.json`). This rebalancing uses only coverage counts, never results.

The **pilot** (the 5 of us) is not dynamic: it runs the full fixed plan, because it decides the vocabulary.

## 3c. Participants: first name, number, and continuing an unfinished person

**Start screen:**
- **New participant**: type the first name. The app gives the next free number (P01, P02, ...), so the
  module rotation and device order follow from that number.
- **Continue participant**: a dropdown of everyone so far, e.g.
  `Riya (P05) | session 1 on Pro 2 complete | left: B, F | next: session 2 on the newer Pro`
  `Arjun (P07) | session 1 incomplete: stopped in core, round 5 of 6`

  Picking a person shows what is left, and the app plans only that.

**What counts as done:**
- A module is done when it finished completely. An interrupted module is redone **whole** next time; its
  partial data is kept and labelled `partial`.
- The core is resumed at the **next round** if the person continues the same day on the same AirPods, after a
  new calibration. On another day it continues from the next round too, but always after setup + calibration
  again (the earbuds sit differently every time they are put in).
- Each session gets a running number per person (`P05_s1`, `P05_s2`, ...), shown in the dropdown.

**Where the list comes from** (several Macs, later iPhones, all need the same list):
- The Drive script also keeps one file, `roster.csv`: number, first name, sessions, device per session,
  modules done, status. The app updates it after every module, and reads it (with the token) to fill the dropdown.
- Offline: the app shows its own local history, and catches up the roster when online again. Two Macs taking the
  same new number at the same moment is prevented by the script handing out the numbers.

**Names (changed 2026-11-07, team decision: names are kept in the data too):** ~~Names stay out of the data:~~ the first name lives **only** in `roster.csv` (and on the app's start screen).
Data folders, files and `session.json` use only the number. So the dataset can be shared (e.g. with the course or
in a paper) by simply not sharing `roster.csv`. The consent screen says the first name is kept only to continue
sessions.

## 4. Live trial check and repeats (no 1-hour re-recording)

Recording is **continuous**: the raw stream is always saved, whatever happens. On top of it, each cued trial gets
a verdict a few seconds after its window, from a Swift port of the gesturekit detector (causal, same parameters,
`quiet_scale` 3) and simple rules that use the calibration:

| Rule | Fail reason shown |
|---|---|
| exactly one motion starts in the cue window | "no motion seen" / "two motions: do it once" |
| duration 0.3-3 s (not running into the 4 s cap) | "too slow / too long" |
| main rotation axis matches the motion (nod/look up: ear-to-ear axis; tilt: nose axis; turn: vertical; circle: two axes) | "that looked like a different motion" |
| first swing direction matches (left/right, down/up, cw/ccw) | "other direction" |
| head ends within 15° of where it started, and does not stay at the far end | "come straight back to the front" |

- A failed trial is **put back in the queue** at a random later place in the same block (at most 2 retries; after
  that it is logged as `failed` and the session moves on, so nobody gets stuck).
- Failed attempts are **not deleted**: they stay in the stream with `status = rejected` and the reason. The labeller
  can use or ignore them.
- **Bias warning:** the checker must only reject clear failures (no motion, wrong motion, two motions, holding).
  It must **not** reject unusual but valid styles (slow, small, different rhythm), or we would remove exactly the
  person-to-person variation we study (H1, H5). Speed and size limits are therefore loose, and the "small" block
  uses a lower size limit.
- **Pilot first:** in the pilot, run the checker in **shadow mode** (verdicts logged, nothing repeated) and compare
  its verdicts with our offline labels before trusting it in the main round.

## 5. Interruptions: resume, never restart

- The session state (which trials are done, the retake queue, the seed) is saved after **every trial**. If the
  app crashes, the Mac sleeps or the AirPods disconnect, reopening the app offers **"resume session"** at the next
  pending trial. The stream continues in a new segment file inside the same session folder.
- **Earbud switch** (stream moves to the other bud, found with `sensor_location`): pause, ask to put the bud
  back in, then **recalibrate** (still + 3 nods, about 15 s) and continue. Same after a re-wear block.
- **Data gaps** over 1 s mark the current trial for a retake.
- **Rate check:** if the rate drops under 40 Hz, pause and show the fix.

## 6. Files (unchanged format, so gesturekit loads them as they are)

```
<participant>_<device>_<date>_<time>/
  session.json        participant, profile, seed, plan + plan version, app version, OS, AirPods model,
                      streaming bud, block order, calibrations, protocol version
  stream_000.csv      sensor_ns, host_ns, 16 channels, sensor_location   (one file per segment; new after resume)
  cues.csv            every cue: time (sensor clock), block, motion, condition, attempt, status, reason
  events_live.csv     the live checker's events and verdicts (for checking the checker)
  notes.csv           experimenter notes and actions
```

The cue time is taken directly on the sensor clock (same device), so the clock-alignment step of collector v3 is
no longer needed.

## 7. Getting the data back to us automatically (task 4)

Requirement: Macs (later iPhones) are somewhere else; after a session the data should appear on our PC without
anyone finding files and sending them. Not a live stream.

How it works in the app:
1. Everything is written **locally first** (section 6). Nothing depends on the network during recording.
2. When a block or the session ends, the session folder is zipped per block (about 1-2 MB per 5-min block) and put
   in an **upload queue**.
3. The queue uploads in the background and **retries** until it succeeds (no internet now = upload later). Each
   upload sends a checksum; it is marked done only after the server confirms the same size and checksum.
4. Local files are **never deleted** by the app. The "Done" screen shows "uploaded ✓" per block.

Where it goes. Options:

| Option | How data reaches the PC | Cost / effort | Notes |
|---|---|---|---|
| **A. Google Drive via Apps Script (recommended)** | the app POSTs each zip to a small Google Apps Script web app that saves it in a Drive folder; **Google Drive for desktop** on the PC syncs that folder, so files just appear | free; about 30 lines of script, deployed once | the script URL plus a shared token act as a write-only key: people can add files, nobody can read them; Apps Script limits (about 50 MB per request) are fine with per-block zips |
| B. Supabase / Firebase Storage bucket | the app uploads with a write-only key; a small script on the PC downloads new files | free tier; account + bucket rules | more control, a proper database later |
| C. Server on our PC (Tailscale) | the app uploads straight to the PC over a private network | free; Tailscale on every device | the PC must be on during uploads |

Privacy: only participant IDs, never names; consent stored with the session; the IMU data has no audio or video.

### 7b. Chosen: Google Drive via Apps Script (decided 2026-11-07)

```
Mac / iPhone app ──HTTPS POST (zip per block)──> Apps Script web app ──> Drive folder "CS724 uploads"
                                                   (runs as us)              │
                                                                            Google Drive for desktop
                                                                            └─> folder on our PC
```

**Request** (one per block zip): JSON body
`{ "token": "<shared secret>", "session": "P05_pro2_2026-11-20_1410", "file": "block03.zip",
   "md5": "<hex>", "data": "<base64 zip>" }`.
The token goes in the body because Apps Script cannot read request headers. Base64 adds about a third, so a 2 MB
zip becomes about 2.7 MB, far below the limit (about 50 MB per request).

**Script behaviour (`doPost`)**:
1. wrong or missing token → `{"ok": false, "error": "token"}`;
2. decode the base64, compute the MD5 with `Utilities.computeDigest`, compare with the app's → mismatch =
   error, nothing saved;
3. find or create the subfolder `session` inside the upload folder;
4. a file with the same name **and** the same MD5 already there → reply ok without saving again (safe retries);
   same name, different MD5 → save as `block03 (2).zip` and report it;
5. save, reply `{"ok": true, "md5": ..., "bytes": ...}`.
The app marks a block uploaded only when `ok` is true and `md5`/`bytes` match its own.

**App side**:
- `URLSession` background upload; retry with back-off (1 min, 5 min, 30 min, then hourly).
- Apps Script replies with an HTTP 302 redirect to the result. Follow it and read the JSON; the upload has
  already happened by then.
- The token and the script URL are entered once in the app's experimenter settings (Keychain), not hard-coded
  and not in the repo, so we can replace them without a rebuild.
- A manual **"Upload now"** button, plus an **"Export zip"** fallback (AirDrop / WhatsApp) if Google is blocked.

**One-time setup (us, about 15 min)**:
1. In the project Gmail, make the Drive folder `CS724 uploads` and copy its ID from the URL.
2. script.google.com → New project → paste the script, set `FOLDER_ID` and `TOKEN` in Script Properties.
3. Deploy → Web app → Execute as **Me**, access **Anyone**. Enter the `/exec` URL and the token in each app's
   experimenter settings (never in the repo).
4. Install Google Drive for desktop on the PC and sync `CS724 uploads`. New sessions appear there.
5. Test from the app with a dummy session, then delete the dummy.

**Security**: anyone with the URL **and** the token can add files and read the roster (numbers, first names,
progress); nobody can read the data files or delete anything through it. If the token leaks, change it in Script
Properties and in each app's settings.

**Account (we only have free personal Google accounts, which is fine):** make **one new free Gmail just for the
project** (e.g. a "cs724 group 6 data" address), instead of using anyone's own account. Apps Script web apps with
"Anyone" access work on free accounts. Its 15 GB is enough (about 1 GB needed). Share the `CS724 uploads` folder
with each member's personal account as **viewer**. On the PC either sign Drive for desktop into the project
account, or add the shared folder to your own Drive ("Add shortcut to Drive") so it syncs. The password stays
with one person plus a written backup; the script runs as the project account, so nobody's own Drive is involved.

**What the team provides, and what it must not give anyone:**
- **Never share the project Gmail password**, not with Claude, not in chat, not in the repo. Nobody else needs it.
- Claude writes the script (`doPost` for uploads, `doGet` for the roster) and the setup steps; a team member
  pastes it into script.google.com while signed into the project Gmail and deploys it (section 7b steps 1-5).
- That gives two values: the **web-app URL** (`https://script.google.com/macros/s/.../exec`) and a **token**
  (a long random string the team makes, e.g. 32 random characters). The app asks for both **once, on first
  launch** (experimenter settings) and stores them in the Mac's Keychain.
- **The URL and the token never go into the git repo**: the repo is public on GitHub, and anyone with both could
  upload junk and read the roster with first names. For testing the app, Claude only needs a dummy URL; the
  team does the real test upload.

**Limits to keep in mind**: Apps Script runs at most 6 min per call and has a daily quota of Drive writes; one
zip per block (about 15-20 calls per participant) is far inside both. Free Drive is 15 GB; a full participant is
about 20-40 MB zipped, so 20 participants need about 1 GB.

## 8. Build order (each step usable on its own)

Status 2026-11-07: step 1 written as `GestureCollector/` (v2.0, not yet compiled or tried on a Mac), including
the time-budget planner, the roster with first names, resume, earbud-switch recalibration, a simple cartoon head
(demo + live mirror) and zip export. Drive upload (step 2) is postponed by decision; the shared Drive folder
remains an option because the data folder can be moved there from the start screen.

1. Session engine: plan JSON, randomisation, spoken + beep cues, continuous recording, cue log on the sensor clock,
   resume after a crash. (Replaces collector v3 + Sensor Logger.)
2. Upload queue + the Apps Script receiver (section 7b).
3. Instructions: 3D head (simple head model made of basic shapes: head, nose, ears, so no licensing), motion
   animations, live mirror, practice.
4. Live checker in shadow mode (Swift port of the detector + the rules in section 4), tested against gesturekit on
   the same recordings.
5. Retake queue switched on (after the pilot shows the checker agrees with our labels).
6. iOS target (walking/running outdoors).

## 9. Decisions needed from the team

1. ~~Upload backend~~ **decided: A, Google Drive via Apps Script** (section 7b), owned by a new free Gmail made
   only for the project.
2. Mac only for now, or plan the iPhone version for walking/running right away?
3. Spoken cue language (English only, or English + Hindi).
4. ~~Who keeps the participant ID list~~ **decided: `roster.csv` in the project Drive** (section 3c); only the
   team can open it.
