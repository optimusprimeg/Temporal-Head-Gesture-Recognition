"""
Gesture data collector v5 - AirPods IMU via Sensor Logger HTTP Push (CS724 Group 6)

Simple flow, as in v2/v3: pick a gesture by number, one take is recorded, progress shows N/20.
  * No 3-2-1 countdown: instruction + "get ready" (~2 s), HIGH beep + red RECORDING banner,
    3 s window, double LOW beep. Then back to the list; press Enter to repeat the same gesture.
  * Ctrl+C during a take cancels it (nothing saved). [d] deletes the last saved take.

Kept from v4 (technical fixes)
  * Windows cut on the PHONE's sample timestamps (monotonic PC clock for the beep mapping),
    0.5 s pre-roll / 1.0 s post-roll, waits for late HTTP batches.
  * Quality checks per take (coverage, gaps, earbud side, no movement, moved during still,
    head moved during face gestures). Bad takes are saved with a 'bad:...' flag and do not count.
  * RIGHT AirPod only (REQUIRED_SIDE), checked at startup and on every take.
  * Robust HTTP parsing (iPad and iPhone), live diagnostics while waiting for the stream,
    browser check at http://<PC-IP>:8000/data, refuses to start if port 8000 is already in use.
  * Subject ID in the dataset; optional name only in sessions.csv.
  * Timestamps are integer nanoseconds: do NOT open and re-save the CSV in Excel.

Gesture set (2026-11-11): 7 head, 8 face, 8 face combos (two gestures, once each), 4 idle,
  3 continuous idle (60 s). smile_2x, molar_tap_2x, jaw_clench_double and jaw_right_then_eyebrow
  are weak/marginal: recorded now, kept or trimmed later on validation results.

Phone/iPad (Sensor Logger): enable only Headphone; Data Streaming > HTTP Push ON with the URL shown
  at startup; Settings > Privacy & Security > Local Network > Sensor Logger ON; start recording.
PC: pip install flask ; python collector_v5.py
"""
import csv
import json
import logging
import math
import os
import random
import sys
import threading
import time
from collections import deque

from flask import Flask, request

VERSION = "5.0"

# ------------------------------------------------------------------ configuration
PORT = 8000
REQUIRED_SIDE = "right"        # every subject records with the RIGHT AirPod only (None = any side)
FS = 50.0                      # AirPods headphone motion rate
PRE_ROLL_S = 0.5               # saved before the start beep (in_window = 0)
POST_ROLL_S = 1.0              # saved after the window end (in_window = 0)
LATE_WAIT_MAX_S = 4.0          # max wait for late HTTP batches after a take
READ_S = 2.0                   # gesture chosen -> start beep (time to read and get ready)
READ_S_NEW = 3.0               # same, while a gesture has < 2 good takes for this subject

# quality checks
MIN_COVERAGE = 0.90            # >= 90 % of expected samples inside the window
MAX_GAP_S = 0.20               # largest tolerated gap inside a short window
MAX_GAP_LONG_S = 1.00          # largest tolerated gap inside a continuous idle window
LOW_MOTION_DPS = 1.8           # gesture below this gyro RMS -> bad (idle-still is ~0.8)
LOW_MOTION_EXEMPT = {"smile_2x", "molar_tap_2x", "jaw_clench_double"}   # naturally ~1-2 deg/s
STILL_MAX_DPS = 3.0            # idle 'still' above this -> bad (subject moved)
HEAD_STILL_MAX_DEG = 20.0      # face/combo take whose orientation moves more -> bad (head moved)

# beeps (Hz, ms)
BEEP_START = (1500, 150)
BEEP_END = (600, 120)          # played twice
BEEP_DISCARD = (350, 350)

# label, group, instruction, window s, target good takes per subject
GESTURES = [
    ("tilt_2x_left",                "head",  "Quick double head tilt to the LEFT (ear to shoulder)",  3.0, 20),
    ("tilt_2x_right",               "head",  "Quick double head tilt to the RIGHT (ear to shoulder)", 3.0, 20),
    ("nod_2x_front",                "head",  "Quick double nod FORWARD",                              3.0, 20),
    ("circle_cw",                   "head",  "One brisk head circle CLOCKWISE (~2 s)",                3.0, 20),
    ("circle_ccw",                  "head",  "One brisk head circle COUNTER-CLOCKWISE (~2 s)",        3.0, 20),
    ("rotate_left_chin_down",       "head",  "Turn head LEFT, then dip chin down",                    3.0, 20),
    ("rotate_right_chin_down",      "head",  "Turn head RIGHT, then dip chin down",                   3.0, 20),
    ("mouth_open_2x",               "face",  "Open mouth wide twice (head still)",                    3.0, 20),
    ("puff_cheeks_2x",              "face",  "Puff both cheeks twice (head still)",                   3.0, 20),
    ("jaw_shift_left_right",        "face",  "Slide jaw LEFT, then RIGHT, back to centre",            3.0, 20),
    ("smile_2x",                    "face",  "Closed-mouth smile, both sides, twice",                 3.0, 20),
    ("molar_tap_2x",                "face",  "Tap back teeth together twice (quick, firm)",           3.0, 20),
    ("jaw_forward_2x",              "face",  "Push lower jaw FORWARD twice",                          3.0, 20),
    ("jaw_clench_double",           "face",  "Clench back teeth firmly twice",                        3.0, 20),
    ("eyebrow_up_down_2x",          "face",  "Raise eyebrows and lower them, twice (head still)",     3.0, 20),
    ("eyebrow_then_mouth_open",     "combo", "Eyebrows up-down ONCE, pause ~1 s, open mouth wide ONCE", 3.0, 20),
    ("mouth_open_then_eyebrow",     "combo", "Open mouth wide ONCE, pause ~1 s, eyebrows up-down ONCE", 3.0, 20),
    ("eyebrow_then_puff_cheeks",    "combo", "Eyebrows up-down ONCE, pause ~1 s, puff cheeks ONCE",     3.0, 20),
    ("mouth_open_then_puff_cheeks", "combo", "Open mouth wide ONCE, pause ~1 s, puff cheeks ONCE",      3.0, 20),
    ("puff_cheeks_then_eyebrow",    "combo", "Puff cheeks ONCE, pause ~1 s, eyebrows up-down ONCE",       3.0, 20),
    ("jaw_left_then_eyebrow",       "combo", "Slide jaw LEFT and back ONCE, pause ~1 s, eyebrows up-down ONCE", 3.0, 20),
    ("eyebrow_then_jaw_left",       "combo", "Eyebrows up-down ONCE, pause ~1 s, slide jaw LEFT and back ONCE", 3.0, 20),
    ("jaw_right_then_eyebrow",      "combo", "Slide jaw firmly RIGHT, hold briefly, back; pause ~1 s; eyebrows up-down ONCE", 3.0, 20),
]
# short idle takes
IDLE_VARIANTS = [
    ("still",   "Sit still, breathe normally",                  10),
    ("talk",    "Talk naturally (count aloud, read something)", 10),
    ("chew",    "Chew (gum or pretend)",                        10),
    ("swallow", "Swallow ONCE, otherwise still",                10),
]
IDLE_WINDOW_S = 3.0
# continuous idle: one long take each (for false-trigger tests)
CONT_IDLE = [
    ("still_long", "Sit relaxed and still, look at the screen",        60.0, 1),
    ("talk_long",  "Talk naturally the whole time (read aloud, chat)", 60.0, 1),
    ("chew_long",  "Chew gum (or pretend) the whole time",             60.0, 1),
]

SENSOR_COLS = ["yaw", "pitch", "roll", "quatX", "quatY", "quatZ", "quatW",
               "rotX", "rotY", "rotZ", "accX", "accY", "accZ", "gravX", "gravY", "gravZ"]
COLUMNS = (["timestamp_ns", "t_rel_s", "in_window"] + SENSOR_COLS +
           ["sensor_location", "label", "group", "idle_variant", "take_id", "rep", "subject_id",
            "session_id", "device", "window_s", "beep_phone_ns", "n_in_window", "coverage",
            "max_gap_s", "side_switch", "quality", "gyro_rms_dps", "orient_range_deg",
            "round_no", "pos_in_round", "collector_version"])
FIELD_MAP = {"yaw": "yaw", "pitch": "pitch", "roll": "roll",
             "quatX": "quaternionX", "quatY": "quaternionY", "quatZ": "quaternionZ", "quatW": "quaternionW",
             "rotX": "rotationRateX", "rotY": "rotationRateY", "rotZ": "rotationRateZ",
             "accX": "accelerationX", "accY": "accelerationY", "accZ": "accelerationZ",
             "gravX": "gravityX", "gravY": "gravityY", "gravZ": "gravityZ"}


# ------------------------------------------------------------------ specs
def make_specs():
    specs = []
    for lab, grp, ins, win, tgt in GESTURES:
        specs.append(dict(key=lab, label=lab, group=grp, variant="", instruction=ins,
                          window=win, target=tgt, long=False))
    for v, ins, tgt in IDLE_VARIANTS:
        specs.append(dict(key=f"idle:{v}", label="idle", group="idle", variant=v, instruction=ins,
                          window=IDLE_WINDOW_S, target=tgt, long=False))
    for v, ins, win, tgt in CONT_IDLE:
        specs.append(dict(key=f"idle:{v}", label="idle", group="idle_cont", variant=v, instruction=ins,
                          window=win, target=tgt, long=True))
    for s in specs:
        s["title"] = (s["label"] if s["label"] != "idle" else f"idle - {s['variant']}").replace("_", " ").upper()
    return specs


SPECS = make_specs()

# ------------------------------------------------------------------ phone stream (HTTP)
logging.getLogger("werkzeug").setLevel(logging.ERROR)
app = Flask(__name__)
lock = threading.Lock()
samples = deque(maxlen=int(FS * 180))        # last 3 minutes: (phone ns, row dict)
offsets = deque(maxlen=400)                  # arrival_pc_ns - newest_sample_phone_ns, per batch
stats = {"packets": 0, "samples": 0, "last_arrival": 0.0, "max_t": 0}
diag = {"posts": 0, "unreadable": 0, "names": {}, "saved": 0, "first_from": "", "ping_from": ""}
DEBUG_FILE = "push_debug.txt"                # first raw HTTP bodies, for troubleshooting


def now_ns():
    return time.perf_counter_ns()            # monotonic, high resolution (QPC on Windows)


def side_of(entry, vals):
    for src in (vals, entry):
        for k in ("devicelocation", "deviceLocation", "sensorLocation", "location"):
            if k in src and src[k] not in (None, ""):
                return str(src[k]).lower()
    return "unknown"


def to_ns(v):
    """Sample time to integer ns; accepts ns, us, ms or s (int, float or string)."""
    if isinstance(v, bool):
        raise ValueError
    if isinstance(v, int):
        t = v
    else:
        try:
            t = int(str(v).strip())
        except ValueError:
            t = float(v)
    if t < 1e11:          # seconds
        return int(t * 1_000_000_000)
    if t < 1e14:          # milliseconds
        return int(t * 1_000_000)
    if t < 1e17:          # microseconds
        return int(t * 1_000)
    return int(t)


def ingest(payload, arrival_ns):
    newest = None
    with lock:
        for e in payload:
            if not isinstance(e, dict):
                continue
            name = str(e.get("name", "headphone")).lower()
            diag["names"][name] = diag["names"].get(name, 0) + 1
            vals = e.get("values")
            if not ("headphone" in name or "airpod" in name) or not isinstance(vals, dict) or "time" not in e:
                continue
            try:
                t_ns = to_ns(e["time"])
            except (TypeError, ValueError):
                continue
            row = {k: vals.get(src, "") for k, src in FIELD_MAP.items()}
            row["sensor_location"] = side_of(e, vals)
            samples.append((t_ns, row))
            newest = t_ns if newest is None else max(newest, t_ns)
            stats["samples"] += 1
        if newest is not None:
            offsets.append(arrival_ns - newest)
            stats["packets"] += 1
            stats["last_arrival"] = time.monotonic()
            stats["max_t"] = max(stats["max_t"], newest)


@app.route("/", methods=["GET"])
@app.route("/data", methods=["GET"])
def ping():
    """Open http://<PC-IP>:8000/data in the phone's browser to test the connection."""
    diag["ping_from"] = request.remote_addr     # shown on the waiting screen (no print from this thread)
    return f"Gesture collector v{VERSION} is reachable. Posts received so far: {diag['posts']}", 200


@app.route("/data", methods=["POST"])
def receive():
    arrival = now_ns()
    raw = request.get_data(cache=False)
    diag["posts"] += 1
    if diag["posts"] == 1:
        diag["first_from"] = request.remote_addr
    if diag["saved"] < 3:                    # keep the first bodies for troubleshooting
        diag["saved"] += 1
        try:
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"--- POST {diag['posts']}  content-type={request.content_type!r}  bytes={len(raw)}\n")
                f.write(raw[:4000].decode("utf-8", "replace") + "\n")
        except OSError:
            pass
    try:
        data = json.loads(raw.decode("utf-8-sig"))      # parse regardless of the Content-Type header
    except (ValueError, UnicodeDecodeError):
        data = request.form.to_dict() if request.form else None
        if data and "payload" in data:
            try:
                data["payload"] = json.loads(data["payload"])
            except ValueError:
                data = None
    if isinstance(data, list):
        payload = data
    elif isinstance(data, dict):
        payload = data.get("payload", [data] if "name" in data else [])
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                payload = []
    else:
        payload = []
        diag["unreadable"] += 1
    ingest(payload if isinstance(payload, list) else [], arrival)
    return "OK", 200


def clock_offset_ns():
    """PC_ns - phone_ns. The smallest observed arrival delay is closest to the true offset."""
    with lock:
        return min(offsets) if len(offsets) >= 5 else None


def stream_ok():
    return stats["packets"] > 5 and time.monotonic() - stats["last_arrival"] < 2.0


def current_side():
    with lock:
        return samples[-1][1]["sensor_location"] if samples else "unknown"


# ------------------------------------------------------------------ sound, screen, keys
try:
    import winsound

    def _tone(f, ms):
        winsound.Beep(f, ms)
except ImportError:
    def _tone(f, ms):
        sys.stdout.write("\a"); sys.stdout.flush(); time.sleep(ms / 1000)


def beep_start():
    _tone(*BEEP_START)


def beep_end():
    _tone(*BEEP_END); time.sleep(0.05); _tone(*BEEP_END)


def beep_discard():
    _tone(*BEEP_DISCARD)


if os.name == "nt":
    os.system("")                              # enable ANSI escape codes in the Windows console
RST, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
GRN, YEL, RED = "\033[92m", "\033[93m", "\033[91m"
REC_BANNER = "\033[41m\033[97m\033[1m      ●  RECORDING      \033[0m"


def clear():
    sys.stdout.write("\033[2J\033[H")



def counts_for(path):
    c = {}
    if not os.path.exists(path):
        return c
    seen = set()
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            k = r["take_id"]
            if k in seen or r.get("quality") != "ok":
                continue
            seen.add(k)
            lab = r["label"] if r["label"] != "idle" else f"idle:{r['idle_variant']}"
            c[lab] = c.get(lab, 0) + 1
    return c


def upgrade_header(path):
    """Rewrite an older CSV so its header matches COLUMNS (missing columns left blank)."""
    if not os.path.exists(path):
        return
    with open(path, newline="") as f:
        rd = csv.DictReader(f)
        if rd.fieldnames == COLUMNS:
            return
        rows = list(rd)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    os.replace(tmp, path)
    print(f"--> Upgraded {path} to the v{VERSION} column layout.")


def last_take_no(path, session):
    """Highest take number already used in this session (normally 0)."""
    n = 0
    if os.path.exists(path):
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                if r.get("session_id") == session:
                    try:
                        n = max(n, int(r["take_id"].rsplit("_", 1)[1]))
                    except (ValueError, IndexError):
                        pass
    return n


def write_rows(path, rows):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerows(rows)
        f.flush(); os.fsync(f.fileno())


def delete_take(path, take_id):
    if not take_id or not os.path.exists(path):
        return False
    with open(path, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["take_id"] != take_id]
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    os.replace(tmp, path)
    return True


def log_session(ctx, name):
    path = "sessions.csv"
    cols = ["session_id", "subject_id", "name", "device", "earbud_side", "collector_version", "started"]
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if new:
            w.writeheader()
        w.writerow({"session_id": ctx["session"], "subject_id": ctx["subject"], "name": name,
                    "device": ctx["device"], "earbud_side": ctx["side"], "collector_version": VERSION,
                    "started": time.strftime("%Y-%m-%d %H:%M:%S")})


# ------------------------------------------------------------------ take analysis
def analyse(spec, t_start_pc, off, cancel_check):
    """Collect samples of one finished take and run the quality checks."""
    start_ph = t_start_pc - off
    end_ph = start_ph + int(spec["window"] * 1e9)
    lo_ph, hi_ph = start_ph - int(PRE_ROLL_S * 1e9), end_ph + int(POST_ROLL_S * 1e9)

    t0 = time.monotonic()
    while time.monotonic() - t0 < LATE_WAIT_MAX_S:          # wait for late HTTP batches
        with lock:
            if stats["max_t"] >= hi_ph:
                break
        cancel_check()
        time.sleep(0.02)

    with lock:
        seg = {t: r for t, r in samples if lo_ph <= t <= hi_ph}   # dict removes duplicates
    seg = sorted(seg.items())
    win = [(t, r) for t, r in seg if start_ph <= t <= end_ph]
    expected = spec["window"] * FS
    coverage = len(win) / expected
    ts = [start_ph] + [t for t, _ in win] + [end_ph]
    max_gap = max(b - a for a, b in zip(ts, ts[1:])) / 1e9
    sides = sorted({r["sensor_location"] for _, r in win})

    def num(r, k):
        try:
            return float(r[k])
        except (TypeError, ValueError):
            return None

    rr = []
    for _, r in win:
        v = [num(r, k) for k in ("rotX", "rotY", "rotZ")]
        if None not in v:
            rr.append(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    gyro_rms = math.degrees(math.sqrt(sum(rr) / len(rr))) if rr else 0.0

    orient = 0.0
    for k in ("yaw", "pitch", "roll"):
        vals = [num(r, k) for _, r in win]
        vals = [v for v in vals if v is not None]
        if len(vals) > 1:
            un, acc = [vals[0]], 0.0                         # unwrap across +-pi
            for a, b in zip(vals, vals[1:]):
                d = b - a
                if d > math.pi:
                    acc -= 2 * math.pi
                elif d < -math.pi:
                    acc += 2 * math.pi
                un.append(b + acc)
            orient = max(orient, math.degrees(max(un) - min(un)))

    problems = []
    if coverage < MIN_COVERAGE:
        problems.append(f"coverage {coverage:.0%}")
    if max_gap > (MAX_GAP_LONG_S if spec["long"] else MAX_GAP_S):
        problems.append(f"gap {max_gap:.2f}s")
    if len(sides) > 1:
        problems.append("earbud switched")
    if spec["label"] != "idle" and spec["label"] not in LOW_MOTION_EXEMPT and gyro_rms < LOW_MOTION_DPS:
        problems.append("no movement")
    if spec["key"] == "idle:still" and gyro_rms > STILL_MAX_DPS:
        problems.append("moved during still")
    if spec["group"] in ("face", "combo") and orient > HEAD_STILL_MAX_DEG:
        problems.append("head moved")

    return dict(spec=spec, seg=seg, start_ph=start_ph, end_ph=end_ph, n_win=len(win),
                coverage=coverage, max_gap=max_gap, sides=sides, gyro_rms=gyro_rms, orient=orient,
                problems=problems, quality="ok" if not problems else "bad:" + ";".join(problems))


# ------------------------------------------------------------------ session runner

def pick(prompt, options):
    while True:
        ch = input(prompt).strip()
        if ch in options:
            return options[ch]


def local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))               # no packet is sent; just picks the LAN interface
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "<PC-IP>"


def serve():
    try:
        app.run(host="0.0.0.0", port=PORT, threaded=True)
    except OSError as e:
        print(f"\n!! Cannot listen on port {PORT}: {e}\n   Close the other collector window and restart.")
        os._exit(1)


def port_in_use():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0



# ------------------------------------------------------------------ one take
def take_screen(ctx, spec, phase, remain=None, note=""):
    clear()
    c, t = ctx["counts"].get(spec["key"], 0), spec["target"]
    out = [f"{DIM}  {ctx['subject']}  ·  {spec['key']}  {c}/{t}{RST}", "", "", "",
           f"     {BOLD}{spec['title']}{RST}", "", f"     {spec['instruction']}", "", ""]
    if phase == "rec":
        out.append("     " + REC_BANNER + (f"   {remain:>3.0f} s" if remain is not None else ""))
    elif phase == "ready":
        out.append(f"     {DIM}get ready{RST}")
    else:
        out.append(f"     {note}")
    sys.stdout.write("\n".join(out) + "\n\n"); sys.stdout.flush()


def build_rows(ctx, take):
    spec = take["spec"]
    ctx["take_no"] += 1
    take_id = f"{ctx['subject']}_{ctx['session']}_{ctx['take_no']:04d}"
    ok = take["quality"] == "ok"
    rep = ctx["counts"].get(spec["key"], 0) + 1 if ok else ""     # numbered over good takes only
    meta = {"label": spec["label"], "group": spec["group"], "idle_variant": spec["variant"],
            "take_id": take_id, "rep": rep, "subject_id": ctx["subject"],
            "session_id": ctx["session"], "device": ctx["device"], "window_s": spec["window"],
            "beep_phone_ns": str(take["start_ph"]), "n_in_window": take["n_win"],
            "coverage": f"{take['coverage']:.3f}", "max_gap_s": f"{take['max_gap']:.3f}",
            "side_switch": int(len(take["sides"]) > 1), "quality": take["quality"],
            "gyro_rms_dps": f"{take['gyro_rms']:.2f}", "orient_range_deg": f"{take['orient']:.1f}",
            "round_no": "", "pos_in_round": "", "collector_version": VERSION}
    rows = []
    for t, r in take["seg"]:
        row = dict(r)
        row.update(meta)
        row["timestamp_ns"] = str(t)
        row["t_rel_s"] = f"{(t - take['start_ph']) / 1e9:.3f}"
        row["in_window"] = int(take["start_ph"] <= t <= take["end_ph"])
        rows.append(row)
    return take_id, rep, rows


def record_take(spec, ctx):
    """Record one take. Returns a one-line result for the menu."""
    if not stream_ok():
        return f"{YEL}!! No data from the phone - check Sensor Logger is recording, then try again.{RST}"
    try:
        take_screen(ctx, spec, "ready")
        time.sleep(READ_S_NEW if ctx["counts"].get(spec["key"], 0) < 2 else READ_S)
        off = clock_offset_ns()
        if off is None:
            return f"{YEL}!! Clock not synced yet - try again in a few seconds.{RST}"
        take_screen(ctx, spec, "rec", spec["window"] if spec["long"] else None)
        t_start = now_ns()
        t_mono = time.monotonic()
        beep_start()
        end = t_mono + spec["window"]
        while time.monotonic() < end:
            time.sleep(min(1.0, max(0.0, end - time.monotonic())) if spec["long"] else
                       max(0.0, end - time.monotonic()))
            if spec["long"] and time.monotonic() < end:
                take_screen(ctx, spec, "rec", end - time.monotonic())
        beep_end()
        take_screen(ctx, spec, "done", note=f"{DIM}saving ...{RST}")
        take = analyse(spec, t_start, off, lambda: None)
    except KeyboardInterrupt:
        beep_discard()
        return f"{YEL}Take cancelled (Ctrl+C) - nothing saved.{RST}"

    if REQUIRED_SIDE and any(s not in (REQUIRED_SIDE, "unknown") for s in take["sides"]):
        take["problems"].append(f"not the {REQUIRED_SIDE} AirPod")
        take["quality"] = "bad:" + ";".join(take["problems"])
    if not take["seg"]:
        return f"{YEL}!! No samples received for this take - nothing saved. Check the stream.{RST}"
    take_id, rep, rows = build_rows(ctx, take)
    write_rows(ctx["path"], rows)
    ctx["last_take"] = take_id
    if take["quality"] == "ok":
        ctx["counts"][spec["key"]] = rep
        return f"{GRN}✓ {spec['key']}  {rep}/{spec['target']}{RST}"
    msg = f"{YEL}✗ {spec['key']} not counted - {', '.join(take['problems'])}. Press Enter to repeat."
    if "no movement" in take["problems"]:
        msg += " (start on the high beep)"
    if any("AirPod" in p for p in take["problems"]):
        msg += f" Use the {REQUIRED_SIDE.upper()} AirPod only."
    return msg + RST


# ------------------------------------------------------------------ menu
def show_progress(ctx, last_msg):
    clear()
    done = sum(min(ctx["counts"].get(s["key"], 0), s["target"]) for s in SPECS)
    goal = sum(s["target"] for s in SPECS)
    print("=" * 78)
    print(f"  GESTURE COLLECTOR v{VERSION}   subject {ctx['subject']}   {ctx['device']}   "
          f"earbud {ctx['side'].upper()}   {done}/{goal} takes")
    print("=" * 78)
    group = None
    for n, s in enumerate(SPECS, 1):
        if s["group"] != group:
            group = s["group"]
            print(f"  {DIM}{group}{RST}")
        c, t = ctx["counts"].get(s["key"], 0), s["target"]
        state = f"{GRN}DONE{RST}   " if c >= t else f"{c:>2}/{t:<4}"
        mark = "»" if ctx.get("last_spec") is s else " "
        print(f" {mark}[{n:>2}] {s['key']:<30} {state}  {s['window']:.0f}s  {DIM}{s['instruction']}{RST}")
    print("=" * 78)
    if last_msg:
        print("  " + last_msg)


def main():
    if port_in_use():
        print(f"!! Another program is already using port {PORT} (probably an older collector window).\n"
              "   Close it, then start this script again.")
        input("Enter to exit ...")
        sys.exit(1)
    threading.Thread(target=serve, daemon=True).start()
    time.sleep(1.0)
    clear()
    print("=" * 78)
    print(f"  GESTURE COLLECTOR v{VERSION}  (AirPods headphone motion, 50 Hz)")
    print(f"  Sensor Logger HTTP Push URL:  http://{local_ip()}:{PORT}/data")
    print("=" * 78)
    subject = ""
    while not subject:
        subject = "".join(c for c in input("Subject ID (e.g. S01): ").strip().upper() if c.isalnum() or c in "-")
    name = " ".join(input("Full name (optional, stored only in sessions.csv): ").split())
    device = pick("AirPods model  [1] AirPods Pro 2   [2] AirPods 5 : ",
                  {"1": "AirPods Pro 2", "2": "AirPods 5"})
    session = time.strftime("%Y%m%d-%H%M%S")
    path = f"dataset_{subject}.csv"
    upgrade_header(path)
    ctx = {"subject": subject, "device": device, "session": session, "path": path,
           "take_no": last_take_no(path, session), "last_take": None, "counts": counts_for(path),
           "side": "unknown", "last_spec": None}

    print(f"\nWaiting for the phone stream on port {PORT} ...  (Sensor Logger recording, HTTP Push on)")
    t_wait = time.monotonic()
    last_print = 0.0
    hinted = False
    while not stream_ok() or clock_offset_ns() is None:
        time.sleep(0.3)
        el = time.monotonic() - t_wait
        if el - last_print >= 3.0:
            last_print = el
            names = ", ".join(f"{k} x{v}" for k, v in sorted(diag["names"].items())) or "none"
            ping = f" | browser check from {diag['ping_from']}" if diag["ping_from"] else ""
            print(f"    {el:4.0f} s | HTTP posts received: {diag['posts']} (unreadable {diag['unreadable']}) "
                  f"| sensors in posts: {names} | headphone samples: {stats['samples']}{ping}")
        if el > 15 and not hinted:
            hinted = True
            if diag["posts"] == 0:
                print(f"!! Nothing is reaching this PC. On the phone/iPad:\n"
                      f"   1. Wi-Fi must be the SAME network as this PC.\n"
                      f"   2. Sensor Logger push URL must be exactly http://{local_ip()}:{PORT}/data\n"
                      f"   3. Open that URL in Safari: it should say 'Gesture collector ... is reachable'.\n"
                      f"   4. Settings > Privacy & Security > Local Network > Sensor Logger must be ON.\n"
                      f"   5. Sensor Logger must be RECORDING (a test push alone is not a data stream).")
            elif stats["samples"] == 0:
                print("!! Posts arrive but contain no headphone samples. Check: Headphone sensor enabled,\n"
                      "   AirPod connected to THIS device and in the ear, Motion & Fitness permission.\n"
                      f"   The raw posts are saved in {DEBUG_FILE} - send that file if it still fails.")
    time.sleep(1.0)
    ctx["side"] = current_side()
    print(f"--> Stream OK from {diag['first_from'] or 'the phone'}.  Recording earbud: {ctx['side'].upper()}")
    if REQUIRED_SIDE and ctx["side"] not in (REQUIRED_SIDE, "unknown"):
        print(f"!! Wrong earbud. Wear the {REQUIRED_SIDE.upper()} AirPod only and put the other one "
              f"in its case. Waiting ...")
        while current_side() != REQUIRED_SIDE:
            time.sleep(0.3)
        ctx["side"] = REQUIRED_SIDE
        print(f"--> Recording earbud: {ctx['side'].upper()}")
    if ctx["side"] == "unknown":
        print("!! The stream does not report the earbud side; it cannot be checked.")
    input("    Keep this earbud for the whole session. Press Enter ...")
    log_session(ctx, name)

    last_msg = ""
    while True:
        try:
            show_progress(ctx, last_msg)
            rep_txt = f"Enter = {ctx['last_spec']['key']} again   " if ctx["last_spec"] else ""
            ch = input(f"\n  {rep_txt}[number] gesture   [d] delete last take   [q] quit : ").strip().lower()
        except KeyboardInterrupt:
            last_msg = "Use q to quit."
            continue
        if ch == "q":
            print("--> Saved. Stop the Sensor Logger recording on the phone.")
            os._exit(0)
        elif ch == "d":
            if ctx["last_take"] and delete_take(path, ctx["last_take"]):
                last_msg = f"Deleted take {ctx['last_take']}."
                ctx["counts"] = counts_for(path)
                ctx["last_take"] = None
            else:
                last_msg = "Nothing to delete."
        elif ch == "" and ctx["last_spec"]:
            last_msg = record_take(ctx["last_spec"], ctx)
        elif ch.isdigit() and 1 <= int(ch) <= len(SPECS):
            ctx["last_spec"] = SPECS[int(ch) - 1]
            last_msg = record_take(ctx["last_spec"], ctx)
        else:
            last_msg = "Invalid choice."


if __name__ == "__main__":
    main()