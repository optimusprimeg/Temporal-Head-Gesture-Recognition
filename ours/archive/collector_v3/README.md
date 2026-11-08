# Collector v3

Continuous recording with audio cues and a cue log. Only Python's standard library is needed (no Flask).
Design and reasons: `../experimental_design.md`.

## What changed from `collector_100hz.py`

| Old | New |
|---|---|
| records 2.5 s after each cue, then stops | records the **whole session** without stopping |
| 25 takes of one gesture in a row | **shuffled rounds**: every motion once per round, random order, 2 idle cues |
| fixed 2.5 s, longer gestures cut off | 4 s window after the beep only marks where to look; nothing is cut |
| gaps between takes lost | gaps kept: real "nothing happening" data, real boundaries |
| double gestures (tilt ×2, nod ×2) | **single** motions; commands are pairs (first, then) |
| no calibration, no negatives | calibration nods, re-wear, posture/speed blocks, commands, no-gesture block |
| timestamps went through Excel | integer nanoseconds, written by code only |

## Run

1. iPhone and PC on the same Wi-Fi. In Sensor Logger: enable **Headphone motion**, HTTP push to the URL the
   collector prints (`http://<PC IP>:8000/data`). Allow Python through the Windows firewall if asked.
2. AirPods in, then:

```
python collector_v3.py --plan pilot                          # team of 5, about 40 min
python collector_v3.py --plan main --device "AirPods Pro 2"  # everyone, about 50 min per session
```

It asks for subject ID, device and a few metadata fields, waits until the stream arrives (shows the rate,
expect about 50 Hz), then walks through the blocks. Press Enter to start each block. Ctrl+C stops at any
time and keeps everything recorded so far.

Dry run without a phone: `python collector_v3.py --plan main --simulate --fast 20 --auto`

## Cues

Low beep = get ready (motion name on screen), high beep = do it now, double low beep = block/activity ends.
One cue = one single motion, done once, then back to neutral. The participant should be able to read the screen,
or the experimenter reads the motion name aloud.

## Plans (edit in `config.py`)

| Plan | Blocks | Length | Takes per motion |
|---|---|---|---|
| `pilot` | calibration, 15 rounds sitting, 1 small, 1 slow, 12 back-to-back pairs (0.3/0.6/1.0 s gaps), 10 min no-gesture | ~40 min | 17 |
| `main` | calibration, 3 enrollment rounds, 8 rounds, re-wear + calibration, 8 rounds, 2 standing, 2 walking in place, 2 head pre-turned, slow, fast, small, 10 cued commands, 2 self-paced lists of 5 commands (no beeps), 8 min no-gesture | ~52 min cue time, ~60 min total with 8 motions (~50 with 6) | 28 (56 over 2 sessions) |

Lengths were measured on simulated dry runs (cue time only); setup and breaks add about 8 min.
After the pilot: put the chosen motions in `MAIN_MOTIONS` and the 20 chosen pairs in `COMMANDS`.

## Output: `../data/raw_v3/<subject>/<date>_<plan>_<device>_<time>/`

| File | Content |
|---|---|
| `stream.csv` | `sensor_ns` (phone clock, per sample), `host_ns` (PC clock when its batch arrived), 16 channels: yaw, pitch, roll, quatX-W, rotX-Z, accX-Z (m/s²), gravX-Z (m/s²) |
| `cues.csv` | per cue: `host_ns` at the **start** of the GO beep, `sensor_ns_est` (same moment on the phone clock), block, kind, round, trial, step (pairs: 1/2), motion (commands: `first>then`), condition, window_s, note |
| `activities.csv` | no-gesture block: start/end per activity, PC clock and phone clock |
| `gaps.csv` | stream drops (no data for > 1.5 s), start/end on the PC clock |
| `session.json` | subject, device, plan, seed, metadata, vocabulary, commands, completed, samples, rejected entries, clock offset |

**Aligning cues and samples:** use the phone clock. Sensor Logger sends samples in batches, so `host_ns` of a
sample is late by up to one batch. The collector keeps `offset = min(host_ns − sensor_ns)` (the fastest batch,
i.e. clock difference + smallest delay) and writes `sensor_ns_est = cue host_ns − offset`. Sort `stream.csv` by
`sensor_ns` first (batches can be written slightly out of order).

**Safety:** a malformed entry is rejected on its own (counted in `session.json`), the rest of the batch is kept;
chunked uploads work; a busy port stops before creating a folder; a stream drop prints a warning and is logged in
`gaps.csv`; Ctrl+C at any point writes `session.json`. Never open these files in Excel and save them.
