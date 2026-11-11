// Live mode: recognise commands from the AirPods in real time (build order step 1, PROJECT_REVIEW.md section 8).
//
//   LiveEngine   motion queue: its own detector (own still-pose calibration), a short sample buffer, the 3-nod head
//                frame, and for every finished event: head frame -> features -> Rules AND Model decisions
//   LiveSession  main thread: Rules/Model switch, pair decoder -> command, sounds + spoken command, log files
//   LiveView     the screen
//
// Files (data folder/live/): live_<stamp>.csv = one row per event (both modes' answers, features, probabilities,
// "marked wrong" notes); live_<stamp>_stream.csv = raw samples (same format as the sessions), for later analysis.
// The model is live_model.json from the data folder if there is one (retrained: export_live_model.py), else the
// one built into the app.

import AVFoundation
import Foundation
import SwiftUI

struct LiveSample {
    var ns: Int64
    var rot: V3
    var acc: V3
    var grav: V3
}

struct LiveResult {
    var startNs: Int64
    var endNs: Int64
    var features: [String: Double]
    var rules: Decision
    var model: Decision
    var proba: [Double]
    var headRot: [V3] = []      // v3.1: head-frame rotation of the event (trial checks: DTW templates)
}

// ---------------------------------------------------------------------------------------------- engine (motion queue)
final class LiveEngine {
    enum Phase { case off, still, nods, running }

    var onResult: ((LiveResult) -> Void)?        // called on the motion queue
    var onNod: ((Int) -> Void)?
    var onCalibrated: ((Double?) -> Void)?
    var onEarbudSwitch: (() -> Void)?

    private let lock = NSLock()
    private let detector = LiveDetector()
    private var buf: [LiveSample] = []
    private var phase: Phase = .off
    private var heading: Double?
    private var model: LiveModel?
    private var nods: [(gDown: V3, gyro: [V3])] = []
    private var location: String?
    private let minNodPeak = 1.0                 // rad/s: smaller events during the nod step are not nods

    func setModel(_ m: LiveModel?) { lock.lock(); model = m; lock.unlock() }

    func beginStill() {
        lock.lock(); phase = .still; heading = nil; nods = []; location = nil; lock.unlock()
        detector.beginQuietCapture()
    }

    /// Ends the still pose (quiet level) and starts waiting for 3 nods. False if too few samples came in.
    func endStill() -> Bool {
        let ok = detector.endQuietCapture()
        _ = detector.takeClosed()
        lock.lock(); phase = ok ? .nods : .off; lock.unlock()
        return ok
    }

    func stop() { lock.lock(); phase = .off; lock.unlock() }

    /// v3.1: true once the 3 nods gave a head frame and events are being recognised.
    var isRunning: Bool { lock.lock(); defer { lock.unlock() }; return phase == .running }

    func push(ns: Int64, rot: V3, acc: V3, grav: V3, location loc: String) {
        lock.lock()
        if phase == .off { lock.unlock(); return }
        let switched = location != nil && location != loc
        if switched { phase = .off; heading = nil }
        location = loc
        buf.append(LiveSample(ns: ns, rot: rot, acc: acc, grav: grav))
        if buf.count > 600 { buf.removeFirst(buf.count - 600) }     // ~12 s at 50 Hz
        lock.unlock()
        if switched { onEarbudSwitch?(); return }
        detector.push(sensorNs: ns, rot: (rot.x, rot.y, rot.z), acc: (acc.x, acc.y, acc.z))
        for e in detector.takeClosed() { handle(e) }
    }

    private func handle(_ e: LiveEvent) {
        lock.lock()
        let ph = phase, h = heading, m = model
        let pre = buf.filter { $0.ns >= e.startNs - 500_000_000 && $0.ns < e.startNs }
        let ev = buf.filter { $0.ns >= e.startNs && $0.ns <= e.endNs }
        lock.unlock()
        guard ev.count >= 5 else { return }
        let g = HeadFrame.gravityDown((pre.isEmpty ? [ev[0]] : pre).map(\.grav))
        switch ph {
        case .nods:
            let peak = ev.map { ($0.rot * $0.rot).sum().squareRoot() }.max() ?? 0
            guard peak >= minNodPeak else { return }
            lock.lock()
            nods.append((g, ev.map(\.rot)))
            let n = nods.count
            var result: Double? = nil
            if n >= 3 {
                heading = HeadFrame.calibrateHeading(nods: nods)
                result = heading
                phase = .running
            }
            lock.unlock()
            onNod?(n)
            if n >= 3 { onCalibrated?(result) }
        case .running:
            guard let m = m else { return }
            let mat = HeadFrame.matrix(heading: h, gDown: g)
            let rot = ev.map { mat.apply($0.rot) }
            let fs = snappedRate(samples: ev.count, seconds: Double(ev[ev.count - 1].ns - ev[0].ns) / 1e9)
            let f = LiveFeatures.compute(rot: rot, fs: fs)
            let d = decide(f, model: m)
            onResult?(LiveResult(startNs: e.startNs, endNs: e.endNs, features: f, rules: d.rules, model: d.model,
                                 proba: d.proba, headRot: rot))
        default:
            break
        }
    }
}

// ---------------------------------------------------------------------------------------------- session (main thread)
@MainActor
final class LiveSession: ObservableObject {
    enum Calib: Equatable { case none, still, nods(Int), ready, failed(String) }

    struct Row: Identifiable {
        let id: Int
        let time: Date
        let result: LiveResult
        let chosen: Decision
        var wrong = false
    }

    @Published var calib: Calib = .none
    @Published var mode: RecognizerMode = .rules { didSet { decoder.reset(); pending = nil } }
    @Published var rows: [Row] = []
    @Published var lastCommand: LiveCommand?
    @Published var lastCommandTime: Date?
    @Published var pending: String?
    @Published var speak = true
    @Published var sounds = true
    @Published var modelSource = ""
    @Published var logPath = ""
    @Published var forestSource = ""
    @Published var lastForest: ForestResult?

    private(set) var model: LiveModel?
    private(set) var forest: ForestModel?
    private var forestLog: FileHandle?
    private var decoder: PairDecoder
    private let recorder: Recorder
    private let dataRoot: URL
    private var log: FileHandle?
    private var timer: Timer?
    private var started = false
    private var ownsSegment = false
    private var counter = 0
    private let synth = AVSpeechSynthesizer()

    init(recorder: Recorder, dataRoot: URL, plan: StudyPlan) {
        self.recorder = recorder
        self.dataRoot = dataRoot
        let cmds = Dictionary(plan.commands.map { ("\($0.first)>\($0.then)", $0.message) }, uniquingKeysWith: { a, _ in a })
        decoder = PairDecoder(commands: cmds)
        (model, modelSource) = LiveSession.loadModel(dataRoot: dataRoot)
        if let m = model { decoder.timeoutS = m.pairTimeoutS }
        (forest, forestSource) = ForestModel.load(dataRoot: dataRoot)
    }

    /// live_model.json from the data folder (no rebuild needed to change it), else the built-in one.
    nonisolated static func loadModel(dataRoot: URL) -> (LiveModel?, String) {
        let user = dataRoot.appendingPathComponent("live_model.json")
        if let d = try? Data(contentsOf: user), let m = try? LiveModel.decode(d) {
            return (m, "Model: live_model.json from the data folder (\(m.version))")
        }
        if let url = Bundle.main.url(forResource: "live_model", withExtension: "json"),
           let d = try? Data(contentsOf: url), let m = try? LiveModel.decode(d) {
            return (m, "Model: built in (\(m.version))")
        }
        return (nil, "No live_model.json found: the recogniser cannot run")
    }

    var classes: [String] { model?.classes ?? [] }

    var calibrating: Bool {
        if case .nods = calib { return true }
        return calib == .still
    }

    func start() {
        guard !started else { return }
        started = true
        Platform.configureAudio()
        Platform.keepAwake(true)
        let eng = recorder.engine
        eng.setModel(model)
        eng.onResult = { [weak self] r in Task { @MainActor in self?.handle(r) } }
        eng.onNod = { [weak self] n in Task { @MainActor in self?.calib = .nods(n) } }
        eng.onCalibrated = { [weak self] h in
            Task { @MainActor in
                guard let self = self else { return }
                self.calib = h == nil ? .failed("Could not work out the nod axis: try again") : .ready
                if h != nil { self.say("Ready") }
            }
        }
        eng.onEarbudSwitch = { [weak self] in
            Task { @MainActor in self?.calib = .failed("The stream moved to the other earbud: calibrate again") }
        }
        // Forest runs on its own detector, needs no calibration, and always runs (logged) when a model is there
        recorder.forest.setModel(forest)
        recorder.forest.onResult = { [weak self] r in Task { @MainActor in self?.handleForest(r) } }
        openFiles()
        timer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.tick() }
        }
    }

    func stop() {
        guard started else { return }
        started = false
        recorder.engine.stop()
        recorder.forest.setModel(nil)
        recorder.forest.onResult = nil
        try? forestLog?.close()
        forestLog = nil
        Platform.keepAwake(false)
        timer?.invalidate()
        timer = nil
        if ownsSegment { recorder.stopSegment(); ownsSegment = false }
        try? log?.synchronize()
        try? log?.close()
        log = nil
    }

    private func tick() {
        let now = Double(sensorNowNs()) / 1e9
        if decoder.tick(now) { pending = nil }
    }

    // ------------------------------------------------------------------ calibration: 3.5 s still, then 3 nods
    func calibrate() {
        Task { @MainActor in
            decoder.reset()
            pending = nil
            calib = .still
            say("Keep still")
            recorder.engine.beginStill()
            try? await Task.sleep(nanoseconds: 3_500_000_000)
            guard recorder.engine.endStill() else {
                calib = .failed("Still pose too short: is data coming in from the AirPods?")
                return
            }
            calib = .nods(0)
            say("Now nod down three times. Chin down and straight back up.")
            for _ in 0..<80 {
                if calib == .ready { return }
                if case .failed = calib { return }
                try? await Task.sleep(nanoseconds: 250_000_000)
            }
            if case .nods = calib {
                recorder.engine.stop()
                calib = .failed("Did not see 3 nods in 20 s: try again, a bit bigger")
            }
        }
    }

    // ------------------------------------------------------------------ events
    private func handleForest(_ r: ForestResult) {
        guard started else { return }
        lastForest = r
        var line = [String(hostNowNs()), String(r.startNs), String(r.endNs), mode.rawValue, r.label,
                    String(format: "%.4f", r.confidence), r.accepted ? "1" : "0"]
        line += r.proba.map { String(format: "%.4f", $0) }
        if let d = (line.joined(separator: ",") + "\n").data(using: .utf8) { forestLog?.write(d) }
        guard mode == .forest, r.accepted else { return }
        // a forest class is a whole gesture, so it is the command itself
        lastCommand = LiveCommand(first: r.label, second: "", message: r.label.replacingOccurrences(of: "_", with: " ").uppercased(),
                                  tStart: Double(r.startNs) / 1e9, tEnd: Double(r.endNs) / 1e9)
        lastCommandTime = Date()
        if sounds { Platform.sound("Glass") }
        if speak { say(r.label.replacingOccurrences(of: "_", with: " ")) }
    }

    private func handle(_ r: LiveResult) {
        guard started else { return }
        let chosen = mode == .rules ? r.rules : r.model
        counter += 1
        rows.insert(Row(id: counter, time: Date(), result: r, chosen: chosen), at: 0)
        if rows.count > 15 { rows.removeLast(rows.count - 15) }
        var cmd: LiveCommand?
        if chosen.accepted && mode != .forest {
            if sounds { Platform.sound("Tink") }
            cmd = decoder.push(chosen.motion, tStart: Double(r.startNs) / 1e9, tEnd: Double(r.endNs) / 1e9)
            if let c = cmd {
                lastCommand = c
                lastCommandTime = Date()
                if sounds { Platform.sound("Glass") }
                if speak { say(c.message) }
            }
        }
        pending = decoder.pending?.motion
        writeRow(r, chosen: chosen, command: cmd?.message ?? "", note: "")
    }

    /// The person says this event was wrong (a false or misread motion): logged, for retraining.
    func markWrong(_ id: Int) {
        guard let i = rows.firstIndex(where: { $0.id == id }) else { return }
        rows[i].wrong = true
        let r = rows[i]
        writeRow(r.result, chosen: r.chosen, command: "", note: "marked wrong")
    }

    private func say(_ text: String) {
        synth.stopSpeaking(at: .immediate)
        let u = AVSpeechUtterance(string: text)
        u.rate = 0.52
        synth.speak(u)
    }

    // ------------------------------------------------------------------ files
    private static let featureColumns = ["share_x", "share_y", "share_z", "linearity", "first_lobe_x", "first_lobe_y",
                                         "first_lobe_z", "loop_xy", "loop_xz", "loop_yz", "duration_s", "peak_rot"]

    private func openFiles() {
        let dir = dataRoot.appendingPathComponent("live")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let f = DateFormatter()
        f.dateFormat = "yyyyMMdd_HHmmss"
        let stamp = f.string(from: Date())
        let url = dir.appendingPathComponent("live_\(stamp).csv")
        let header = ["host_ns", "start_ns", "end_ns", "mode", "rules_kind", "rules_motion", "model_kind", "model_motion",
                      "model_confidence", "model_margin", "model_accepted", "chosen_motion", "accepted", "command"]
            + LiveSession.featureColumns + classes.map { "p_\($0)" } + ["model_version", "note"]
        FileManager.default.createFile(atPath: url.path, contents: (header.joined(separator: ",") + "\n").data(using: .utf8))
        log = try? FileHandle(forWritingTo: url)
        log?.seekToEndOfFile()
        logPath = url.path
        // live mode is only reachable from the start screen, so no session is writing to the recorder now
        try? recorder.startSegment(at: dir.appendingPathComponent("live_\(stamp)_stream.csv"))
        ownsSegment = true
        if let f = forest {
            let furl = dir.appendingPathComponent("live_\(stamp)_forest.csv")
            let fh = ["host_ns", "start_ns", "end_ns", "mode", "label", "confidence", "accepted"] + f.classes.map { "p_\($0)" }
            FileManager.default.createFile(atPath: furl.path, contents: (fh.joined(separator: ",") + "\n").data(using: .utf8))
            forestLog = try? FileHandle(forWritingTo: furl)
            forestLog?.seekToEndOfFile()
        }
    }

    private func writeRow(_ r: LiveResult, chosen: Decision, command: String, note: String) {
        func s(_ x: Double) -> String { String(format: "%.5f", x) }
        var v: [String] = [String(hostNowNs()), String(r.startNs), String(r.endNs), mode.rawValue,
                           r.rules.kind, r.rules.motion, r.model.kind, r.model.motion, s(r.model.confidence),
                           s(r.model.margin), r.model.accepted ? "1" : "0", chosen.motion, chosen.accepted ? "1" : "0",
                           command]
        v += LiveSession.featureColumns.map { s(r.features[$0] ?? .nan) }
        v += r.proba.map(s)
        v += [(model?.version ?? "").replacingOccurrences(of: ",", with: ";"), note]
        if let d = (v.joined(separator: ",") + "\n").data(using: .utf8) { log?.write(d) }
    }
}

// ---------------------------------------------------------------------------------------------- screen
struct LiveView: View {
    @EnvironmentObject var model: AppModel
    @EnvironmentObject var rec: Recorder
    @ObservedObject var live: LiveSession

    private var calibText: String {
        switch live.calib {
        case .none: return "Not calibrated. Sit still, press Calibrate: 3 s still, then nod down 3 times (chin down first)."
        case .still: return "Keep still..."
        case .nods(let n): return "Nod down 3 times, chin down and straight back up: \(n) of 3"
        case .ready: return "Calibrated. Do commands: first motion, then the second within 1.5 s."
        case .failed(let why): return why
        }
    }

    var body: some View {
        PhoneScroll {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Live recognizer").font(.largeTitle).bold()
                Spacer()
                Button("Back") { model.closeLive() }
            }
            AdaptiveStack(spacing: 16) {
                Text(String(format: "%.0f Hz", rec.rateHz))
                Text("Earbud: \(rec.location)")
                Text(rec.status).foregroundColor(rec.healthy ? .green : .orange)
                Spacer()
                VStack(alignment: .trailing) {
                    Text(live.modelSource).font(.caption).foregroundColor(.secondary)
                    Text(live.forestSource).font(.caption).foregroundColor(.secondary)
                }
            }
            AdaptiveStack(spacing: 20) {
                Picker("Mode", selection: $live.mode) {
                    ForEach(RecognizerMode.allCases, id: \.self) { Text($0.rawValue) }
                }
                .pickerStyle(.segmented)
                .frame(width: 300)
                Toggle("Speak commands", isOn: $live.speak)
                Toggle("Sounds", isOn: $live.sounds)
            }
            Text(live.modeHelp(for: live.mode)).font(.caption).foregroundColor(.secondary)
            GroupBox {
                HStack {
                    Text(calibText).foregroundColor(live.calib == .ready ? .green : .primary)
                    Spacer()
                    Button(live.calib == .ready ? "Calibrate again" : "Calibrate") { live.calibrate() }
                        .disabled(live.calibrating)
                }
            }
            AdaptiveStack(spacing: 24) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Last command").font(.headline)
                    Text(live.lastCommand?.message ?? "-").font(.system(size: 44, weight: .bold))
                    if let c = live.lastCommand {
                        Text("\(c.first) then \(c.second)").foregroundColor(.secondary)
                    }
                    if let f = live.lastForest {
                        Text(String(format: "Forest last saw: %@ (%.2f)%@", f.label, f.confidence, f.accepted ? "" : ", not sent"))
                            .font(.caption).foregroundColor(.secondary)
                    }
                    if let p = live.pending {
                        Text("First motion: \(p). Waiting up to 1.5 s for the second...").foregroundColor(.orange)
                    }
                    if let r = live.rows.first {
                        Text("Last event, model probabilities").font(.caption).foregroundColor(.secondary)
                        ForEach(Array(live.classes.enumerated()), id: \.offset) { pair in
                            let p = pair.offset < r.result.proba.count ? r.result.proba[pair.offset] : 0
                            HStack {
                                Text(pair.element).frame(width: 60, alignment: .leading).font(.caption)
                                ProgressView(value: p).frame(width: 200)
                                Text(String(format: "%.2f", p)).font(.caption.monospacedDigit())
                            }
                        }
                    }
                }
                Spacer()
                LiveHead(recorder: rec, reference: model.reference).frame(width: 200, height: 200)
            }
            Text("Recent motions (newest first)").font(.headline)
            List(live.rows) { row in
                AdaptiveStack(spacing: 14) {
                    Text(row.time, style: .time).font(.caption.monospacedDigit())
                    Text(row.chosen.accepted ? row.chosen.motion : "(\(row.chosen.motion == "none" ? "not a gesture" : row.chosen.motion))")
                        .bold(row.chosen.accepted)
                        .foregroundColor(row.chosen.accepted ? .primary : .secondary)
                        .frame(minWidth: Platform.isPhone ? 0 : 170, alignment: .leading)
                    Text("rules: \(row.result.rules.motion)").font(.caption).frame(minWidth: Platform.isPhone ? 0 : 130, alignment: .leading)
                    Text(String(format: "model: %@ %.2f", row.result.model.motion, row.result.model.confidence))
                        .font(.caption).frame(minWidth: Platform.isPhone ? 0 : 170, alignment: .leading)
                    Text(String(format: "%.1f s", row.result.features["duration_s"] ?? 0)).font(.caption)
                    Spacer()
                    Button(row.wrong ? "marked" : "Wrong") { live.markWrong(row.id) }.disabled(row.wrong)
                }
            }
            .frame(minHeight: Platform.isPhone ? 320 : 180)
            Text("Log: \(live.logPath)").font(.caption).foregroundColor(.secondary).textSelection(.enabled)
        }
        }
        .onAppear { live.start() }
        .onDisappear { live.stop() }
    }
}

extension LiveSession {
    func modeHelp(for m: RecognizerMode) -> String {
        switch m {
        case .rules:
            return "Rules: the axis that carries most of the rotation (nod / tilt / turn), a loop for circles, direction from the first swing. No 'not a gesture' class: anything with one clear axis counts as a motion."
        case .model:
            return "Model: logistic regression trained on EarSet (30 people) + P01. It also has a 'not a gesture' class and needs ≥ 50 % confidence. Circles: only 16 training examples so far."
        case .forest:
            return "Forest: the teammates' receiver approach (start at 0.60 rad/s, 96 raw statistics, random forest) on all our recordings. Each class is a whole gesture (e.g. tilt 2x left) and is sent as the command. No calibration needed."
        }
    }
}
