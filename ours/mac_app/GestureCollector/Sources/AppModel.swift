// App state: data folder, experiment files, roster, the current participant/session, and the screens' flow.
// Shared by the Mac and iPhone apps (platform differences: Platform.swift).

import Foundation
#if os(macOS)
import AppKit
#endif

@MainActor
final class AppModel: ObservableObject {
    enum Screen { case start, check, review, run, done, live }

    @Published var screen: Screen = .start
    @Published var dataRoot: URL
    @Published var plan: StudyPlan
    @Published var planSource: String
    @Published var experiments: [ExperimentFile] = []
    @Published var experimentFile = ""
    @Published var participantNumber: Int?
    @Published var device = ""
    @Published var budgetMin = 45.0
    @Published var preview: SessionPlan?
    @Published var runner: SessionRunner?
    @Published var lastMeta: SessionMeta?
    @Published var message = ""
    @Published var reference = HeadAngles()
    @Published var live: LiveSession?

    let recorder = Recorder()
    let roster: RosterStore
    // All AirPods with head tracking (CMHeadphoneMotionManager). The first two are the study's crossover pair.
    static let devices = ["AirPods Pro 2", "AirPods 5", "AirPods Pro 3", "AirPods Pro (1st gen)", "AirPods 4",
                          "AirPods 4 (ANC)", "AirPods 3", "AirPods Max", "Other"]
    static let crossover = Array(devices.prefix(2))
    @Published var detected: [String: String] = [:]   // what macOS reports about the connected AirPods
    private var seed: UInt64 = 0

    init() {
        #if os(macOS)
        let saved = UserDefaults.standard.string(forKey: "dataRoot")
        let root = saved.map { URL(fileURLWithPath: $0) } ?? Platform.defaultDataRoot
        #else
        let root = Platform.defaultDataRoot          // the app's Documents folder (Files app: On My iPhone)
        #endif
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        dataRoot = root
        roster = RosterStore(dataRoot: root)
        plan = StudyPlan.pilot
        planSource = ""
        reloadExperiments()
    }

    /// Rescans <data folder>/experiments and keeps the current choice if it is still valid (else the pilot).
    func reloadExperiments() {
        experiments = Experiments.load(dataRoot: dataRoot)
        let keep = UserDefaults.standard.string(forKey: "experimentFile") ?? experimentFile
        let pick = experiments.first { $0.file == keep && $0.plan != nil }
            ?? experiments.first { $0.file == "pilot.json" && $0.plan != nil }
            ?? experiments.first { $0.plan != nil }
        if let e = pick, let p = e.plan { chooseExperiment(e.file, p) }
        else { planSource = "No valid experiment file: using the built-in pilot" }
    }

    func chooseExperiment(_ file: String) {
        if let e = experiments.first(where: { $0.file == file }), let p = e.plan { chooseExperiment(file, p) }
    }

    private func chooseExperiment(_ file: String, _ p: StudyPlan) {
        experimentFile = file
        plan = p
        planSource = "\(p.name), \(file) (version \(p.version))"
        UserDefaults.standard.set(file, forKey: "experimentFile")
        if let n = participantNumber { select(n) }
    }

    var participant: Participant? { participantNumber.flatMap { roster.participant($0) } }

    #if os(macOS)
    func chooseDataRoot() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.prompt = "Use this folder"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        dataRoot = url
        UserDefaults.standard.set(url.path, forKey: "dataRoot")
        roster.moveTo(dataRoot: url)
        participantNumber = nil
        reloadExperiments()
    }
    #endif

    func addParticipant(firstName: String, profile: [String: String], number: Int?) {
        let name = firstName.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { message = "Type a first name."; return }
        guard let p = roster.add(firstName: name, profile: profile, number: number) else {
            message = "Participant number \(number ?? 0) is already used on this device."
            return
        }
        message = ""
        select(p.number)
    }

    func select(_ number: Int?) {
        participantNumber = number
        guard let p = participant else { return }
        let done = AppModel.crossover.filter { d in plan.core.allSatisfy { p.coreBlocksDone(device: d).contains($0.id) } }
        device = Planner.suggestedDevice(number: p.number, done: done, devices: AppModel.crossover)
    }

    // ------------------------------------------------------------------ which AirPods are connected
    /// What the system reports about the connected AirPods (Platform.headphones), saved with the session.
    func detectAirPods() {
        #if os(macOS)
        Task.detached {
            let found = Platform.headphones()
            await MainActor.run { self.detected = found }
        }
        #else
        detected = Platform.headphones()
        #endif
    }

    // ------------------------------------------------------------------ planning
    func makePreview() {
        guard let p = participant else { return }
        seed = UInt64.random(in: 1...UInt64(Int64.max))
        preview = Planner.plan(study: plan, participant: p, device: device, budgetMin: budgetMin, seed: seed)
        screen = .review
    }

    func minutes(_ s: Double) -> String { String(format: "%.0f min", s / 60) }

    // ------------------------------------------------------------------ sessions
    private func shortName(_ s: String) -> String {
        s.lowercased().filter { $0.isLetter || $0.isNumber }
    }

    func startSession() {
        guard let p = participant, let pv = preview else { return }
        let index = p.sessions.count + 1
        let code = "\(p.code)_s\(index)"
        let stamp = DateFormatter()
        stamp.dateFormat = "yyyyMMdd_HHmmss"
        let folderName = "\(p.code)_\(shortName(p.firstName))_s\(index)_\(shortName(device))_\(stamp.string(from: Date()))"
        let folder = dataRoot.appendingPathComponent(folderName)
        do { try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true) } catch {
            message = "Could not create the session folder: \(error.localizedDescription)"
            return
        }
        let meta = SessionMeta(participant: p.code, firstName: p.firstName, session: code, sessionIndex: index, device: device,
                               budgetMin: budgetMin, seed: seed, planVersion: plan.version, appVersion: APP_VERSION,
                               protocolVersion: PROTOCOL_VERSION, os: Platform.osVersion,
                               macModel: Platform.deviceModel, profile: p.profile, plannedCore: pv.coreBlocks,
                               plannedModules: pv.modules, fillerRounds: pv.fillerRounds, started: Date(), ended: nil,
                               status: "running")
        var m = meta
        m.detectedAirPods = detected
        m.experimentFile = experimentFile
        m.experimentName = plan.name
        m.platform = Platform.name
        // exactly what was run, next to the data
        if let d = Experiments.encode(plan) { try? d.write(to: folder.appendingPathComponent("experiment.json")) }
        let state = SessionState(meta: m, steps: pv.steps, index: 0, trial: 0, attempts: [:])
        roster.update(p.number) {
            $0.sessions.append(SessionRecord(code: code, folder: folderName, device: device, started: Date(),
                                             status: "running", modulesDone: [], coreBlocksDone: []))
        }
        launch(folder: folder, state: state, resuming: false)
    }

    private func launch(folder: URL, state: SessionState, resuming: Bool) {
        let r = SessionRunner(folder: folder, state: state, recorder: recorder, timing: plan.timing)
        r.onModuleDone = { [weak self] meta, id in Task { @MainActor in self?.recordProgress(meta, id) } }
        r.onFinished = { [weak self] meta in Task { @MainActor in self?.sessionFinished(meta) } }
        runner = r
        screen = .run
        r.start(resuming: resuming)
    }

    private func number(of meta: SessionMeta) -> Int? { Int(meta.participant.dropFirst()) }

    private func recordProgress(_ meta: SessionMeta, _ id: String) {
        guard let n = number(of: meta) else { return }
        roster.update(n) { p in
            if id.hasPrefix("core.") {
                var done = p.coreDone[meta.device] ?? []
                if !done.contains(id) { done.append(id) }
                p.coreDone[meta.device] = done
            } else {
                if !p.modulesDone.contains(id) { p.modulesDone.append(id) }
                var byDev = p.modulesByDevice[meta.device] ?? []
                if !byDev.contains(id) { byDev.append(id) }
                p.modulesByDevice[meta.device] = byDev
            }
            if let i = p.sessions.firstIndex(where: { $0.code == meta.session }) {
                p.sessions[i].modulesDone = meta.modulesDone
                p.sessions[i].coreBlocksDone = meta.coreBlocksDone
            }
        }
    }

    private func sessionFinished(_ meta: SessionMeta) {
        if let n = number(of: meta) {
            roster.update(n) { p in
                if let i = p.sessions.firstIndex(where: { $0.code == meta.session }) { p.sessions[i].status = meta.status }
            }
        }
        lastMeta = meta
        screen = .done
    }

    /// Sessions whose state says "running": the app was closed or crashed during them.
    var resumable: [(URL, SessionState)] {
        let items = (try? FileManager.default.contentsOfDirectory(at: dataRoot, includingPropertiesForKeys: nil)) ?? []
        return items.compactMap { url in
            guard let s = SessionRunner.loadState(folder: url), s.meta.status == "running", s.index < s.steps.count
            else { return nil }
            return (url, s)
        }.sorted { $0.0.lastPathComponent < $1.0.lastPathComponent }
    }

    func resume(_ folder: URL, _ state: SessionState) {
        participantNumber = number(of: state.meta)
        device = state.meta.device
        launch(folder: folder, state: state, resuming: true)
    }

    func closeResumable(_ folder: URL, _ state: SessionState) {
        var s = state
        s.meta.status = "incomplete"
        s.meta.ended = Date()
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        enc.dateEncodingStrategy = .iso8601
        if let d = try? enc.encode(s) { try? d.write(to: folder.appendingPathComponent("state.json"), options: .atomic) }
        if let d = try? enc.encode(s.meta) { try? d.write(to: folder.appendingPathComponent("session.json"), options: .atomic) }
        sessionFinished(s.meta)
        screen = .start
    }

    // ------------------------------------------------------------------ live recogniser
    func openLive() {
        live = LiveSession(recorder: recorder, dataRoot: dataRoot, plan: plan)
        screen = .live
    }

    func closeLive() {
        live?.stop()
        live = nil
        screen = .start
    }

    func backToStart() {
        runner = nil
        preview = nil
        screen = .start
    }
}
