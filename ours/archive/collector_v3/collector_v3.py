"""Collector v3: continuous AirPods IMU recording with audio cues and a cue log.

Recording never stops during a session. Every cue (what was asked, when) goes to cues.csv; labelled takes are
cut out later from cue time + motion detector. Sensor Logger (iPhone) pushes headphone motion over HTTP to
http://<this PC's IP>:<port>/data, same as the old collectors.

    python collector_v3.py --plan pilot
    python collector_v3.py --plan main --device "AirPods Pro 2"
    python collector_v3.py --plan pilot --simulate --fast 20 --auto     # dry run, no phone needed

Writes data/raw_v3/<subject>/<date>_<plan>_<device>_<time>/:
    stream.csv      every sample: sensor_ns (phone clock), host_ns (this PC's clock at receipt), 16 channels
    cues.csv        one row per cue: host_ns (PC clock at the START of the GO beep), sensor_ns_est (same moment
                    on the phone clock), block, round, trial, step, motion, condition, ...
    activities.csv  negative block: host/sensor start and end per activity
    gaps.csv        stream drops (no samples for > 1.5 s): start/end host_ns
    session.json    metadata, plan, seed, vocabulary, clock offset, rejected entries
Clock: Sensor Logger sends samples in batches, so host_ns of a sample is its batch's arrival time (late by up to
one batch). Align on the phone clock: sensor_ns_est = host_ns - offset, offset = min(host_ns - sensor_ns) over the
stream (the fastest batch). Always sort stream.csv by sensor_ns before use.
Only standard library: no Flask needed. Never open these files in Excel and save them.
"""
import argparse
import csv
import json
import queue
import random
import socket
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config as C

try:
    import winsound
except ImportError:  # not on Windows
    winsound = None

CHANNELS = ["yaw", "pitch", "roll", "quatX", "quatY", "quatZ", "quatW", "rotX", "rotY", "rotZ",
            "accX", "accY", "accZ", "gravX", "gravY", "gravZ"]
SOURCE_KEYS = ["yaw", "pitch", "roll", "quaternionX", "quaternionY", "quaternionZ", "quaternionW",
               "rotationRateX", "rotationRateY", "rotationRateZ", "accelerationX", "accelerationY",
               "accelerationZ", "gravityX", "gravityY", "gravityZ"]
ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------- stream ---------------------------------------


class Stream:
    """Receives samples from any thread, one writer thread appends them to stream.csv."""

    def __init__(self, path):
        self.q = queue.Queue()
        self.n = 0
        self.rejected = 0          # payload entries we could not use
        self.offset_ns = None      # min(host_ns - sensor_ns): phone clock -> PC clock, plus the smallest latency
        self.last_host_ns = 0
        self.recent = []  # sensor_ns of recent samples, for the rate (arrivals are bursty, sample times are not)
        self.lock = threading.Lock()
        self.f = open(path, "w", newline="")
        self.w = csv.writer(self.f)
        self.w.writerow(["sensor_ns", "host_ns"] + CHANNELS)
        self.running = True
        self.thread = threading.Thread(target=self._write, daemon=True)
        self.thread.start()

    def put(self, sensor_ns, values):
        host_ns = time.time_ns()
        with self.lock:
            self.n += 1
            self.last_host_ns = host_ns
            off = host_ns - sensor_ns
            if abs(off) < 3600e9:  # a garbage timestamp must not wreck the clock offset (clocks agree within minutes)
                self.offset_ns = off if self.offset_ns is None else min(self.offset_ns, off)
            self.recent.append(sensor_ns)
            if len(self.recent) > 1000:
                self.recent = self.recent[-500:]
        self.q.put([sensor_ns, host_ns] + values)

    def reject(self, n=1):
        with self.lock:
            self.rejected += n

    def to_sensor_ns(self, host_ns):
        with self.lock:
            return host_ns - self.offset_ns if self.offset_ns is not None else ""

    def rate(self, seconds=3.0):
        """Samples per second over the last `seconds` of sample time; 0 if nothing arrived for 1.5 s."""
        with self.lock:
            if not self.recent or time.time_ns() - self.last_host_ns > 1.5e9:
                return 0.0
            last = max(self.recent)
            return sum(1 for t in self.recent if last - t < seconds * 1e9) / seconds

    def _write(self):
        last_flush = time.time()
        while self.running or not self.q.empty():
            try:
                self.w.writerow(self.q.get(timeout=0.2))
            except queue.Empty:
                pass
            if time.time() - last_flush > 1.0:
                self.f.flush()
                last_flush = time.time()
        self.f.flush()

    def close(self):
        self.running = False
        self.thread.join()  # the writer drains the queue before it stops
        self.f.close()


def watchdog(stream, folder, stop):
    """Log and announce stream drops (no samples for more than 1.5 s) while the session runs."""
    with open(folder / "gaps.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["host_start_ns", "host_end_ns"])
        down_since = None
        while not stop.is_set():
            time.sleep(0.25)
            with stream.lock:
                last = stream.last_host_ns
            silent = last and time.time_ns() - last > 1.5e9
            if silent and down_since is None:
                down_since = last
                print("\n!!!!! STREAM DROPPED: no AirPods data. Check phone, Sensor Logger, AirPods in ears. !!!!!",
                      flush=True)
            elif not silent and down_since is not None:
                w.writerow([down_since, last])
                f.flush()
                print(f"\n..... stream back after {(last - down_since) / 1e9:.1f} s .....", flush=True)
                down_since = None
        if down_since is not None:
            w.writerow([down_since, ""])


def make_handler(stream):
    class Handler(BaseHTTPRequestHandler):
        def body(self):
            if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
                data = b""
                while True:
                    size = int(self.rfile.readline().strip().split(b";")[0], 16)
                    if size == 0:
                        self.rfile.readline()
                        return data
                    data += self.rfile.read(size)
                    self.rfile.readline()
            return self.rfile.read(int(self.headers.get("Content-Length", 0)))

        def do_POST(self):
            try:
                entries = json.loads(self.body()).get("payload", [])
            except (ValueError, AttributeError, TypeError):
                entries = None
                stream.reject()
            for entry in entries or []:
                try:  # one bad entry must not drop the rest of the batch
                    v = entry.get("values", {})
                    if not any(k in v for k in ("rotationRateX", "quaternionW")):
                        continue  # another sensor (battery, phone motion, ...): not ours, not an error
                    vals = [float(v[k]) for k in SOURCE_KEYS]
                    stream.put(int(float(entry["time"])), vals)
                except (KeyError, ValueError, TypeError, AttributeError):
                    stream.reject()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, *args):  # keep the console for cues
            pass

    return Handler


def simulate(stream, stop, fs=50):
    """Fake 50 Hz headphone stream for dry runs."""
    t0 = time.time_ns()
    k = 0
    while not stop.is_set():
        k += 1
        vals = [0.0] * 6 + [1.0] + [random.gauss(0, 0.02) for _ in range(6)] + [0.0, 0.0, -9.81]
        stream.put(t0 + int(k * 1e9 / fs), vals)
        time.sleep(1 / fs)

# ---------------------------------------------------------------- session --------------------------------------


class Session:
    def __init__(self, args, folder, stream):
        self.a, self.folder, self.stream = args, folder, stream
        self.rng = random.Random(args.seed)
        self.cue_f = open(folder / "cues.csv", "w", newline="")
        self.cues = csv.writer(self.cue_f)
        self.cues.writerow(["host_ns", "sensor_ns_est", "block", "kind", "round", "trial", "step", "motion",
                            "condition", "window_s", "note"])
        self.act_f = open(folder / "activities.csv", "w", newline="")
        self.acts = csv.writer(self.act_f)
        self.acts.writerow(["host_start_ns", "host_end_ns", "sensor_start_ns_est", "sensor_end_ns_est", "activity"])
        self.trial = 0

    # -- helpers --
    def wait(self, s):
        time.sleep(s / self.a.fast)

    def ask(self, msg):
        print(f"\n>>> {msg}")
        if not self.a.auto:
            input("    press Enter when ready ")

    def beep(self, kind):
        if self.a.mute or winsound is None:
            print("\a", end="", flush=True)
            return
        freq, ms = {"ready": (800, 150), "go": (1500, 250), "end": (600, 150)}[kind]
        winsound.Beep(freq, ms)
        if kind == "end":
            winsound.Beep(freq, ms)

    def go(self):
        """GO beep; returns the PC time at the START of the beep (the beep itself blocks for 0.25 s)."""
        t = time.time_ns()
        self.beep("go")
        return t

    def log_cue(self, t, block, kind, rnd, step, motion, condition, window, note=""):
        self.cues.writerow([t, self.stream.to_sensor_ns(t), block, kind, rnd, self.trial, step,
                            motion, condition, window, note])
        self.cue_f.flush()

    def motions(self, which):
        return C.PILOT_MOTIONS if which == "pilot" else C.MAIN_MOTIONS

    def show(self, text, sub=""):
        print("\n" + "=" * 70 + f"\n   {text}\n" + (f"   {sub}\n" if sub else "") + "=" * 70, flush=True)

    def status(self):
        rate = self.stream.rate()
        warn = "   <-- CHECK STREAM" if rate < 40 else ""
        print(f"    stream: {self.stream.n} samples, {rate:.0f} Hz{warn}")

    # -- blocks --
    def calibration(self, b, name):
        self.ask("CALIBRATION. Sit upright, look straight ahead, AirPods in. From now on keep BOTH AirPods in: "
                 "if one comes out, the stream moves to the other bud and we must calibrate again.")
        self.show("STAY STILL", "4 seconds")
        t = self.go()
        self.log_cue(t, name, "calibration", 0, 0, "still", "sitting", 4.0)
        self.wait(4)
        self.beep("end")
        self.show("3 NODS", "one nod per beep: chin DOWN first, straight back up to the front, don't hold it down")
        for i in range(3):
            self.wait(1.0)
            t = self.go()
            self.log_cue(t, name, "calibration", 0, i + 1, "calib_nod", "sitting", 2.0)
            self.wait(2.0)
        self.show("LOOK LEFT, THEN RIGHT, THEN FRONT")
        t = self.go()
        self.log_cue(t, name, "calibration", 0, 0, "look_left_right", "sitting", 5.0)
        self.wait(5)
        self.beep("end")
        self.status()

    def one_cue(self, name, kind, rnd, motion, condition):
        self.trial += 1
        self.show(C.INSTRUCTIONS[motion], f"[{condition}]  trial {self.trial}")
        self.beep("ready")
        self.wait(0.8)
        t = self.go()
        self.log_cue(t, name, kind, rnd, 0, motion, condition, C.WINDOW_S)
        self.wait(C.WINDOW_S)
        self.wait(self.rng.uniform(*C.GAP_S))

    def rounds(self, b, name):
        ms = self.motions(b["motions"])
        self.ask(f"BLOCK '{name}': {b['rounds']} rounds, condition: {b['condition']}. "
                 f"Do the motion right after the high beep, in one smooth go, straight back to the front "
                 f"(don't hold at the end), then keep still.")
        for r in range(1, b["rounds"] + 1):
            seq = ms + ["idle"] * C.IDLE_PER_ROUND
            self.rng.shuffle(seq)
            print(f"\n--- {name}: round {r}/{b['rounds']} ---")
            for m in seq:
                self.one_cue(name, "rounds", r, m, b["condition"])
            self.status()
            if r % 5 == 0 and r < b["rounds"]:
                self.ask("Short break. Relax, keep the AirPods in.")

    def pairs(self, b, name):
        ms = [m for m in self.motions(b["motions"])]
        self.ask(f"BLOCK '{name}': two motions back to back. First motion on the first beep, second on the "
                 f"second beep.")
        for gap in C.PAIR_GAPS_S:
            for k in range(b["pairs_per_gap"]):
                first, then = self.rng.sample(ms, 2)
                self.trial += 1
                self.show(f"{first.upper()}  then  {then.upper()}", f"pause between them about {gap} s")
                self.wait(2.0)
                t = self.go()
                self.log_cue(t, name, "pairs", k + 1, 1, first, "sitting", 1.0 + gap, f"gap_s={gap}")
                self.wait(1.0 + gap)
                t = self.go()
                self.log_cue(t, name, "pairs", k + 1, 2, then, "sitting", C.WINDOW_S, f"gap_s={gap}")
                self.wait(C.WINDOW_S)
                self.wait(self.rng.uniform(*C.GAP_S))
        self.status()

    def commands(self, b, name):
        items = self.rng.sample(sorted(C.COMMANDS.items()), min(b["n"], len(C.COMMANDS)))
        self.ask(f"BLOCK '{name}': send {len(items)} commands. Each = first motion, then second motion, "
                 f"at your normal pace, after the beep.")
        for i, ((first, then), msg) in enumerate(items, 1):
            self.trial += 1
            self.show(f"COMMAND: {msg}", f"{first.upper()}  then  {then.upper()}")
            self.wait(2.5)
            t = self.go()
            self.log_cue(t, name, "commands", i, 0, f"{first}>{then}", "sitting", 6.0, msg)
            self.wait(6.0)
            self.wait(self.rng.uniform(*C.GAP_S))
        self.status()

    def self_paced(self, b, name):
        """No beeps: the person sends a list of commands at their own pace. Only the order is known; the decoder
        must find when each command happened (closest test to real use)."""
        for k in range(b["lists"]):
            items = self.rng.sample(sorted(C.COMMANDS.items()), b["per_list"])
            seq = " | ".join(f"{m}: {a} then {t}" for (a, t), m in items)
            self.ask(f"SELF-PACED list {k + 1}/{b['lists']}: no beeps. After Enter, send these commands IN ORDER, "
                     "at your own pace, a few seconds apart. Then sit still; the experimenter presses Enter.")
            self.show("SEND IN ORDER:", "\n   ".join(f"{i}. {m}:  {a.upper()} then {t.upper()}"
                                                     for i, ((a, t), m) in enumerate(items, 1)))
            self.trial += 1
            self.log_cue(time.time_ns(), name, "self_paced", k + 1, 0, ";".join(f"{a}>{t}" for (a, t), _ in items), "sitting",
                         0, f"start; {seq}")
            if self.a.auto:
                self.wait(b["per_list"] * 6)
            else:
                input("    (experimenter) press Enter when all commands are done ")
            self.log_cue(time.time_ns(), name, "self_paced", k + 1, 1, "end", "sitting", 0, "end")
        self.status()

    def rewear(self, b, name):
        self.ask("RE-WEAR: take both AirPods out, put them back in as usual.")
        self.log_cue(time.time_ns(), name, "rewear", 0, 0, "rewear", "", 0)

    def negatives(self, b, name):
        acts = C.NEGATIVES_PILOT if b["activities"] == "pilot" else C.NEGATIVES_MAIN
        self.ask(f"NO-GESTURE BLOCK ({sum(m for _, m in acts)} min). Do NOT do any of the gestures. "
                 "Just do each activity naturally.")
        for activity, minutes in acts:
            self.show(f"ACTIVITY: {activity}", f"{minutes} min, until the double beep")
            self.wait(2.0)
            start = self.go()
            self.log_cue(start, name, "negatives", 0, 0, "none", activity, minutes * 60)
            self.wait(minutes * 60)
            end = time.time_ns()
            self.acts.writerow([start, end, self.stream.to_sensor_ns(start), self.stream.to_sensor_ns(end), activity])
            self.act_f.flush()
            self.beep("end")
        self.status()

    def run(self, plan):
        for i, b in enumerate(plan, 1):
            name = b.get("name", b["kind"])
            print(f"\n######## block {i}/{len(plan)}: {name} ########")
            getattr(self, b["kind"])(b, name)
        self.show("SESSION DONE. Thank you!")

    def close(self):
        self.cue_f.close()
        self.act_f.close()

# ---------------------------------------------------------------- main -----------------------------------------


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def metadata(args):
    meta = {"subject": args.subject, "device": args.device, "plan": args.plan, "seed": args.seed,
            "protocol_version": "v3", "app": "Sensor Logger", "fs_expected_hz": 50}
    fields = [("ear_tip_size", "S/M/L/XS"), ("glasses", "yes/no"), ("long_hair_over_ears", "yes/no"),
              ("handedness", "right/left"), ("age_band", "e.g. 20-24"), ("sex", "optional"),
              ("airpods_firmware", "optional"), ("recorded_by", "name"), ("notes", "")]
    if not args.auto:
        print("\nSession metadata (Enter to skip):")
        for k, hint in fields:
            meta[k] = input(f"  {k} [{hint}]: ").strip()
    meta.update({"pilot_motions": C.PILOT_MOTIONS, "main_motions": C.MAIN_MOTIONS,
                 "commands": {f"{a}>{b}": m for (a, b), m in C.COMMANDS.items()},
                 "window_s": C.WINDOW_S, "gap_s": C.GAP_S, "started": datetime.now().isoformat(timespec="seconds")})
    return meta


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--plan", choices=list(C.PLANS), default="pilot")
    p.add_argument("--subject", help="e.g. subject05 (asked if missing)")
    p.add_argument("--device", help='e.g. "AirPods Pro 2" (asked if missing)')
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--out", default=str(ROOT / "data" / "raw_v3"))
    p.add_argument("--seed", type=int, default=None, help="random order seed (default: from the clock)")
    p.add_argument("--simulate", action="store_true", help="fake stream, no phone needed")
    p.add_argument("--fast", type=float, default=1.0, help="divide all waits by this (dry runs only)")
    p.add_argument("--auto", action="store_true", help="no Enter prompts, no metadata questions (dry runs)")
    p.add_argument("--mute", action="store_true", help="no beeps")
    args = p.parse_args()
    args.subject = args.subject or ("sim" if args.auto else input("Subject ID (e.g. subject05): ").strip())
    args.device = args.device or ("simulated" if args.auto else input("Device (e.g. AirPods Pro 2): ").strip())
    args.seed = args.seed if args.seed is not None else int(time.time())

    try:  # bind the port first, so a busy port does not leave an empty session folder
        server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(None))
    except OSError as e:
        raise SystemExit(f"Port {args.port} is not free ({e}). Close the other collector or use --port.")
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    folder = Path(args.out) / args.subject / f"{stamp}_{args.plan}_{args.device.replace(' ', '')}"
    folder.mkdir(parents=True, exist_ok=False)
    meta = metadata(args)
    meta["completed"] = False

    stream = Stream(folder / "stream.csv")
    server.RequestHandlerClass = make_handler(stream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    stop = threading.Event()
    if args.simulate:
        threading.Thread(target=simulate, args=(stream, stop), daemon=True).start()
    session = None
    try:
        print(f"\nSaving to {folder}")
        print(f"Sensor Logger HTTP push URL: http://{local_ip()}:{args.port}/data  (headphone motion on)")
        print("Waiting for the stream ... (Ctrl+C to give up)")
        waited = 0.0
        while stream.n < 50:
            time.sleep(0.5)
            waited += 0.5
            if waited % 5 == 0:
                print(f"    still waiting: {stream.n} samples, {stream.rejected} rejected entries. Check the URL, "
                      "Wi-Fi, firewall, and that Headphone motion is on in Sensor Logger.")
        time.sleep(3)
        print(f"Stream OK: {stream.rate():.0f} Hz (expect about 50)")
        threading.Thread(target=watchdog, args=(stream, folder, stop), daemon=True).start()
        session = Session(args, folder, stream)
        session.run(C.PLANS[args.plan])
        meta["completed"] = True
    except KeyboardInterrupt:
        print("\nStopped early (Ctrl+C). Everything recorded so far is saved.")
    finally:
        stop.set()
        server.shutdown()  # no new samples after this point
        if session:
            session.close()
        stream.close()
        time.sleep(0.5)  # let the watchdog close gaps.csv
        meta.update({"ended": datetime.now().isoformat(timespec="seconds"), "samples": stream.n,
                     "rejected_entries": stream.rejected, "clock_offset_ns": stream.offset_ns,
                     "trials": session.trial if session else 0})
        (folder / "session.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"Saved {stream.n} samples ({stream.rejected} rejected entries), "
              f"{session.trial if session else 0} trials -> {folder}")


if __name__ == "__main__":
    main()
