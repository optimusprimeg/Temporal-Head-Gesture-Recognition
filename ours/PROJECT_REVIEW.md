# Project review (2026-11-07)

Where the project stands after the first real AirPods data, what is missing for a credible paper, how it would work
in a real team operation, and the small experiments worth adding. Sources: our own results (`algorithm/results/`),
the earlier team analysis (`../prior_work/gesture_lab/reports/08_analysis_and_plan.md`), related work found online (end).

---

## 1. Compared with the earlier pipeline

The earlier pipeline: Sensor Logger on an iPhone, cut takes of 2.5 s, a random forest on 96 statistics from a centre
crop, 4 people, 8 gestures including jaw clenches and doubles. Its own analysis found:

| Earlier finding | Number | What we did with it |
|---|---|---|
| Within-person 0.91 drops to **0.61 on a new person** (the live receiver recipe) | LOSO, 944 takes | the core problem we attack: head frame + features that measure the gesture, not the person |
| Gravity alignment + MiniRocket | 0.72 | kept as the main learned baseline; we add the heading from calibration nods |
| **Enrollment: 3-5 own takes per gesture** | **+8 to +10 points** (0.72 → 0.82) | **dropped by us so far, should come back** (see 2.3) |
| More training people | +7 points per person, not flat at 4 | 20 people planned; keep the learning-curve figure |
| Leaky ESN (reservoir computing) | 0.66, best finder but 200-300 false alarms/h | answers the reservoir question: tried, below MiniRocket; not worth repeating |
| Augmentation | −3 to −6 points | not used |
| Fixed sliding windows | 130-240 false alarms/h | replaced by the variable-length detector |
| Idle as a class beats a confidence threshold | 23 % vs 68-79 % of idle let through | same conclusion; the negatives block exists for this |
| Jaw single vs double | 0.57 (chance) | jaw and doubles dropped |

**Genuinely better now:**
- **Recording.** Continuous recording with a cue log, plus real negatives (talking, chewing, walking) and shuffled
  rounds. This should remove the suspected time leak behind the 0.91 within-person figure. That leak is a
  hypothesis from the earlier analysis, not yet tested.
- **Head frame.** Gravity plus calibration nods.
  - With axis features only: EarSet → AirPods 0.95, but the reverse direction is 0.80; EarSet → P01 21/21.
  - With signed and timing features added, EarSet → P01 drops to 17/21.
  - Against raw axes, the head frame is only a small gain on one device: 0.97 vs 0.95, not significant for 3
    classes (p = 0.14). Its value is robustness across people and devices.
- **Features chosen by statistics** (R mixed models), not hand-picked. The rule was written after seeing EarSet and
  fixed before our own data, not before all data.
- **Causal detector** with variable-length events. It runs live.
- **Command layer.** Pairs plus a gate: on EarSet, false single motions/h drop from 39 to 0.2 false commands/h.
- **Collection app.** Resume after a crash, earbud-switch handling, a one-motion check, time budgets.

**What they did that we should keep:**
- the personalization curve and the learning curve, as two figures;
- the channel ablation (rotation rate alone carries most of the information);
- the earlier recipe (RF, 96 statistics) as the "status quo" baseline on our data.

---

## 2. Missing analyses for a credible paper

### 2.1 Baselines on the same splits (no new recording)
Run every method on the same leave-one-person-out folds, plus device-out folds:
- (a) the earlier recipe: RF, 96 statistics, centre crop, raw axes;
- (b) MiniRocket with gravity alignment;
- (c) DTW 1-NN on enrollment templates;
- (d) ours: detector, head frame, screened features, logistic regression.

Report per-person accuracy with bootstrap 95 % CIs, resampling people, not trials. Test differences with the
planned mixed-effects logistic model. Plain McNemar ignores that trials cluster by person, so it is not the test.
Any tuning (quiet_scale, end_s, gate) is done inside the training folds only.

### 2.2 Ablations (no new recording)
| Ablation | What it shows |
|---|---|
| raw axes / gravity only / head frame (R0 / R1 / R2) | H1, on our data rather than EarSet |
| feature sets: axis / + signed / + timing / + magnitude (normalised) | H5 and the screening rule |
| detector vs fixed 2 s windows on the continuous streams | H3, which is still untested |
| quiet_scale 1 / 2 / 3 / 4, end_s 0.2 / 0.4 / 0.6 | how sensitive the system is; covert gestures (H4) |
| pair timeout 1.0 / 1.5 / 2.0 s, gate thresholds | the command-recall vs false-commands curve (H2, H6) |

### 2.3 Enrollment (personalization)
The app's core records 2 enrollment rounds per person (the older collector used 3). That allows k = 0, 1, 2 own
trials per motion, weighted, on top of the population model. The earlier data says this is the biggest single lever
(+10 points). In operations it maps to "2 minutes of calibration before the mission".

Two caveats:
- **To reach k = 5,** raise the core enrollment to 5 rounds (+4.5 min). Taking trials from the main rounds would use
  up test data.
- **Enrollment is "slow and clear",** unlike the test trials. Report the curve with that caveat, or make enrollment
  normal-speed.

### 2.4 Leakage and confounds to rule out
- Feature screening and any normalisation fitted **inside** each training fold only.
- Calibration nods and practice trials never used as test data (already excluded by the labeller).
- Device order and session order: crossover, test as fixed effects.
- Left vs right earbud (the streaming bud can change mid-session): include it as a factor, and check that the
  head frame removes it.
- 50 vs 25 Hz models: resample, report separately.

### 2.5 End-to-end metrics (what an operator feels)
These come from the cued commands, the self-paced lists and the negatives:
- command recall and precision;
- false commands per hour per activity;
- **latency** from the end of the second motion to the command (currently about 0.4 s plus the pair wait);
- commands per minute.

### 2.6 Covertness: currently claimed, never measured
The title promises covert commands, but nothing tests whether a bystander notices. See experiment E4 below.

### 2.7 Threats to validity found in our own numbers (from the independent fact-check)
- **P01 is not an independent test.** quiet_scale 3 and the labelling fixes were tuned on P01's own recordings.
  Test the final settings only on pilot people who were not used for tuning.
- **The false-command estimate covers the wrong vocabulary.** It used EarSet's 3 motions (6 pairs). Look up, turn
  and circles are not in EarSet. The real rate for 20 pairs over 8 motions must be measured on our negatives.
- **False pairs are not independent.** A nodding conversation partner, or look-up followed by nod-down, produce pairs
  in bursts. Report false commands per hour with CIs across people, from real timelines, never by multiplying
  single-motion rates.
- **The quiet level depends on posture.** It comes from a seated still pose. Standing or patrolling raises the
  background motion. Test calibration-in-one-posture, use-in-another (module C/D data).
- **The heading sign assumes "chin down first"**, which was never verified on the old data. Check it per person with
  the calibration nods' first swing, and report how often it is violated.
- **share_x is partly true by construction.** The head frame's x axis comes from the person's own nods, so "nod
  turns about x" is partly guaranteed. Say so whenever the axis shares are reported.

---

## 3. How it would work in a real operation (Alpha / Charlie teams)

### 3.1 The system
```
operator (AirPods) --BLE--> own phone app: detector + classifier + pair decoder (on device, no raw data sent)
        |  private earcon in own ear: "tilt-nod = GO FORWARD" + 1.5 s to cancel (shake)
        v
command message {team, sender, command, time, confidence, position}  (~100 bytes)
        |  team network: Wi-Fi / LTE / mesh radio (e.g. Meshtastic LoRa), later ATAK Cursor-on-Target
        v
central platform (command post): roster, team dictionaries, routing, live timeline + map, acknowledgements, logs
        |
        v
teammates' phones -> spoken in their AirPods: "Alpha 2: enemy left"; they nod-nod to ACK -> sender hears "acked by 3"
```

### 3.2 What the central platform does
1. **Teams and roster.** Alpha 1-4, Charlie 1-4. Who is online, with battery and earbud status.
2. **Dictionaries.** One per team or mission, pushed to the phones. This is the same idea as the app's `plan.json`.
3. **Routing.** Team broadcast by default; command post to team; later, addressed commands.
4. **Acknowledgements and timeline.** Each command shows who received and acked it, with latency.
5. **"Not me" reports.** An operator can flag a false command. Each flag is a labelled negative for retraining,
   and it gives a field false-alarm rate.
6. **After-action log** for review.

For the course this is a small server (FastAPI + WebSockets) plus a web dashboard. Phones or Macs run the
recogniser, and three people in a room run a scripted scenario.

### 3.3 Operational risks, and how each is handled or tested
| Risk | Why it matters | Mitigation | Cheapest test |
|---|---|---|---|
| **False commands while moving** (walking, running, crouching) | head motion during gait triggers the detector | pair rule + "none" class + **gating**: an arm gesture first, or only when the body is not running | module D data: false commands/h with vs without gating |
| **No feedback to the sender** | a misread command goes out silently | private earcon + 1.5 s cancel window (shake = cancel) | live demo: count cancelled false commands |
| **Microphone use may stop motion data** (reported by developers, not verified by us) | if AirPods are also the voice radio, gestures could die during talk-back | separate radio headset, or note it as an Apple API limit | E8: 2 min with a call open: does the rate drop to 0? |
| **Quiet level set in a different posture** | calibration seated, use while standing or moving | recalibrate per posture, or use the running (adaptive) quiet level | calibrate seated, test standing (module C) |
| **Helmets, ear defenders, sweat** | AirPods may not fit under gear; the fit changes the angle | the head frame recalibrates (10 s); generalise to any earable IMU | re-wear module A; one session with a cap or helmet |
| **One earbud streams; switch mid-mission** | the head frame changes with the bud | done: detect the switch, recalibrate | earbud-switch test (done once) |
| **Stress and fatigue** change gesture size and speed | the classifier must not rely on speed | the screened set leaves raw speed out (speed is mostly person); normalised speed is still useful for gesture-vs-none (EarSet 39 → 14 false single motions/h); enrollment | B module (slow/fast/small) |
| **Latency** | "enemy left" is urgent | measure the full chain: motion end → phone → hub → teammate ear | live demo timestamps |
| **Battery** | AirPods last ~5-6 h of listening; the phone runs the app | low duty-cycle recogniser; report drain | 1 h run, battery before/after |
| **Security** | spoofed or replayed commands | sign and encrypt messages (team key), sequence numbers | out of scope; state it |
| **Learnability** of 20 commands | operators must remember pairs | pairs with meaning (tilt = direction, nod = confirm); a card; practice | SUS + recall test after a session |

### 3.4 Does it work in the real world?
**Seated or standing, at a checkpoint or on watch: promising, not yet shown.**
- **Recognition transfers:** axis features 0.95 EarSet → AirPods; 21/21 on P01.
- **On EarSet, the pair rule cut false commands to about 0.2 per hour overall, but 2-3 per hour while speaking.**
  Those come from very few events, so they are noisy.
- **On real AirPods talking, there is no answer yet:** without a "none" class, 348 gestures/h pass the gate. The
  real false-command rate while talking is the key unknown.

**Moving (patrol, running): unknown, and the biggest risk.**
- EarSet walking and running were on a treadmill, and offline.
- An explicit wake gesture or motion gating is probably needed.

**Covert: plausible for small gestures, but not yet shown.**
- The ×3 detector setting may miss them.

---

## 4. Related work (online search, 2026-11-07)

| Work | What it does | How we differ |
|---|---|---|
| **MorsEar** (CHI 2026, Chugh et al.) | earable IMU micro-gestures near the ear (taps, slides) → Morse code → text; 24 people, CER 7.3 %, 9 WPM; silent, cafe and metro settings | ours: head motions, no hand needed, 20 fixed commands, team relay; their 3-setting evaluation is a model for ours |
| **Apple AirPods head gestures** (iOS 18) | nod = accept, shake = decline calls and notifications; Pro 2, AirPods 4 (Pro 3) | an industry precedent with 2 gestures, used only after a Siri prompt (that is their false-alarm control); we do 8 motions → 20 commands with no prompt |
| **HeadText** (2022) | hands-free text entry by head gestures on a smart earpiece | text entry, not commands |
| **eSense studies** | nod/shake F1 0.82-0.88; cross-user F1 0.79 (13 people) | our cross-person numbers should be compared with these |
| **EarSet** (Sci. Data 2023) | 30 people, in-ear IMU, head and face motion | we use it as public pre-training and test data |
| **CHAR** (PerCom) | composite head-body activities from one earable: 97 % user-dependent, 89.7 % independent | shows the person gap we target |
| **Tactical sign-language wearable** (Springer 2025) | hand gestures → encrypted mesh messages with GPS | closest "silent team command" system; hands busy is our argument |
| **ATAK / Meshtastic plugin** | team map and messaging (Cursor-on-Target) over mesh radio | the natural integration target for the central platform |

**Gap we fill (as far as an unsystematic web search shows; do a proper ACM/IEEE search before claiming it in the
paper):** we found no published system that turns earbud head motions into a **team command vocabulary** with
cross-person and cross-device evaluation, measured false commands per hour, and a relay to teammates.

---

## 5. Small experiments to add to the paper

| # | Experiment | Data | Supports | Cost |
|---|---|---|---|---|
| E1 | **Baseline shoot-out** (earlier RF recipe, MiniRocket, DTW, ours) on identical folds, mixed-model test | pilot + main | the main claim | compute only |
| E2 | **Enrollment curve** k = 0, 1, 2 (k up to 5 if enrollment is raised to 5 rounds) | core enrollment rounds | the operations story (2-min calibration) | compute only (+4.5 min/session for k = 5) |
| E3 | **Natural-pair frequency**: how often everyday motion produces each candidate pair. Choose the 20 least-natural pairs on half the people, report false commands on the other half (otherwise selection bias). About 2.7 h of negatives in total, so many counts will be zero: pool similar pairs | negatives blocks | novel dictionary design rule; lower false commands | compute only |
| E4 | **Covertness**: 3+ performers chat normally; in some clips they send small or normal commands, in **catch clips none**; 5+ observers who do not know when, mark what they saw; report detectability (d′) per gesture size | ~30 short clips + viewers | the "covert" claim (bystander side; H4 recognition is measured separately) | ~1 h |
| E5 | **Live team demo**: 3 people, a central dashboard, a scripted scenario; latency and recall per command, cancels. A feasibility demo only: too short for false commands per hour or SUS statistics | live | real-world feasibility | ~45 min + building the hub |
| E6 | **Walking with vs without gating** (wake gesture or stationary-only). Module D is walking in place with ~2 min of negatives, so add one real walk (10 min, corridor) for a usable rate | module D + 10 min walk | operations while moving | small code change + 10 min |
| E7 | **Device transfer**: Pro 2 ↔ AirPods 5, both directions (AirPods 5 confirmed by the team; record its model and rate from the app's detection) | crossover sessions | H1 device bias | compute only |
| E8 | **Microphone test**: call open → is motion data lost? | 2 min | a deployment constraint, honestly reported | 5 min |
| E9 | **Helmet or cap session** (one person) | 10 min | robustness to gear | 15 min |

---

## 6. What looks overstated today
- **EarSet false commands are offline.** They use the worst-case dictionary, on 7.5 h of data of which 60 % is cued
  face tasks. They are a lower bound on what we need to measure live.
- **All real AirPods results come from one person (P01)**, with 3-4 examples per motion.
- **quiet_scale 3 was chosen on P01.** It then improved EarSet, which is good, but it was not fixed in advance. P01's
  own scores are therefore not an independent test. State that in the paper.
- **The head frame vs raw axes on one device:** 0.97 vs 0.95, not significant for 3 classes. Do not sell it as an
  accuracy gain; sell it as robustness across people, devices and earbud switches.

This review was fact-checked by an independent Claude reviewer against the repo files (2026-11-07). Its corrections
are applied above. The agy and byteask second opinions could not run on this machine: agy needed command permission
in headless mode, and byteask's Windows wrapper failed.
- **The paper skeleton** (`../paper/main.tex`) is still titled "Tongue/Face Gestures using Earable". It needs
  rewriting around head-gesture commands.

---

## 7. Highest-value next actions
1. **Run the pilot** (5 people × both devices) with app v2.1. It unlocks E1, E2, E3, E7 and the vocabulary decision.
2. **Build the small central platform** (server + dashboard + phone/Mac client sending commands), for the live demo (E5).
3. **Add the earcon + cancel and the motion gating** to the recogniser. These are the two cheapest protections
   against false commands in the field.

## 8. Decisions after the review (2026-11-07 discussion)
**Build order:** (1) live command recogniser in the Mac app (rule-based: dominant axis + sign of the first swing,
which separated every direction pair in P01); (2) hub + phone listeners on a phone hotspot (Mac = recogniser +
hub, teammates' phones open a web page, hear "Alpha 2: enemy left", tap to acknowledge); (3) earcon + 1.5 s
head-shake cancel; (4) motion gating, after the walk recording. The pilot stays the top priority for the paper.

**Status (2026-11-07, app v2.2, not yet run on a Mac):** step 1 and the pilot changes are built. Live recogniser with a Rules/Model switch; first numbers in `algorithm/results/live_model.md`: on P01's 60 motions Rules get 0.93 and Model 0.78 (Model is weak on circles, with only 16 training examples). Rules reject almost nothing that is not a gesture (EarSet no-gesture events called 'none': 0.03, against 0.59 for Model), so in Rules mode the pair rule does all the false-command work.

**Pilot changes:** module D becomes real walking around the room with corners (not walking in place), plus ~10
commands while walking slowly, plus walking without gestures including turns. New hard negatives: turn the whole
body to look behind, look around the room, stand up and sit down. Procedure: freeze the analysis settings (git tag)
before P02-P06 (P01 is development data only); one microphone test (QuickTime recording from the AirPods mic while
the app records); one cap/helmet session; phone video of 2-3 people for the covertness test, synced by one tap on
the AirPod. The enrollment curve uses the existing enrollment + sitting rounds, so no extra rounds are needed.

**Covertness** is measured as "was a command sent at all?" (observer d′ against chance, and command amplitude
against everyday head movement), not "which command?" (the dictionary is private). Covertness and false commands
are two sides of one coin: the more a command looks like normal movement, the more normal movement looks like a
command.

**Head turn vs body turn (idea, to test on the walk recording).** The earbud sits to the side of the neck's
rotation axis, so a pure head turn already produces large acceleration at the ear (P01 turns: 4.5-6.4 m/s² peak,
the largest of all motions). Treating the earbud as a point on a rigid head, a_ear = a_body + α × r + ω × (ω × r).
Fitting r on half of P01's seated trials gave **r = 8.6 cm to the side** (anatomically right, found from data
alone), and on the other half head rotation explained **91-92 % of the acceleration variance in turns** (0.69
over all motions; nods only 0.13-0.26, because nods pivot lower in the neck). So: residual = the acceleration head
rotation cannot explain = body motion, and detection gets stricter as the residual grows. A second cue: net
heading change from the quaternion (a gesture returns to the front, a body turn does not; summing the gyro is
not enough, circles show a false 55-72° net yaw that way). Caveats: one person, 14 trials, seated; residual
peaks in still-body trials already reach 1.5-2.2 m/s², so the separation must be shown on walking data.
Script: `algorithm/scripts/lever_arm_check.py`.

Sources: MorsEar ([researchr](https://researchr.org/publication/ChughGRCC26),
[summary](https://synapsesocial.com/papers/W7161410902)); Apple head gestures
([9to5Mac](https://9to5mac.com/2024/09/25/how-to-use-new-airpods-features/),
[SoundGuys](https://www.soundguys.com/all-the-new-airpods-features-you-probably-didnt-know-about-149916/));
[HeadText](https://arxiv.org/pdf/2205.09978);
[eSense hierarchical classification](https://www.researchgate.net/publication/355379812_Hierarchical_Classification_and_Transfer_Learning_to_Recognize_Head_Gestures_and_Facial_Expressions_Using_Earbuds);
[CHAR](https://yongpanzou.github.io/documents/CHARPercom.pdf);
[EarSet](https://www.researchgate.net/publication/376142378_EarSet_A_Multi-Modal_Dataset_for_Studying_the_Impact_of_Head_and_Facial_Movements_on_In-Ear_PPG_Signals);
[tactical sign-language wearable](https://link.springer.com/chapter/10.1007/978-3-032-16791-0_8);
[Meshtastic ATAK plugin](https://gh.r-mj.com/meshtastic/ATAK-Plugin); [Nett Warrior](https://en.wikipedia.org/wiki/Nett_Warrior);
[walking false detections (Sensors and Materials)](https://sensors.myu-group.co.jp/sm_pdf/SM3019.pdf).
