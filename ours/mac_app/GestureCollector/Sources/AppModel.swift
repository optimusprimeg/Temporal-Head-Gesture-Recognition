// App state: data folder, plan, roster, the current participant/session, and the screens' flow.

import AppKit
import Foundation

@MainActor
final class AppModel: ObservableObject {
    enum Screen { case start, check, review, run, done, live }

    @Published var screen: Screen = .start
    @Published var dataRoot: URL
    @Published var plan: StudyPlan
    @Published var planSource: String
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
        let saved = UserDefaults.standard.string(forKey: "dataRoot")
        let root = saved.map { URL(fileURLWithPath: $0) }
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Documents/GestureCollector")
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        dataRoot = root
        roster = RosterStore(dataRoot: root)
        let loaded = StudyPlan.load(dataRoot: root)
        plan = loaded.0
        planSource = loaded.1
    }

    var participant: Participant? { participantNumber.flatMap { roster.participant($0) } }

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
        let loaded = StudyPlan.load(dataRoot: url)
        plan = loaded.0
        planSource = loaded.1
        participantNumber = nil
    }

    func addParticipant(firstName: String, profile: [String: String]) {
        let name = firstName.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { message = "Type a first name."; return }
        let p = roster.add(firstName: name, profile: profile)
        select(p.number)
    }

    func select(_ number: Int?) {
        participantNumber = number
        guard let p = participant else { return }
        let done = AppModel.crossover.filter { d in plan.core.allSatisfy { p.coreBlocksDone(device: d).contains($0.id) } }
        device = Planner.suggestedDevice(number: p.number, done: done, devices: AppModel.crossover)
    }

    // ------------------------------------------------------------------ which AirPods are connected
    /// Reads the connected headphones from `system_profiler SPBluetoothDataType -json` (name, product ID, firmware).
    func detectAirPods() {
        Task.detached {
            let found = AppModel.readBluetooth()
            await MainActor.run { self.detected = found }
        }
    }

    nonisolated static func readBluetooth() -> [String: String] {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/sbin/system_profiler")
        p.arguments = ["SPBluetoothDataType", "-json"]
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = FileHandle.nullDevice
        do { try p.run() } catch { return ["error": "system_profiler failed"] }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = root["SPBluetoothDataType"] as? [[String: Any]] else { return ["error": "no Bluetooth info"] }
        for item in items {
            for dev in (item["device_connected"] as? [[String: Any]]) ?? [] {
                for (name, value) in dev {
                    guard let props = value as? [String: Any] else { continue }
                    let minor = props["device_minorType"] as? String ?? ""
                    if name.localizedCaseInsensitiveContains("airpods") || minor == "Headphones" {
                        return ["name": name,
                                "productID": props["device_productID"] as? String ?? "",
                                "vendorID": props["device_vendorID"] as? String ?? "",
                                "firmware": props["device_firmwareVersion"] as? String ?? "",
                                "minorType": minor]
                    }
                }
            }
        }
        return ["error": "no connected headphones found"]
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
        let os = ProcessInfo.processInfo.operatingSystemVersion
        let meta = SessionMeta(participant: p.code, firstName: p.firstName, session: code, sessionIndex: index, device: device,
                               budgetMin: budgetMin, seed: seed, planVersion: plan.version, appVersion: APP_VERSION,
                               protocolVersion: PROTOCOL_VERSION,
                               os: "macOS \(os.majorVersion).\(os.minorVersion).\(os.patchVersion)",
                               macModel: macModel(), profile: p.profile, plannedCore: pv.coreBlocks,
                               plannedModules: pv.modules, fillerRounds: pv.fillerRounds, started: Date(), ended: nil,
                               status: "running")
        var m = meta
        m.detectedAirPods = detected
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
            } else if !p.modulesDone.contains(id) {
                p.modulesDone.append(id)
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
