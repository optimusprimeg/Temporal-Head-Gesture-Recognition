# External logic check, 2026-11-08: GPT (byteask, gpt-6.1-sol) and Gemini (agy, gemini-3.8-flash-high)

Both models got the same self-contained packet (below, section 3): claims C1-C9 from the 2026-11-08 work, with the
real numbers. GPT ran read-only with repository access; Gemini answered from the text only. Section 1 is our
response after checking their points against the data.

## 1. Our response (checked against the data)

| Claim | GPT | Gemini | Our conclusion |
|---|---|---|---|
| C1 streams vs clips | sound | sound | Keep. Fix: replay the same held-out streams through all methods with ONE event-matching rule. Correction: the "+10 points" was MiniRocket 0.72 -> 0.82, not the random forest's 0.61 (the packet mixed them). |
| C2 head frame + R | partly | partly | Agree the screening is exploratory (rule written after EarSet). Signed features were not rejected for direction: EarSet cannot judge them; the per-pair screen runs on pilot data. |
| C3 loop fix | partly | partly | Gemini's point is fair: max radius is spike-sensitive; switch to the 95th-percentile radius at the next algorithm change and test on held-out people. |
| C4 commands | partly | wrong | Agree: stitched pairs are not real commands. Real cross pairs come from the self-test and the pilot (core commands + module E). Whether a 0.5 s pause is acceptable for covert use is itself a measure. |
| C5 personalisation | partly | partly | Checked per person (k = 0): speed/size lowered wrongly accepted non-gestures for 27 of 30 people, 0 worse; mean -0.083, 95 % CI [-0.117, -0.054]. Enrollment k = 5: +0.016, CI [0.005, 0.029], 12 better / 6 worse. Same-session caveat stands: the pilot tests enrollment across sessions. |
| C6 cross-device | partly | sound | Agree: one developer, inconclusive. Re-check on pilot people with both devices. |
| C7 body turn | wrong as inference | sound (gait impacts) | Treat as a hypothesis only. Test needs ground truth: head-only, body-only and combined turns, with the phone on the torso as a body reference, plus gait-only streams. |
| C8 design | partly | sound | Adopt: name two primary endpoints (command success on naive participants; false commands per hour), analyse the 5 team members separately, and add long everyday-wear no-gesture recording (8 min/session bounds false commands only to about 0.56/h over 40 sessions; the reviewers' 1.12/h assumed one session each). |
| C9 teammates' demo | sound | sound | Keep: run both recognisers on identical labelled streams; agree a timestamped message format before integrating. |

## 2. Changes proposed from this check
1. Experiment file: optional **everyday-wear** block (about 30 min of normal work with the AirPods in, no gestures)
   to raise no-gesture time per person; no app rebuild needed.
2. Experimental design: two primary endpoints; team members as a separate stratum; one frozen event-matching rule
   for all methods; method comparison with pairing (participant-level resampling).
3. Loop feature: 95th-percentile radius (with the next algorithm change, before freezing).
4. Walking module: body-only and head-only turns with a torso reference.

## 3. The packet sent to both models

# Independent logic check: CS724 head-gesture project (IIT Kanpur, Group 6)

You are a sceptical senior reviewer (signal processing, HCI, experimental design, statistics). READ-ONLY: do not
edit, create or delete any file, and do not run anything that writes files. Everything you need is below; if you
can read the repository (C:\Users\Orion\Desktop\Temporal-Head-Gesture-Recognition, folder `ours/`), you may use it
to verify, but do not rely on it.

## Project
Covert team commands from head motion read by AirPods (Apple CMHeadphoneMotionManager, 50 Hz: rotation rate,
user acceleration, gravity, quaternion; one earbud streams at a time). 8 single motions (nod down, look up, tilt
L/R, turn L/R, circle cw/ccw); a command = two DIFFERENT motions, second must start within 1.5 s of the first's end.
Pipeline on the continuous stream: causal hysteresis detector (quiet level from a 4 s still pose x3; start when
score > 4x quiet for 0.06 s, end after 0.4 s below 2x; events 0.3-4 s) -> head frame (z = up from gravity in the
0.5 s before the event; x = nod axis from 3 calibration nods, chin-down first swing positive; y = z x x) ->
features -> Rules or logistic regression + gate (top prob >= 0.5, margin >= 0.1) -> pair decoder.
Features: axis shares (rotation energy share per head axis), linearity (top eigenvalue share), signed first swing
per axis, loop area per plane, timing (peaks, gaps, high-frequency jerk), magnitude (peak/rms rotation, duration,
cycles, acc per rotation).

## Claims and decisions to check (numbers are real outputs)

C1. Why we work on continuous streams. The earlier teammates' pipeline (Sensor Logger, 2.5 s cued clips, 4
people) reported in its own analysis: MiniRocket 0.72 accuracy on cut clips; on a stream the same models found and
named 0.39-0.43 of gestures (6-16 false alarms/h); sliding 2 s windows 0.33 with 130-240 false alarms/h; reservoir
network 0.49-0.52 with 240-300 false alarms/h. Their random forest on 96 statistics: 0.91 on a seen person, 0.61 on a
new person; +3-5 own takes from the new person: +10 points (0.82; 0.94 with jaw dropped, on clips). Accuracy rose
~7 points per added training person (1: 0.57, 2: 0.65, 3: 0.72). Our conclusion: clip accuracy hides detection and
rejection; evaluate on streams with false alarms per hour.

C2. Head frame + R feature screening. lme4 per feature (z-scored): feature ~ gesture + (1|person) +
(1|person:gesture) on EarSet (30 people, in-ear IMU, nod/shake/tilt, 2035 gesture events, 100 parametric bootstrap
draws). Keep rule (written AFTER seeing EarSet): gesture share >= 0.30, >= 2x(person+style), lower CI of gesture >
upper CI of person+style. Kept: share_x 0.98, share_z 0.93, share_y 0.90 (person+style <= 0.06). Rejected:
linearity (gesture 0.24), speed/size (person 0.34-0.44), signed features (gesture ~0, style 0.30-0.45; EarSet has no
direction labels). EarSet -> our AirPods (one person, P01 = the developer): 21/21 with axis features.

C3. Loop feature fix. Old: 0.5*sum(shoelace cross) / sum(u^2+w^2) = pi/N for a perfect circle (depended on length
and rate). First fix tried: divide by MEAN(u^2+w^2) -> one-axis motions scored up to 3.6 (thin loops near the origin).
Final: signed enclosed area / (pi * max(u^2+w^2)) = 1.0 for a circle at any length/rate; P01 circles median
0.28-0.44, one-axis motions max 0.28 (medians 0.05-0.19). Rules: max axis share >= 0.6 -> nod/tilt/turn; else
|loop| >= 0.15 -> circle; else none (threshold set on P01).

C4. Two-motion commands. Real fast doubles (same motion twice, 4 earlier participants, 290 doubles): 84-89 %
merged into ONE detected event. Commands stitched from P01's real single motions with an inserted still pause:
command accuracy (Rules) 0.30 at 0.1 s, 0.77 at 0.3 s, 0.88 at 0.5 s, 0.88 at 0.8 s. Decision: instruct a short
still pause (~0.5 s) between the two motions; later, cut merged cross pairs where the dominant rotation axis
changes (cannot work for same-axis pairs like tilt L -> tilt R). No real recorded cross pairs exist yet.

C5. Personalisation experiment (EarSet, leave one person out, k earliest own trials per gesture, test = their
remaining gestures + all their no-gesture events; app gate). Gesture-only features: k=0 0.958 gestures right,
11.8 % of no-gesture events wrongly accepted; k=5 weighted x5: 0.973 / 12.0 %. Adding raw magnitude features: k=0
0.973 / 3.6 %; k=5: 0.980 / 3.7 %. Magnitude features normalised by the person's median over own enrollment trials:
0.970-0.981 / 4.5-5.6 %. Conclusions: personal trials add only 1-1.5 points here; raw speed/size help gesture-vs-
non-gesture for everyone; making them person-relative removes that. Caveat: enrollment and test from the same
2-minute recording.

C6. Cross-device check (train all 30 EarSet people, test P01 AirPods Pro 2: 44 motions nod/turn/tilt, 23
no-gesture events). Gesture-only: 40/44 right, 5/23 no-gesture accepted. +magnitude: 43/44, 6/23. Medians differ:
P01 peak rotation 1.1-1.7x EarSet; n_cycles 0.5 vs 1.5-2 (EarSet repeats gestures continuously); acc_per_rot tilt
0.77 vs 2.1. Decision: keep the app on gesture features for the pilot; after the pilot retrain on AirPods data and
add only peak/rms speed and duration (not n_cycles, acc_per_rot).

C7. Body turn vs head turn (walking). Rigid head: a_ear = a_body + alpha x r + omega x (omega x r). Fitting r on half
of P01's seated trials: r = 8.6 cm lateral; on the other half rotation explains 91-92 % of acceleration variance in
turns (nods 0.13-0.26). Plan: residual acceleration = body motion -> stricter detection while walking, off while
running; plus net heading change from the quaternion (gesture returns, body turn does not).

C8. Experimental design (pilot v3, protocol as a JSON "experiment file" the app reads). 20 people (5 team + 15),
each on AirPods Pro 2 and AirPods 5 (crossover by participant number), Mac or iPhone. Session: calibration +
practice; core (enrollment 2 rounds, sitting 6 rounds, small 2 rounds counterbalanced with sitting, 10 commands, 5
own-pace commands, 8 min no-gesture split early/late); optional modules rotated by a Williams square (re-wear,
speed/size, posture, walking with corners, pairs at set pauses, daily-life no-gesture), re-wear or posture required,
modules tracked per device. Hypotheses: H1 head frame removes person/device bias, H2 commands work on new people
without personal training, H3 variable-length detection beats fixed windows, H4 small motions keep accuracy, H5
screened physics features transfer as well as MiniRocket, H6 false commands rare. Analysis: settings frozen (git
tag) before P02; leave-one-person-out and cross-device both directions; R screening per confusable pair with >=500
bootstrap draws, device as fixed effect; logistic mixed model correct ~ method*device + condition + (1|person), no
McNemar; zero false commands reported with a rule-of-three upper bound. Stages: P01 self-test -> pilot (5 people) ->
main round with a frozen file.

C9. Teammates' demo (iPhone app + tracker_server: callsign, commander map, position from step counting, gesture ->
message, spoken instructions). Their log shows double-gesture classes (NOD_2X_FRONT 70 %, TILT_2X_LEFT 52-70 %,
JAW_CLENCH_DOUBLE 51 %). Our assessment: strong operations layer we lack; but a demo by a person in the training
set with 51-70 % confidences and no record of misses or false triggers does not measure new-person accuracy or false
commands. Proposal: two layers - their app/hub for operations, our recogniser + evaluation for recognition; test
their classifier as a baseline on our pilot streams.

## What to answer
For each claim C1-C9: verdict (SOUND / PARTLY / WRONG), the strongest objection or alternative explanation, and
the cheapest check or fix. Then: (a) the 3 biggest logical errors or overclaims across all of it, (b) anything
statistically invalid, (c) what you would change in the pilot design before data collection starts.
Be concrete and concise (under 900 words). Plain text or markdown.


## 4. GPT (byteask, gpt-6.1-sol), verbatim

The stream-first direction is sound. The main weaknesses are extrapolating from developer data, treating synthetic pairs as command validation, and interpreting acceleration residuals as body motion.

**C1 — SOUND.** Clip accuracy omits segmentation, rejection and command decoding. Objection: differing datasets, matching rules and thresholds prevent attributing every gap to continuous operation; three training-person counts do not establish a learning curve. Cheapest check: replay identical held-out streams through all methods with one event-matching rule. Reconcile “0.61 +10 points = 0.82.”

**C2 — PARTLY.** Axis shares are plausible transferable features; the screening is exploratory. Gesture is a fixed effect, so “gesture variance share” needs an explicit definition and denominator. Person×gesture variation need not represent style alone. Missing direction labels make signed-feature rejection uninformative for your eight classes. Cheapest fix: freeze screening now, validate on independent people with direction labels, and ablate head-frame alignment. Orthogonalise and normalise the calibrated axes. P01’s 21/21 establishes feasibility only.

**C3 — PARTLY.** The final normalisation removes the original sample-count scaling, but “1 at any length/rate” is too strong: polygon area approximates continuous area; multiple traversals accumulate signed area, and self-intersections cancel. The reported feature ranges overlap, although the preceding axis gate might resolve that overlap. Cheapest check: resample identical trajectories, vary cycle count, and inspect confusion after the complete rule cascade on held-out people.

**C4 — PARTLY.** A deliberate pause is a defensible interaction constraint. However, repeated identical motions do not establish how different motions merge, and stitching excludes real transitions, anticipation and head-position changes. A 0.5-second pause barely exceeds the detector’s 0.4-second quiet requirement. Cheapest fix: record real pairs across several people, including opposite directions on one axis; measure achieved pauses, command accuracy and latency. Define “first’s end” consistently between ground truth and decoder.

**C5 — PARTLY.** The measured improvements are small; “magnitude helps everyone” is unsupported by pooled averages. Normalisation might remove useful separation or introduce noisy estimates. Same-recording enrollment supports within-session adaptation only. Cheapest check: show participant-level paired differences and uncertainty; enroll in one session, test after re-wear or another day. Specify how personalised normalisation works at k=0.

**C6 — PARTLY.** Keeping the simpler representation pending pilot evidence is reasonable. One developer cannot distinguish device shift from person, execution or recording-protocol differences. Three extra correct gestures and one extra false acceptance are inconclusive. Cheapest fix: paired device recordings from several people with matched instructions; select magnitude features using training participants only.

**C7 — WRONG as an inference.** The equation describes points on one rigid body; head and torso articulate. Its reference-point acceleration is not automatically body acceleration ([rigid-body equations](https://mechref.engr.illinois.edu/dyn/rkg.html)). Residuals also include model error, changing rotation centres and sensor processing. High seated variance explained cannot validate walking discrimination. Head gestures need not return; body turns can reverse. Cheapest check: record head-only, body-only and combined turns with torso-phone/video ground truth. Treat both proposed cues as hypotheses.

**C8 — PARTLY.** Freezing settings, crossover and participant-held-out evaluation are good foundations. Six hypotheses plus optional modules exceed what 20 people can establish convincingly; optional participation creates selection bias. H1 “removes bias” and H5 “as well as” require explicit estimands and equivalence margins. Cheapest fix: prioritise command success and false commands/hour; make essential conditions mandatory and standardised. Define whether the five-person pilot contributes to confirmatory analysis.

**C9 — SOUND.** Operational integration and recognition evidence are separate contributions. Confidence scores are neither accuracy nor necessarily calibrated; their numerical size alone proves little. Cheapest check: run both frozen recognisers on identical labelled streams, preserving misses, false triggers, latency and command outputs.

**(a) Three biggest overclaims**

1. P01 and same-session results establish generalisation across people, devices and re-wears.
2. Synthetic single-motion concatenations validate real command production.
3. Seated acceleration fits identify body motion during walking.

**(b) Statistical problems**

Post-selection bootstrap intervals do not confirm the data-chosen screening rule; 100 draws give unstable tail estimates. Increasing draws cannot remove selection bias. Bootstrap the actual comparison statistic and report fitting failures.

A participant intercept alone misses pairing when methods score the same events: include event/trial pairing and consider participant method slopes or participant-level resampling. McNemar is valid for appropriate paired binary observations; pooling clustered events is the problem ([NIST](https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/mcnemar.htm)).

No-gesture-event acceptance is not false alarms/hour. Zero false commands gives an approximate 95% upper rate of 3/T under a homogeneous Poisson model ([NIST](https://www.itl.nist.gov/div898/handbook/apr/section4/apr451.htm)). Twenty eight-minute recordings total 2.67 hours: approximately **1.12 false commands/hour**, insufficient to establish rarity.

**(c) Before collection**

Freeze event matching, pairing/reset rules, thresholds and analysis; nest feature selection within training folds. Require real pairs, re-wear and representative negatives on both devices. Balance device order and platform; record earbud side, fit and timestamps. Increase negative exposure according to a prespecified acceptable rate. Separate calibration from labelled personal training. Report participant-level command success, false commands/hour, rejection and latency; add workload, comfort and perceived conspicuousness for the covert-use claim.

## 5. Gemini (agy, gemini-3.8-flash-high), verbatim

﻿### Claim-by-Claim Verdicts (C1–C9)

* **C1. Continuous stream vs. clips**  
  * **Verdict:** **SOUND**  
  * **Strongest Objection:** Comparing a fixed 2 s sliding window to an adaptive hysteresis detector conflates segmentation architecture with stream evaluation; windowing may have failed due to unoptimized stride/NMS rather than stream dynamics.  
  * **Cheapest Check/Fix:** Report full Precision-Recall / FA-per-hour curves across detection thresholds for both sliding windows and hysteresis on the same stream.

* **C2. Head frame + R feature screening**  
  * **Verdict:** **PARTLY**  
  * **Strongest Objection:** **Severe HARKing and methodological disconnect.** Feature retention thresholds were chosen *after* inspecting EarSet. Crucially, rejecting signed features because EarSet (which lacked direction labels) showed low gesture variance is invalid when distinguishing directional gestures (nod down vs. look up, turn L vs. R). Furthermore, 21/21 on P01 reflects developer movement bias.  
  * **Cheapest Check/Fix:** Screen signed features explicitly on directional data (e.g., teammate recordings); freeze retention criteria prior to pilot analysis.

* **C3. Loop feature fix**  
  * **Verdict:** **PARTLY**  
  * **Strongest Objection:** $\max(u^2+w^2)$ in the denominator is hypersensitive to single-axis jerk or noise spikes, which suppresses true circle scores. The threshold (0.15) is uncomfortably close to one-axis medians (0.05–0.19) and below one-axis max (0.28), inviting false positives if max axis share dips below 0.6.  
  * **Cheapest Check/Fix:** Replace max radius with 95th percentile radius or trajectory covariance eigenvalues; evaluate separation margin on multi-axis non-circular movements.

* **C4. Two-motion commands**  
  * **Verdict:** **WRONG**  
  * **Strongest Objection:** **Synthetic stitching invalidates interaction dynamics.** Real human compound gestures exhibit co-articulation, momentum, and continuous head transitions. Forcing an unnatural 0.5 s "freeze" violates the core requirement for *covert, fast* tactical communication. Cutting merged pairs by rotation axis change fails completely for opposite-direction gestures on the same axis (e.g., Tilt L $\rightarrow$ Tilt R).  
  * **Cheapest Check/Fix:** Record 20 real, unstitched cross-pairs across 2 participants to verify whether zero-crossing/velocity troughs naturally segment them without artificial pauses.

* **C5. Personalisation experiment**  
  * **Verdict:** **PARTLY**  
  * **Strongest Objection:** **Temporal and re-wear leakage.** Enrollment and test sets came from the exact same 2-minute recording block. This measures intra-session consistency, not true user adaptation across earbud re-insertions, postural shifts, or time.  
  * **Cheapest Check/Fix:** Split enrollment and test sets across distinct recording runs separated by removing and reseating the earbud.

* **C6. Cross-device check**  
  * **Verdict:** **SOUND**  
  * **Strongest Objection:** $N=1$ (P01) test set is insufficient to claim cross-device transfer. Differences in Apple IMU firmware filtering, sample rate jitter, and ear-canal coupling could behave unpredictably across diverse head geometries.  
  * **Cheapest Check/Fix:** Verify sampling rate regularity and axis frame alignment on 2 additional non-developer subjects before freezing features.

* **C7. Body turn vs. head turn (walking)**  
  * **Verdict:** **SOUND**  
  * **Strongest Objection:** Seated rigid-body kinematic fitting ($r = 8.6\text{ cm}$) breaks during walking; periodic heel-strike impacts (1–2 Hz shockwaves up the spine) produce high residual accelerations that will trigger false "body motion" gating and suppress real gestures.  
  * **Cheapest Check/Fix:** Run residual acceleration computation on a 60-second walking stream without gestures to ensure gait transients do not falsely mute the detector.

* **C8. Experimental design (pilot v3)**  
  * **Verdict:** **SOUND**  
  * **Strongest Objection:** 8 minutes of sitting no-gesture per person is drastically underpowered for measuring False Alarms per Hour (FA/h). In addition, including 5 team members in a 20-person cohort introduces severe user bias.  
  * **Cheapest Check/Fix:** Mandate 30–60 minutes of passive daily-activity streaming per participant, and segregate team members into a separate pilot/feasibility stratum.

* **C9. Teammates' demo & two-layer proposal**  
  * **Verdict:** **SOUND**  
  * **Strongest Objection:** Integration risk. Bridging an unfamiliar network/UI stack with a new causal recognition engine right before a frozen pilot risks hard-to-trace latency jitter or socket drops affecting 50 Hz temporal alignment.  
  * **Cheapest Check/Fix:** Formalize an asynchronous IPC/socket contract with timestamped payload logging, testing both pipelines offline on identical pre-recorded raw sensor streams.

---

### (a) Top 3 Logical Errors / Overclaims

1. **Synthetic Double Gestures Substituted for Real Interaction (C4):** Assuming that stitching single gestures with artificial silence reflects real user execution is a fatal design flaw. It ignores muscle inertia, transitional trajectories, and tactical usability.
2. **Circular Tuning on Developer P01 (C2, C3, C6, C7):** Nearly every key decision (thresholds, loop normalizer, kinematic radius $r$, cross-device sanity) was tuned and verified on the developer. This guarantees overfitting to P01's idiosyncratic kinematics.
3. **Discarding Directional Features Using Unlabeled Data (C2):** Discarding signed features based on an ANOVA on EarSet—a dataset that lacked direction labels—is fundamentally fallacious when the target lexicon explicitly relies on directional pairs.

---

### (b) Statistical Invalidation

1. **Post-Hoc Screening (HARKing):** Establishing feature retention rules ($\ge 0.30$ gesture share, lower CI $>$ upper CI) *after* examining the EarSet variance components invalidates nominal confidence intervals and statistical tests.
2. **Zero-Event Rule-of-Three Fallacy:** With only 8 min of no-gesture data across 20 participants (~2.67 hours total), zero false commands yields a 95% upper bound of $3 / 2.67 \approx 1.12\text{ FA/hour}$—far too loose to claim false commands are "rare" in covert operations.
3. **Session Auto-Correlation in Personalization (C5):** Drawing $k$-enrollment and test sets from the same continuous 2-minute recording violates sample independence, dramatically exaggerating classifier stability.

---

### (c) Immediate Pilot Design Modifications

1. **Capture Real Compound Pairs:** Remove synthetic stitching; record natural, unpaused cross-pairs to train segmentation on actual inter-gesture dynamics.
2. **Quarantine Team Data:** Analyze the 5 team members separately from the 15 naive subjects to ensure unbiased generalizability metrics.
3. **Expand Negative Streaming:** Extend passive no-gesture recording to at least 30 minutes per subject (talking, walking, working) to establish statistically defensible FA/h estimates.
4. **Pre-Register Decision Thresholds:** Freeze all detector, loop, and classification thresholds via git commit before touching any P02+ data.
