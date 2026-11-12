# Experiment files for Gesture Collector

Copy this whole folder's contents into the app's data folder, inside `experiments/` (Mac: the start screen's
**Open** button shows the data folder; iPhone: Files > On My iPhone > Gesture Collector > experiments), then press
**Reload experiment files** and pick one on the start screen.

| File | What | Per round |
|---|---|---|
| `v5.json` | the teammates' collector_v5 set: 23 gestures + 4 short idles in random rounds, then 3 x 60 s idle | ~3.5 min |
| `v5_plus.json` | v5 + 1x versions (half the reps) + extra gestures + near-miss cues + modules | ~6 min |
| `micro_v1.json` | the earlier 16-motion micro set | ~3 min |
| `media/*.gif` | a cartoon demo clip per motion id (keep the folder name `media`) | |

The first session of a person has a WATCH + practice step per motion (v5: ~27, v5_plus: ~51 motions), so plan
the first session at 30 min or more for v5 and 45 min or more for v5_plus.
After a session: `python ours/algorithm/scripts/app_to_v5_csv.py <session.zip> --subject S07` gives a
collector_v5-format CSV; `review_session.py <session.zip>` gives a report.
Files are generated: edit `algorithm/scripts/make_v5_experiments.py` / `make_gesture_clips.py` and run them again.
