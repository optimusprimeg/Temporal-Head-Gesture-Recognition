# Why we changed the approach (for the team)

The earlier pipeline (Sensor Logger + 2.5-second clips + a classifier on 96 statistics, in
`prior_work/gesture_lab`) was real, careful work, and its own reports are what showed us where to go next.
This note explains the change in plain terms, with the numbers from those reports.

## 1. In real use, nobody tells the system when a gesture starts

In the old set-up, every recording was a 2.5 s clip cut around a gesture we *knew* was there. The classifier only
had to answer "which of these 8 gestures is in this clip?"

A real user wears the AirPods for an hour. The system hears a **continuous stream** and must decide by itself:
1. **Is there a gesture at all**, or is the person talking, eating or looking around?
2. **Where does it start and end?** Gestures last 0.5 to 4 s, not exactly 2.5 s.
3. **Which gesture is it?**

The old test measured only step 3, the easiest one. That is why we record and evaluate on continuous streams.

### What happened when the old pipeline met a stream (its own report, `08_analysis_and_plan.md`)

| Same data, same models | Gestures found and named | False alarms per hour |
|---|---|---|
| Cut clips (the usual test), MiniRocket | 0.72 accuracy | not measurable on clips |
| Stream, live receiver + MiniRocket | **0.39-0.43** | 6-16 |
| Stream, sliding 2 s windows | 0.33 | **130-240** |
| Stream, reservoir network (ESN) | 0.49-0.52 | 240-300 |

A model that scores 0.72 on clips finds and names fewer than half the gestures in a stream. Sliding fixed windows
give a false alarm every 15-30 seconds. **The clip number hides the hardest part of the problem.** Our pipeline
starts from the stream: a detector finds motions of any length, then they are named, then the false alarm rate
is measured on real no-gesture time.

## 2. A model trained on some people must work on a new person

| | Accuracy |
|---|---|
| Old random forest, a person it has seen | 0.91 |
| Same model, a **new** person | **0.61** |

The 96 statistics mostly described *how each person moves*, not *which gesture* it was. We changed two things:
- **Head frame.** The signal is rotated into the head's own axes (nod, tilt, turn) using gravity and three
  calibration nods, so the same motion looks the same for everyone, whatever the earbud angle in the ear.
- **Features chosen by statistics.** An R mixed model splits each feature's variation into gesture, person,
  style and noise. Only gesture-driven features are trusted across people: the axis shares are 0.90-0.98
  gesture, while speed and size are mostly person.

Result so far: a model trained only on 30 *other* people with a *different* earbud (EarSet) recognised all 21 of
Ghanshyam's AirPods motions it covers (nod, turn, tilt). One person, so not proof, but the direction is right.

## 3. Commands made of two simple motions

The old design had 20 separate gesture classes. Each new command needed new training data, and every single
gesture could be triggered by accident.

Now: 8 simple motions, and a **command = two different motions in a row** (second within 1.5 s).
- One stray nod or turn never sends a command.
- 8 motions give 56 possible commands without new data.
- The dictionary is private to the team and can change any time.

## 4. Why a data-collection app instead of Sensor Logger

Sensor Logger records, but it does not run a protocol: no spoken cues, no timing log on the same clock, no
no-gesture blocks, no walking, no re-wear, no device crossover, no live check that a trial was done right, and its
axes are flipped compared with Apple's raw data. The Gesture Collector app (Mac and iPhone) does all of that and
saves one folder per session that the analysis reads directly.

## 5. What we kept from the earlier work

- **Personal enrollment** was their biggest win (+10 points with 3-5 own trials). Our sessions record enrollment
  rounds so we can measure the same curve.
- **MiniRocket (0.72)** and **their random forest** stay as baselines; our method must beat them on the same splits.
- **"Idle" as a class** beat a confidence threshold in their tests. Our model has a "not a gesture" class.
- **Their 4-person data** is still used: it showed that fast double gestures merge into one event in a stream
  (84-89 %), which is why commands now ask for a short pause between the two motions.
- **The jaw-clench finding** (barely visible in rotation) is why jaw is not in the vocabulary.

## 6. What is not shown yet

Command accuracy on new people, false commands in real conversation and while walking, and covertness. The
pilot (5 people) measures these. If our approach does not beat the baselines on the same data, we will say so.
