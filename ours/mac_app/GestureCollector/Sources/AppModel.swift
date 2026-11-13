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
    // v3.6 gestures for this session: chosen motion -> target good reps (absent = off), the long idles, and how many
    // good reps this person already has per motion (this experiment, this AirPods model)
    @Published var targets: [String: Int] = [:]
    @Published var longIdle = true
    @Published var doneSoFar: [String: Int] = [:]
    private var sessionStudy: StudyPlan?

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
    /// v3.3: copy picked files into the right place: *.json -> experiments/, *.gif -> experiments/media/,
    /// a folder -> its *.json and *.gif (and a "media" subfolder's clips), then reload. Replaces same-named files.
    func importExperiments(_ urls: [URL]) {
        let fm = FileManager.default
        let exp = Experiments.folder(dataRoot), media = exp.appendingPathComponent("media")
        try? fm.createDirectory(at: media, withIntermediateDirectories: true)
        var json = 0, gif = 0, failed: [String] = []
        func copy(_ src: URL, to dir: URL) -> Bool {
            let dst = dir.appendingPathComponent(src.lastPathComponent)
            if src.standardizedFileURL == dst.standardizedFileURL { return true }
            try? fm.removeItem(at: dst)
            do { try fm.copyItem(at: src, to: dst); return true } catch { failed.append(src.lastPathComponent); return false }
        }
        func take(_ u: URL) {
            switch u.pathExtension.lowercased() {
            case "json": if copy(u, to: exp) { json += 1 }
            case "gif": if copy(u, to: media) { gif += 1 }
            default: break
            }
        }
        for u in urls {
            let scoped = u.startAccessingSecurityScopedResource()
            defer { if scoped { u.stopAccessingSecurityScopedResource() } }
            var isDir: ObjCBool = false
            if fm.fileExists(atPath: u.path, isDirectory: &isDir), isDir.boolValue {
                let items = (try? fm.contentsOfDirectory(at: u, includingPropertiesForKeys: nil)) ?? []
                for i in items { take(i) }
                let sub = u.appendingPathComponent("media")
                for i in (try? fm.contentsOfDirectory(at: sub, includingPropertiesForKeys: nil)) ?? [] { take(i) }
            } else {
                take(u)
            }
        }
        reloadExperiments()
        message = "Imported \(json) experiment file(s) and \(gif) clip(s) into \(exp.path)"
            + (failed.isEmpty ? "" : ". Could not copy: " + failed.joined(separator: ", "))
    }

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
        targets = p.defaultTargets
        longIdle = p.hasLongIdle
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
        // v3.6: this person's last choice for this experiment, else the experiment's defaults
        if let saved = p.selections[plan.name] {
            targets = saved.filter { plan.motion($0.key) != nil }
            longIdle = plan.hasLongIdle && (saved["long_idle"] ?? 1) > 0
        } else {
            targets = plan.defaultTargets
            longIdle = plan.hasLongIdle
        }
        refreshDone()
    }

    // ------------------------------------------------------------------ v3.6 gesture choice
    func refreshDone() {
        guard let p = participant else { doneSoFar = [:]; return }
        doneSoFar = doneCounts(p).counts
    }

    func applyPreset(_ preset: PresetDef) {
        let d = plan.defaultTargets
        targets = Dictionary(preset.motions.compactMap { id in d[id].map { (id, targets[id] ?? $0) } },
                             uniquingKeysWith: { a, _ in a })
        longIdle = plan.hasLongIdle && preset.motions.contains("long_idle")
    }

    func setAll(_ on: Bool) {
        targets = on ? plan.defaultTargets : [:]
        longIdle = on && plan.hasLongIdle
    }

    func toggle(_ id: String, _ on: Bool) {
        if on { targets[id] = targets[id] ?? plan.defaultTargets[id] ?? 10 } else { targets[id] = nil }
    }

    /// Good reps per motion (rounds trials "done" minus those the experimenter marked wrong) and the last round
    /// number per rounds block, from this person's earlier sessions of the same experiment on this AirPods model.
    func doneCounts(_ p: Participant) -> (counts: [String: Int], lastRound: [String: Int]) {
        var counts: [String: Int] = [:], last: [String: Int] = [:]
        for rec in p.sessions where rec.device == device {
            let folder = dataRoot.appendingPathComponent(rec.folder)
            guard let ed = try? Data(contentsOf: folder.appendingPathComponent("experiment.json")),
                  let ran = try? JSONDecoder().decode(StudyPlan.self, from: ed), ran.name == plan.name,
                  let text = try? String(contentsOf: folder.appendingPathComponent("cues.csv"), encoding: .utf8)
            else { continue }
            var lines = text.split(whereSeparator: \.isNewline).map(String.init)
            guard !lines.isEmpty else { continue }
            let head = AppModel.csvFields(lines.removeFirst())
            guard let iB = head.firstIndex(of: "block"), let iK = head.firstIndex(of: "kind"),
                  let iR = head.firstIndex(of: "round"), let iM = head.firstIndex(of: "motion"),
                  let iS = head.firstIndex(of: "status") else { continue }
            for l in lines {
                let f = AppModel.csvFields(l)
                guard f.count > max(iB, iK, iR, iM, iS), f[iK] == "rounds" else { continue }
                if f[iS] == "done" { counts[f[iM], default: 0] += 1 }
                if f[iS] == "marked_wrong" { counts[f[iM], default: 0] -= 1 }
                if let r = Int(f[iR]) { last[f[iB]] = max(last[f[iB]] ?? 0, r) }
            }
        }
        return (counts.mapValues { max(0, $0) }, last)
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
        // v3.6: only the chosen gestures, each topped up to its target
        let study = plan.selecting(Set(targets.keys), longIdle: longIdle)
        let done = doneCounts(p)
        doneSoFar = done.counts
        sessionStudy = study
        preview = Planner.plan(study: study, participant: p, device: device, budgetMin: budgetMin, seed: seed,
                               targets: targets, doneCounts: done.counts, lastRound: done.lastRound)
        screen = .review
    }

    /// v3.4 continue a person: complete rounds per core rounds block, counted from the cues.csv of this person's
    /// earlier sessions with the same experiment (by name) on the same device. A round counts when every motion
    /// planned in it was done (or marked can't-do); a round cut off half way does not count.
    func doneRounds(_ p: Participant) -> [String: Int] {
        var out: [String: Int] = [:]
        let blocks = plan.core.filter { $0.kind == .rounds }
        guard !blocks.isEmpty else { return out }
        for rec in p.sessions where rec.device == device {
            let folder = dataRoot.appendingPathComponent(rec.folder)
            guard let ed = try? Data(contentsOf: folder.appendingPathComponent("experiment.json")),
                  let ran = try? JSONDecoder().decode(StudyPlan.self, from: ed), ran.name == plan.name,
                  let text = try? String(contentsOf: folder.appendingPathComponent("cues.csv"), encoding: .utf8)
            else { continue }
            var lines = text.split(whereSeparator: \.isNewline).map(String.init)
            guard !lines.isEmpty else { continue }
            let head = AppModel.csvFields(lines.removeFirst())
            guard let iB = head.firstIndex(of: "block"), let iK = head.firstIndex(of: "kind"),
                  let iR = head.firstIndex(of: "round"), let iM = head.firstIndex(of: "motion"),
                  let iS = head.firstIndex(of: "status") else { continue }
            var got: [String: [Int: Set<String>]] = [:]
            for l in lines {
                let f = AppModel.csvFields(l)
                guard f.count > max(iB, iK, iR, iM, iS), f[iK] == "rounds", f[iS] == "done" || f[iS] == "cant_do",
                      let r = Int(f[iR]) else { continue }
                got[f[iB], default: [:]][r, default: []].insert(f[iM])
            }
            for b in blocks {
                let ids = b.motions ?? plan.motions.map(\.id)
                var n = 0
                for (r, seen) in got[b.id] ?? [:] {
                    let need = ids.filter { (r - 1) % max(1, plan.motion($0)?.every ?? 1) == 0 }
                    if need.allSatisfy({ seen.contains($0) }) { n += 1 }
                }
                out[b.id, default: 0] += n
            }
        }
        return out
    }

    /// v3.5 end-of-session table: per motion, gesture trials done, flagged by the checks, marked wrong by the
    /// experimenter, and "Confused?" clicks (from notes.csv). Rounds, practice and commands rows only.
    struct SummaryRow: Identifiable { var id: String { motion }; var motion: String; var done = 0, flagged = 0, wrong = 0, confused = 0 }

    static func sessionSummary(folder: URL) -> [SummaryRow] {
        var rows: [String: SummaryRow] = [:]
        if let text = try? String(contentsOf: folder.appendingPathComponent("cues.csv"), encoding: .utf8) {
            var lines = text.split(whereSeparator: \.isNewline).map(String.init)
            if !lines.isEmpty {
                let head = csvFields(lines.removeFirst())
                if let iK = head.firstIndex(of: "kind"), let iM = head.firstIndex(of: "motion"),
                   let iS = head.firstIndex(of: "status"), let iF = head.firstIndex(of: "flags") {
                    for l in lines {
                        let f = csvFields(l)
                        guard f.count > max(iK, iM, iS, iF), ["rounds", "practice", "commands"].contains(f[iK]) else { continue }
                        var r = rows[f[iM]] ?? SummaryRow(motion: f[iM])
                        if f[iS] == "done" { r.done += 1; if !f[iF].isEmpty { r.flagged += 1 } }
                        if f[iS] == "marked_wrong" { r.wrong += 1 }
                        rows[f[iM]] = r
                    }
                }
            }
        }
        if let notes = try? String(contentsOf: folder.appendingPathComponent("notes.csv"), encoding: .utf8) {
            for l in notes.split(whereSeparator: \.isNewline) {
                guard let r = l.range(of: "confused: opened examples for ") else { continue }
                let m = String(l[r.upperBound...]).trimmingCharacters(in: CharacterSet(charactersIn: "\" "))
                var row = rows[m] ?? SummaryRow(motion: m)
                row.confused += 1
                rows[m] = row
            }
        }
        return rows.values.sorted { $0.motion < $1.motion }
    }

    /// One CSV line -> fields (handles "quoted, fields" and "" escapes).
    static func csvFields(_ line: String) -> [String] {
        var out: [String] = [], cur = "", quoted = false
        let it = Array(line)
        var i = 0
        while i < it.count {
            let c = it[i]
            if quoted {
                if c == "\"" {
                    if i + 1 < it.count && it[i + 1] == "\"" { cur.append("\""); i += 1 } else { quoted = false }
                } else { cur.append(c) }
            } else if c == "\"" { quoted = true }
            else if c == "," { out.append(cur); cur = "" }
            else { cur.append(c) }
            i += 1
        }
        out.append(cur)
        return out
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
        m.targets = targets
        m.longIdle = longIdle
        // exactly what was run (the chosen gestures only), next to the data
        if let d = Experiments.encode(sessionStudy ?? plan) { try? d.write(to: folder.appendingPathComponent("experiment.json")) }
        let chosen = targets.merging(["long_idle": longIdle ? 1 : 0]) { a, _ in a }
        let name = plan.name
        roster.update(p.number) { $0.selections[name] = chosen }
        let state = SessionState(meta: m, steps: pv.steps, index: 0, trial: 0, attempts: [:])
        roster.update(p.number) {
            $0.sessions.append(SessionRecord(code: code, folder: folderName, device: device, started: Date(),
                                             status: "running", modulesDone: [], coreBlocksDone: []))
        }
        launch(folder: folder, state: state, resuming: false)
    }

    private func launch(folder: URL, state: SessionState, resuming: Bool) {
        // the experiment that was actually run (saved next to the data) wins over the one chosen now (resume)
        var study = plan
        if let d = try? Data(contentsOf: folder.appendingPathComponent("experiment.json")),
           let p = try? JSONDecoder().decode(StudyPlan.self, from: d) { study = p }
        let r = SessionRunner(folder: folder, state: state, recorder: recorder, timing: study.timing, motions: study.motions)
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
