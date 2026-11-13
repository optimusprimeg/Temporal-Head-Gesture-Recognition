// Runs a planned session step by step: spoken cue + beeps, cue log on the sensor clock, state saved after every
// step (resume after a crash), earbud switch -> recalibrate and redo the trial, experimenter controls.
//
// Session folder (APP_V2_PLAN.md section 6):
//   session.json   who/what/when (participant number + first name), plan, seed, device, modules, status
//   state.json     the full step list + how far we got (for resume)
//   stream_NNN.csv one per segment (a new one after every resume)
//   cues.csv       every cue: same columns as collector v3 + module, attempt, status
//   notes.csv      experimenter actions and notes

import AVFoundation
import Foundation

let APP_VERSION = "3.7.0"
let PROTOCOL_VERSION = "v3.2-2026-11"   // v3: experiment files; v3.1: trial checks + retake; v3.2: the name is the go
// v2.1: shown_sensor_ns = when the cue was announced (text + spoken name); people start moving from there, so the
// labeller opens the motion window at the announcement, not at GO. live_* = the app's own one-motion check.
// v3.1 adds: flags (count/too_small/posture_jump/mismatch/unsure, ';'-joined), the three check answers, their vote,
// the event's peak rotation (rad/s). Older columns are unchanged.
let CUE_HEADER = "host_ns,sensor_ns_est,block,kind,round,trial,step,motion,condition,window_s,note,module,attempt,status,shown_sensor_ns,live_events,live_verdict,flags,check_rule,check_model,check_dtw,check_vote,peak_rot\n"

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
    // v2.1 (optional so v2.0 files still load)
    var detectedAirPods: [String: String]? = nil   // name, product ID, firmware read from macOS Bluetooth
    var liveChecked: Int? = nil
    var liveOK: Int? = nil
    // v3: which experiment file ran (a copy is saved as experiment.json in the session folder), and on what
    var experimentFile: String? = nil
    var experimentName: String? = nil
    var platform: String? = nil                    // "macOS" or "iOS"
    // v3.6: the chosen gestures and their target good reps for this person (nil = whole experiment, rounds as planned)
    var targets: [String: Int]? = nil
    var longIdle: Bool? = nil
    // v3.7: the earbud side streaming at the start (every stream row also has sensor_location), whether a scene video
    // was recorded (files in <data folder>/video/<session folder>/), and how the session ended
    var earbudSide: String? = nil
    var sceneVideo: Bool? = nil
    var videoQuality: String? = nil  // "small" (480p) / "normal" (720p); HEVC, H.264 if HEVC is not available
    var endedBy: String? = nil      // complete / end_after_round / end_session
}

struct SessionState: Codable {
    var meta: SessionMeta
    var steps: [Step]
    var index: Int                 // next step to run
    var trial: Int                 // running trial counter (cue log)
    var attempts: [String: Int]    // "block|round|step|motion" -> attempts so far
    var cantDo: [String]? = nil    // v3.1: motions this person cannot do (skipped from then on, logged "cant_do")
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
    static func ready() { Platform.sound("Tink") }
    static func go() { Platform.sound("Pop") }
    static func end() { Platform.sound("Bottle") }
}

@MainActor
final class SessionRunner: ObservableObject {
    enum Phase: Equatable { case idle, running, waitingContinue, waitingDone, paused, finished }

    @Published var phase: Phase = .idle
    @Published var title = ""
    @Published var sub = ""
    @Published var motion = ""          // motion being cued (for the head animation)
    @Published var cueID = ""           // v3.3: the motion id itself (its clip: experiments/media/<id>.gif)
    @Published var countdown = 0.0
    @Published var nowActive = false      // v3.2: the motion window is open (green NOW bar)
    @Published var windowS = 0.0
    @Published var progress = 0.0
    @Published var remainingS = 0.0
    @Published var banner = ""           // warnings (earbud switch, gap)
    @Published var feedback = ""         // result of the one-motion check for the last trial
    @Published var feedbackOK = true
    @Published var endAfterRound = false  // v3.1: stop cleanly when the current round is finished
    @Published var pausePending = false   // v3.7: Pause pressed, the current step is finishing first
    @Published var markable = ""          // v3.7: the gesture "Last one was wrong" would mark ("" = nothing to mark)
    var familyKey = ""                    // v3.7: the experiment family (can't-do is remembered per family)
    var camera: SceneCamera?              // v3.7: optional scene video, one file per segment like the stream
    @Published private(set) var state: SessionState?

    let folder: URL
    let recorder: Recorder
    let timing: Timing
    let motions: [String: MotionDef]      // v3.1: motion definitions of the experiment (expected count, group, demo)
    private let speaker = Speaker()
    // v3.1 trial checks
    private var liveModel: LiveModel?
    private var results: [LiveResult] = []
    private var templates = TemplateStore()
    private var lastAngles: HeadAngles?
    private var retakeNext = false
    private var cueFile: FileHandle?
    private var noteFile: FileHandle?
    private var task: Task<Void, Never>?
    private var continueFlag = false
    private var skipFlag = false
    private var pauseRequested = false
    private var stopRequested = false
    private var endedAfterRound = false
    private var recalibrateRequested = false
    private var switchDuringStep = false
    // v3.5 experimenter "last one was wrong": the last logged gesture trial, and a redo waiting to be inserted
    private var lastTrial: (step: Step, trial: Int, shownNs: Int64)?
    private var redoStep: Step?
    @Published var redoInfo = ""
    var onModuleDone: ((SessionMeta, String) -> Void)?   // (meta, module id or core block id)
    var onFinished: ((SessionMeta) -> Void)?

    init(folder: URL, state: SessionState, recorder: Recorder, timing: Timing, motions: [MotionDef] = []) {
        self.folder = folder
        self.state = state
        self.recorder = recorder
        self.timing = timing
        self.motions = Dictionary(motions.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
        self.liveModel = LiveSession.loadModel(dataRoot: folder.deletingLastPathComponent()).0
    }

    // ------------------------------------------------------------------ files
    private func openAppend(_ name: String, header: String) -> FileHandle? {
        var url = folder.appendingPathComponent(name)
        // a session started by an older app version has other columns: continue in a second file, never mix
        if let old = try? String(contentsOf: url, encoding: .utf8), let first = old.split(separator: "\n").first,
           String(first) + "\n" != header {
            url = folder.appendingPathComponent(name.replacingOccurrences(of: ".csv", with: "_v31.csv"))
        }
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

    private func logCue(_ st: Step, hostNs: Int64, sensorNs: Int64, status: String, note: String = "",
                        shownNs: Int64? = nil, live: LiveVerdict? = nil, check: TrialCheck? = nil, vote: String = "") {
        guard var s = state else { return }
        s.trial += 1
        // the same planned trial repeated (after a switch/gap) keeps its uid; two idles in one round do not collide
        let key = st.uid.map { "uid\($0)" } ?? "\(st.block)|\(st.round)|\(st.step)|\(st.motion)|t\(s.trial)"
        s.attempts[key, default: 0] += 1
        if let v = live {
            s.meta.liveChecked = (s.meta.liveChecked ?? 0) + 1
            if v.ok { s.meta.liveOK = (s.meta.liveOK ?? 0) + 1 }
        }
        let fields: [String] = [String(hostNs), String(sensorNs), st.block, st.cueKind, String(st.round), String(s.trial),
                                String(st.step), st.motion, st.condition, String(format: "%.2f", st.windowS),
                                [st.note, note].filter { !$0.isEmpty }.joined(separator: "; "), st.module,
                                String(s.attempts[key] ?? 1), status, shownNs.map { String($0) } ?? "",
                                live.map { String($0.count) } ?? "", live?.text ?? "",
                                check?.flags.joined(separator: ";") ?? "", check?.rule ?? "", check?.model ?? "",
                                check?.dtw ?? "", vote, check.map { String(format: "%.3f", $0.peakRot) } ?? ""]
        state = s
        if status == "done", ["rounds", "practice", "commands"].contains(st.cueKind), st.motion != "idle" {
            lastTrial = (st, s.trial, shownNs ?? sensorNs)
            markable = st.motion
        }
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
        if phase == .paused || pausePending {
            pauseRequested = false; pausePending = false; note("experimenter: resume")
        } else {
            pauseRequested = true; pausePending = true; note("experimenter: pause after this step")
        }
    }
    func requestRecalibration() { recalibrateRequested = true; note("experimenter: recalibrate") }
    func stop() { stopRequested = true; skipFlag = true; continueFlag = true; note("experimenter: end session") }
    func toggleEndAfterRound() {
        endAfterRound.toggle()
        note(endAfterRound ? "experimenter: end after this round" : "experimenter: cancel end after this round")
    }
    /// v3.5: the experimenter saw the person do the WRONG gesture (or none) in the last trial. Nothing is deleted:
    /// a row with status "marked_wrong" pointing at that trial is added to cues.csv (column trial of the marked row
    /// is in the note), and the same trial is done again right after the current step.
    func markLastWrong() {
        guard let last = lastTrial, redoStep == nil else { return }
        logCue(last.step, hostNs: hostNowNs(), sensorNs: last.shownNs, status: "marked_wrong",
               note: "experimenter: trial \(last.trial) was wrong", shownNs: last.shownNs)
        lastTrial = nil                      // marking the same trial twice does nothing
        markable = ""
        var again = last.step
        again.note = [last.step.note, "redo: trial \(last.trial) marked wrong"].filter { !$0.isEmpty }.joined(separator: "; ")
        again.sub = "AGAIN: " + last.step.sub
        again.windowS -= last.step.spoken.isEmpty ? 0 : timing.speechS   // the logged window had the speech time added
        redoStep = again
        redoInfo = "Will redo \(last.step.motion.replacingOccurrences(of: "_", with: " ")) next"
        note("experimenter: last trial wrong (\(last.step.motion), trial \(last.trial)); redo queued")
    }

    /// The person cannot do the motion being cued: skip it from now on (logged, not counted as an error).
    func cantDoCurrent() {
        guard let st = state, st.index < st.steps.count else { return }
        let m = st.steps[st.index].motion
        guard !m.isEmpty, m != "idle", m != "still", !m.hasPrefix("calib") else { return }
        var s = st
        var list = s.cantDo ?? []
        for part in m.components(separatedBy: ">") where !list.contains(part) { list.append(part) }
        s.cantDo = list
        state = s
        note("experimenter: cannot do \(m)")
        skipFlag = true
    }
    private func isCantDo(_ st: Step) -> Bool {
        guard let list = state?.cantDo, !list.isEmpty, st.kind == .cue else { return false }
        return st.motion.components(separatedBy: ">").contains { list.contains($0) }
    }

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
        recorder.engine.setModel(liveModel)
        recorder.engine.onResult = { [weak self] r in Task { @MainActor in self?.collect(r) } }
        recorder.engine.onNod = nil
        recorder.engine.onCalibrated = { [weak self] h in
            Task { @MainActor in
                self?.note(h.map { String(format: "trial checks: head frame ready (heading %.2f rad)", $0) }
                           ?? "trial checks: no head frame from the nods")
            }
        }
        recorder.engine.onEarbudSwitch = nil
        if let cam = camera {
            // same number as the stream segment; frame times on the sensor clock go to scene_NNN_frames.csv
            let n = s.meta.segments - 1
            cam.start(segment: n) { [weak self] msg in Task { @MainActor in self?.note("scene video: " + msg) } }
        }
        phase = .running
        Platform.configureAudio()
        Platform.keepAwake(true)
        task = Task { await self.loop() }
    }

    private func earbudSwitched(from: String, to: String) {
        banner = "Earbud changed (\(from) -> \(to)). Put the AirPod(s) back as at the start; we will calibrate again."
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
                pausePending = false
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
            var step = s.steps[s.index]
            skipFlag = false
            switchDuringStep = false
            retakeNext = false
            if isCantDo(step) {
                logCue(step, hostNs: hostNowNs(), sensorNs: sensorNowNs(), status: "cant_do")
            } else {
                await run(step)
            }
            guard var st = state else { break }
            // a repeated trial takes over the end-of-block / end-of-module marks, so a block is marked done once
            if retakeNext && !switchDuringStep && !stopRequested {
                var again = step
                again.note = [step.note, "retake after check"].filter { !$0.isEmpty }.joined(separator: "; ")
                again.sub = "AGAIN: " + step.sub
                st.steps.insert(again, at: st.index + 1)
                step.endsBlock = false; step.endsModule = false
            }
            if switchDuringStep && step.kind == .cue && step.cueKind != "calibration" && !stopRequested {
                // the trial was disturbed (earbud switch or data gap): repeat it right after the recalibration
                var again = step
                again.note = [step.note, "repeat after earbud switch/gap"].filter { !$0.isEmpty }.joined(separator: "; ")
                again.endsBlock = s.steps[s.index].endsBlock; again.endsModule = s.steps[s.index].endsModule
                st.steps.insert(again, at: st.index + 1)
                step.endsBlock = false; step.endsModule = false
            }
            if var again = redoStep, !stopRequested {
                // v3.5 experimenter redo: right after this step; it takes over the end-of-block marks if it is the same trial
                if again.uid == step.uid {
                    again.endsBlock = step.endsBlock; again.endsModule = step.endsModule
                    step.endsBlock = false; step.endsModule = false
                }
                st.steps.insert(again, at: st.index + 1)
                redoStep = nil
                redoInfo = ""
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
            if endAfterRound && !stopRequested {
                let next = st.index < st.steps.count ? st.steps[st.index] : nil
                let sameRound = next.map { $0.kind == .cue && $0.block == step.block && $0.round == step.round && step.round > 0 } ?? false
                if !sameRound {
                    note("ended after the round (experimenter)")
                    endedAfterRound = true
                    stopRequested = true
                }
            }
        }
        finish()
    }

    /// How many motions a cue asks for (nil = not checked: pairs, the look-around, the closing still).
    private func expectedMotions(_ st: Step) -> Int? {
        switch st.cueKind {
        case "rounds", "practice":
            if st.motion == "idle" { return 0 }
            let n = motions[st.motion]?.expectedCount ?? 1
            return n == 0 ? nil : (n >= 2 ? 3 : 1)   // 3 = a double: one merged event or two both count
        case "commands": return 2
        case "calibration":
            if st.motion == "calib_nod" { return 1 }
            if st.motion == "still" && st.module != "closing" { return 0 }
            return nil
        default: return nil
        }
    }

    private func run(_ st: Step) async {
        // v3.7: "Last one was wrong" only right after a gesture: not across a break, a message or a calibration
        if st.kind != .cue || st.cueKind == "calibration" { lastTrial = nil; markable = "" }
        title = st.text
        sub = st.sub
        motion = ""
        cueID = ""
        if st.kind == .message && !st.motion.isEmpty {         // v3.3 watch step: show the demo while reading
            motion = motions[st.motion]?.demo ?? st.motion
            cueID = st.motion
        }
        switch st.kind {
        case .message:
            await speaker.say(st.text.lowercased())
            await waitForButton(.waitingContinue)
        case .cue:
            // v3.2 flow (option A): the name IS the go. Text + voice start together and the window opens at once
            // (people moved on the name anyway: P01 61 % before the old GO beep). The window is the planned window
            // plus the speech time; a green NOW bar shows it; one short beep marks its end. No beep before.
            // cues.csv: sensor_ns_est = shown_sensor_ns = the announcement; window_s = the whole window.
            var st = st
            st.windowS += st.spoken.isEmpty ? 0 : timing.speechS
            motion = motions[st.motion]?.demo ?? st.motion
            cueID = st.motion
            feedback = ""
            let shown = sensorNowNs()
            let stillCalib = st.cueKind == "calibration" && st.motion == "still"
            if skipFlag { logCue(st, hostNs: hostNowNs(), sensorNs: shown, status: "skipped", shownNs: shown); return }
            let h = hostNowNs(), t = shown
            if stillCalib { recorder.live.beginQuietCapture(); if st.module != "closing" { recorder.engine.beginStill() } }
            let anglesAtGo = recorder.angles
            if st.spoken.isEmpty {
                Beep.go()                                  // nothing to say (e.g. second motion of a pair): beep
            } else {
                let sp = speaker, text = st.spoken
                Task { @MainActor in await sp.say(text) }  // speak while the window already runs
            }
            windowS = st.windowS
            nowActive = true
            await wait(st.windowS)
            nowActive = false
            if !skipFlag && !(st.cueKind == "pairs" && st.step == 1) { Beep.end() }   // a pair's 2nd beep follows at once
            if stillCalib && !recorder.live.endQuietCapture() { note("live check: still pose too short, default quiet level") }
            if stillCalib && st.module != "closing" && !recorder.engine.endStill() { note("trial checks: still pose too short") }
            var verdict: LiveVerdict? = nil
            if let expected = expectedMotions(st), !skipFlag {
                try? await Task.sleep(nanoseconds: 500_000_000)       // let the detector close the last motion
                let v = recorder.live.verdict(from: shown - 300_000_000, to: t + Int64(st.windowS * 1e9), expected: expected)
                verdict = v
                feedback = v.text
                feedbackOK = v.ok
                // face / touch / breath motions hardly move the head: the motion count is logged, not shown
                if let d = motions[st.motion], !d.isHead { feedback = "" }
            }
            var check: TrialCheck? = nil
            var vote = ""
            if ["rounds", "practice", "commands"].contains(st.cueKind), st.motion != "idle", !skipFlag {
                let wa = shown - 300_000_000, wb = t + Int64(st.windowS * 1e9)
                var c = trialCheck(st, from: wa, to: wb, verdict: verdict, angles: anglesAtGo)
                vote = c.vote(expected: st.motion)
                if vote == "mismatch" {
                    c.flags.append("mismatch")
                    let seen = [c.rule, c.model, c.dtw].first { !$0.isEmpty && $0 != st.motion } ?? "something else"
                    feedback = "Looked like \(seen.replacingOccurrences(of: "_", with: " ")): once more, please"
                    feedbackOK = false
                } else if vote == "unsure" {
                    c.flags.append("unsure")
                }
                check = c
                let key = st.uid.map { "uid\($0)" } ?? ""
                let attempt = (state?.attempts[key] ?? 0) + 1
                let headMotion = motions[st.motion]?.isHead ?? true
                let failed = vote == "mismatch" || (headMotion && (verdict.map { !$0.ok } ?? false))
                if failed && timing.retakeOnce && attempt == 1 && st.cueKind != "practice" { retakeNext = true }
                if !failed && st.cueKind == "practice" && vote != "unsure", let ev = mainEvent(wa, wb) {
                    templates.add(st.motion, ev.headRot)
                }
            } else if st.cueKind == "rounds" && st.motion == "idle" {
                lastAngles = anglesAtGo
            }
            logCue(st, hostNs: h, sensorNs: t, status: skipFlag ? "skipped" : (switchDuringStep ? "disturbed" : "done"),
                   shownNs: shown, live: verdict, check: check, vote: vote)
            await wait(max(0, st.gapAfterS - (verdict == nil ? 0 : 0.5)))
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
            await speaker.say(st.cueKind == "rewear" ? "take both AirPods out and put them back in"
                              : (st.spoken.isEmpty ? "send the commands in order" : st.spoken))
            logCue(st, hostNs: hostNowNs(), sensorNs: sensorNowNs(), status: "start")
            await waitForButton(.waitingDone)
        case .manualEnd:
            logCue(st, hostNs: hostNowNs(), sensorNs: sensorNowNs(), status: "end")
        }
    }

    // ------------------------------------------------------------------ v3.1 trial checks
    private func collect(_ r: LiveResult) {
        results.append(r)
        if results.count > 100 { results.removeFirst(results.count - 100) }
    }

    /// The biggest recognised event that started inside the cue window.
    private func mainEvent(_ a: Int64, _ b: Int64) -> LiveResult? {
        results.filter { $0.startNs >= a && $0.startNs < b }
            .max { ($0.features["peak_rot"] ?? 0) < ($1.features["peak_rot"] ?? 0) }
    }

    private func trialCheck(_ st: Step, from a: Int64, to b: Int64, verdict: LiveVerdict?, angles: HeadAngles) -> TrialCheck {
        var c = TrialCheck()
        if let v = verdict, !v.ok { c.flags.append("count") }
        if let prev = lastAngles {
            let jump = max(abs(angles.pitch - prev.pitch), abs(angles.roll - prev.roll)) * 180 / Double.pi
            if jump > timing.postureJumpDeg { c.flags.append("posture_jump") }
        }
        lastAngles = angles
        guard st.cueKind != "commands", let ev = mainEvent(a, b) else { return c }
        c.peakRot = ev.features["peak_rot"] ?? 0
        let def = motions[st.motion]
        if (def?.isHead ?? true) && c.peakRot < timing.smallPeakRot { c.flags.append("too_small") }
        let single = (def?.expectedCount ?? 1) == 1
        let alias = def?.check ?? st.motion                    // v3.3: tilt_1x_left is checked as tilt_left
        if RULE_MOTIONS.contains(alias) && single {
            c.rule = ev.rules.motion == alias ? st.motion : ev.rules.motion
            if let m = liveModel, ev.model.accepted, m.direction[ev.model.kind] != nil {
                c.model = ev.model.motion == alias ? st.motion : ev.model.motion
            }
        }
        if st.cueKind != "practice", let near = templates.nearest(ev.headRot) { c.dtw = near.motion }
        return c
    }

    private func finish() {
        guard var s = state else { return }
        s.meta.ended = Date()
        let complete = s.index >= s.steps.count && !stopRequested
        s.meta.status = complete ? "complete" : "incomplete"
        s.meta.endedBy = complete ? "complete" : (endedAfterRound ? "end_after_round" : "end_session")
        state = s
        saveState()
        recorder.stopSegment()
        camera?.stop()
        try? cueFile?.close()
        try? noteFile?.close()
        recorder.onSwitch = nil
        recorder.onGap = nil
        recorder.engine.stop()
        recorder.engine.onResult = nil
        recorder.engine.onCalibrated = nil
        Platform.keepAwake(false)
        phase = .finished
        title = complete ? "DONE. Thank you!"
            : (endedAfterRound ? "Stopped after the round (saved). Next time continues from here."
               : "Session ended (saved). The unfinished round is planned again next time.")
        sub = ""
        onFinished?(s.meta)
    }

    /// Zip of the session folder next to it (for AirDrop / WhatsApp / Drive / pen drive).
    func exportZip() -> URL? { Platform.zip(folder: folder) }
}
