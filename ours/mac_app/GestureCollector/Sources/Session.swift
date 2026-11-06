// Runs a planned session step by step: spoken cue + beeps, cue log on the sensor clock, state saved after every
// step (resume after a crash), earbud switch -> recalibrate and redo the trial, experimenter controls.
//
// Session folder (APP_V2_PLAN.md section 6):
//   session.json   who/what/when (participant number + first name), plan, seed, device, modules, status
//   state.json     the full step list + how far we got (for resume)
//   stream_NNN.csv one per segment (a new one after every resume)
//   cues.csv       every cue: same columns as collector v3 + module, attempt, status
//   notes.csv      experimenter actions and notes

import AppKit
import AVFoundation
import Foundation

let APP_VERSION = "2.0.0"
let PROTOCOL_VERSION = "v2-2026-11"
let CUE_HEADER = "host_ns,sensor_ns_est,block,kind,round,trial,step,motion,condition,window_s,note,module,attempt,status\n"

struct SessionMeta: Codable {
    var participant: String        // "P05"
    var firstName: String
    var session: String            // "P05_s2"
    var sessionIndex: Int
    var device: String
    var budgetMin: Double
    var seed: UInt64
    var planVersion: String
    var appVersion: String
    var protocolVersion: String
    var os: String
    var macModel: String
    var profile: [String: String]
    var plannedCore: [String]
    var plannedModules: [String]
    var fillerRounds: Int
    var started: Date
    var ended: Date?
    var status: String             // running / complete / incomplete
    var coreBlocksDone: [String] = []
    var modulesDone: [String] = []
    var earbudSwitches: Int = 0
    var gaps: Int = 0
    var segments: Int = 0
}

struct SessionState: Codable {
    var meta: SessionMeta
    var steps: [Step]
    var index: Int                 // next step to run
    var trial: Int                 // running trial counter (cue log)
    var attempts: [String: Int]    // "block|round|step|motion" -> attempts so far
}

@MainActor
final class Speaker: NSObject, AVSpeechSynthesizerDelegate {
    private let synth = AVSpeechSynthesizer()
    private var cont: CheckedContinuation<Void, Never>?

    override init() {
        super.init()
        synth.delegate = self
    }

    /// Speaks and returns when done (or after the timeout). Main thread.
    private var generation = 0   // only the current utterance may end the wait (no late callbacks from older ones)

    func say(_ text: String, timeout: Double = 4) async {
        guard !text.isEmpty else { return }
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            finish(nil)
            generation += 1
            let my = generation
            cont = c
            let u = AVSpeechUtterance(string: text)
            u.rate = 0.52
            synth.speak(u)
            Task { @MainActor [weak self] in
                try? await Task.sleep(nanoseconds: UInt64(timeout * 1e9))
                self?.finish(my)
            }
        }
    }

    /// Ends the wait. gen = nil: whatever is waiting; otherwise only if that utterance is still the current one.
    private func finish(_ gen: Int?) {
        if let g = gen, g != generation { return }
        let c = cont
        cont = nil
        c?.resume()
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor in
            if !self.synth.isSpeaking { self.finish(self.generation) }
        }
    }
}

enum Beep {
    static func play(_ name: String) { NSSound(named: NSSound.Name(name))?.play() }
    static func ready() { play("Tink") }
    static func go() { play("Pop") }
    static func end() { play("Bottle") }
}

func macModel() -> String {
    var size = 0
    sysctlbyname("hw.model", nil, &size, nil, 0)
    guard size > 0 else { return "unknown" }
    var buf = [CChar](repeating: 0, count: size)
    sysctlbyname("hw.model", &buf, &size, nil, 0)
    return String(cString: buf)
}

@MainActor
final class SessionRunner: ObservableObject {
    enum Phase: Equatable { case idle, running, waitingContinue, waitingDone, paused, finished }

    @Published var phase: Phase = .idle
    @Published var title = ""
    @Published var sub = ""
    @Published var motion = ""          // motion being cued (for the head animation)
    @Published var countdown = 0.0
    @Published var progress = 0.0
    @Published var remainingS = 0.0
    @Published var banner = ""           // warnings (earbud switch, gap)
    @Published private(set) var state: SessionState?

    let folder: URL
    let recorder: Recorder
    let timing: Timing
    private let speaker = Speaker()
    private var cueFile: FileHandle?
    private var noteFile: FileHandle?
    private var task: Task<Void, Never>?
    private var continueFlag = false
    private var skipFlag = false
    private var pauseRequested = false
    private var stopRequested = false
    private var recalibrateRequested = false
    private var switchDuringStep = false
    var onModuleDone: ((SessionMeta, String) -> Void)?   // (meta, module id or core block id)
    var onFinished: ((SessionMeta) -> Void)?

    init(folder: URL, state: SessionState, recorder: Recorder, timing: Timing) {
        self.folder = folder
        self.state = state
        self.recorder = recorder
        self.timing = timing
    }

    // ------------------------------------------------------------------ files
    private func openAppend(_ name: String, header: String) -> FileHandle? {
        let url = folder.appendingPathComponent(name)
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: header.data(using: .utf8))
        }
        guard let h = try? FileHandle(forWritingTo: url) else { return nil }
        h.seekToEndOfFile()
        return h
    }

    func saveState() {
        guard let s = state else { return }
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        enc.dateEncodingStrategy = .iso8601
        if let d = try? enc.encode(s) { try? d.write(to: folder.appendingPathComponent("state.json"), options: .atomic) }
        if let d = try? enc.encode(s.meta) { try? d.write(to: folder.appendingPathComponent("session.json"), options: .atomic) }
    }

    static func loadState(folder: URL) -> SessionState? {
        let dec = JSONDecoder()
        dec.dateDecodingStrategy = .iso8601
        guard let d = try? Data(contentsOf: folder.appendingPathComponent("state.json")) else { return nil }
        return try? dec.decode(SessionState.self, from: d)
    }

    private func csv(_ s: String) -> String {
        s.contains(",") || s.contains("\"") || s.contains("\n") ? "\"" + s.replacingOccurrences(of: "\"", with: "\"\"") + "\"" : s
    }

    private func logCue(_ st: Step, hostNs: Int64, sensorNs: Int64, status: String, note: String = "") {
        guard var s = state else { return }
        s.trial += 1
        let key = "\(st.block)|\(st.round)|\(st.step)|\(st.motion)"
        s.attempts[key, default: 0] += 1
        let fields: [String] = [String(hostNs), String(sensorNs), st.block, st.cueKind, String(st.round), String(s.trial),
                                String(st.step), st.motion, st.condition, String(format: "%.2f", st.windowS),
                                [st.note, note].filter { !$0.isEmpty }.joined(separator: "; "), st.module,
                                String(s.attempts[key] ?? 1), status]
        state = s
        if let d = (fields.map(csv).joined(separator: ",") + "\n").data(using: .utf8) { cueFile?.write(d) }
        try? cueFile?.synchronize()
    }

    func note(_ text: String) {
        let line = "\(hostNowNs()),\(sensorNowNs()),\(csv(text))\n"
        if let d = line.data(using: .utf8) { noteFile?.write(d) }
        try? noteFile?.synchronize()
    }

    // ------------------------------------------------------------------ controls (experimenter)
    func pressContinue() { continueFlag = true }
    func skip() { skipFlag = true; note("experimenter: skip") }
    func togglePause() {
        if phase == .paused { pauseRequested = false; note("experimenter: resume") }
        else { pauseRequested = true; note("experimenter: pause after this step") }
    }
    func requestRecalibration() { recalibrateRequested = true; note("experimenter: recalibrate") }
    func stop() { stopRequested = true; skipFlag = true; continueFlag = true; note("experimenter: end session") }

    // ------------------------------------------------------------------ run
    func start(resuming: Bool) {
        guard var s = state else { return }
        cueFile = openAppend("cues.csv", header: CUE_HEADER)
        noteFile = openAppend("notes.csv", header: "host_ns,sensor_ns,note\n")
        let seg = String(format: "stream_%03d.csv", s.meta.segments)
        do { try recorder.startSegment(at: folder.appendingPathComponent(seg)) } catch {
            banner = "Could not create \(seg): \(error.localizedDescription)"
        }
        s.meta.segments += 1
        s.meta.status = "running"
        if resuming {
            // the earbuds may sit differently now: calibrate again before continuing
            s.steps.insert(contentsOf: Planner.calibration(module: "setup", reason: "Resuming the session. "), at: s.index)
        }
        state = s
        saveState()
        note(resuming ? "resume (segment \(seg))" : "start (segment \(seg))")
        recorder.onSwitch = { [weak self] from, to in Task { @MainActor in self?.earbudSwitched(from: from, to: to) } }
        recorder.onGap = { [weak self] g in Task { @MainActor in self?.gap(g) } }
        phase = .running
        task = Task { await self.loop() }
    }

    private func earbudSwitched(from: String, to: String) {
        banner = "Earbud changed (\(from) -> \(to)). Put BOTH AirPods in; we will calibrate again."
        switchDuringStep = true
        recalibrateRequested = true
        if var s = state { s.meta.earbudSwitches += 1; state = s }
        note("earbud switch \(from)->\(to)")
    }

    private func gap(_ g: Double) {
        banner = String(format: "Data gap of %.1f s: the current trial will be repeated.", g)
        switchDuringStep = true
        if var s = state { s.meta.gaps += 1; state = s }
        note(String(format: "data gap %.2f s", g))
    }

    private func updateProgress() {
        guard let s = state else { return }
        progress = s.steps.isEmpty ? 1 : Double(s.index) / Double(s.steps.count)
        remainingS = Planner.estimate(Array(s.steps[min(s.index, s.steps.count)...]), timing)
    }

    /// Sleeps in small steps; returns early when skipped or stopped.
    private func wait(_ seconds: Double) async {
        let end = Date().addingTimeInterval(seconds)
        while Date() < end && !skipFlag {
            countdown = end.timeIntervalSinceNow
            try? await Task.sleep(nanoseconds: 50_000_000)
        }
        countdown = 0
    }

    private func waitForButton(_ p: Phase) async {
        continueFlag = false
        phase = p
        while !continueFlag { try? await Task.sleep(nanoseconds: 100_000_000) }
        continueFlag = false
        phase = .running
    }

    private func loop() async {
        while let s = state, s.index < s.steps.count, !stopRequested {
            if pauseRequested {
                phase = .paused
                title = "PAUSED"
                sub = "Press Resume when ready."
                while pauseRequested && !stopRequested { try? await Task.sleep(nanoseconds: 100_000_000) }
                phase = .running
                if stopRequested { break }
            }
            if recalibrateRequested {
                recalibrateRequested = false
                if var st = state {
                    st.steps.insert(contentsOf: Planner.calibration(module: "setup", reason: "Calibrating again. "), at: st.index)
                    state = st
                    saveState()
                }
                continue
            }
            updateProgress()
            let step = s.steps[s.index]
            skipFlag = false
            switchDuringStep = false
            await run(step)
            guard var st = state else { break }
            if switchDuringStep && step.kind == .cue && step.cueKind != "calibration" && !stopRequested {
                // the trial was disturbed (earbud switch or data gap): repeat it right after the recalibration
                var again = step
                again.note = [step.note, "repeat after earbud switch/gap"].filter { !$0.isEmpty }.joined(separator: "; ")
                st.steps.insert(again, at: st.index + 1)
            }
            st.index += 1
            if step.endsBlock && step.module == "core" && !stopRequested {
                st.meta.coreBlocksDone.append(step.block)
                state = st
                onModuleDone?(st.meta, step.block)
            }
            if step.endsModule && step.module != "core" && step.module != "setup" && !stopRequested {
                st.meta.modulesDone.append(step.module)
                state = st
                onModuleDone?(st.meta, step.module)
            }
            state = st
            saveState()
            recorder.flush()
        }
        finish()
    }

    private func run(_ st: Step) async {
        title = st.text
        sub = st.sub
        motion = ""
        switch st.kind {
        case .message:
            await speaker.say(st.text.lowercased())
            await waitForButton(.waitingContinue)
        case .cue:
            motion = st.motion
            if !st.spoken.isEmpty { await speaker.say(st.spoken) }
            if st.readyS > 0 {
                Beep.ready()
                await wait(st.readyS)
            }
            if skipFlag { logCue(st, hostNs: hostNowNs(), sensorNs: sensorNowNs(), status: "skipped"); return }
            let h = hostNowNs(), t = sensorNowNs()
            Beep.go()
            await wait(st.windowS)
            logCue(st, hostNs: h, sensorNs: t, status: skipFlag ? "skipped" : (switchDuringStep ? "disturbed" : "done"))
            if st.cueKind == "calibration" && st.motion == "look_left_right" { Beep.end() }
            await wait(st.gapAfterS)
        case .activity:
            await speaker.say(st.spoken)
            let h = hostNowNs(), t = sensorNowNs()
            Beep.go()
            await wait(st.windowS)
            logCue(st, hostNs: h, sensorNs: t, status: skipFlag ? "skipped" : "done")
            Beep.end()
            try? await Task.sleep(nanoseconds: 300_000_000)
            Beep.end()
        case .manualStart:
            await speaker.say(st.cueKind == "rewear" ? "take both AirPods out and put them back in" : "send the commands in order")
            logCue(st, hostNs: hostNowNs(), sensorNs: sensorNowNs(), status: "start")
            await waitForButton(.waitingDone)
        case .manualEnd:
            logCue(st, hostNs: hostNowNs(), sensorNs: sensorNowNs(), status: "end")
        }
    }

    private func finish() {
        guard var s = state else { return }
        s.meta.ended = Date()
        s.meta.status = (s.index >= s.steps.count && !stopRequested) ? "complete" : "incomplete"
        state = s
        saveState()
        recorder.stopSegment()
        try? cueFile?.close()
        try? noteFile?.close()
        recorder.onSwitch = nil
        recorder.onGap = nil
        phase = .finished
        title = s.meta.status == "complete" ? "DONE. Thank you!" : "Session ended early (saved)"
        sub = ""
        onFinished?(s.meta)
    }

    /// Zip of the session folder next to it (for AirDrop / WhatsApp / pen drive).
    func exportZip() -> URL? {
        let zip = folder.deletingLastPathComponent().appendingPathComponent(folder.lastPathComponent + ".zip")
        try? FileManager.default.removeItem(at: zip)
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
        p.arguments = ["-c", "-k", "--keepParent", folder.path, zip.path]
        do { try p.run(); p.waitUntilExit() } catch { return nil }
        return p.terminationStatus == 0 ? zip : nil
    }
}
