// Participants (APP_V2_PLAN.md section 3c): first name + number, what each person has done, per device.
// Stored as roster.json in the data folder. The first name is also in each session folder name and session.json.

import Foundation

struct SessionRecord: Codable, Hashable {
    var code: String          // "P05_s2"
    var folder: String        // session folder name
    var device: String
    var started: Date
    var status: String        // running / complete / incomplete
    var modulesDone: [String]
    var coreBlocksDone: [String]
}

struct Participant: Codable, Hashable, Identifiable {
    var number: Int
    var firstName: String
    var profile: [String: String]
    var coreDone: [String: [String]] = [:]   // device -> core block ids done on that device
    var modulesDone: [String] = []            // module ids done (any device)
    var modulesByDevice: [String: [String]] = [:]   // v3: device -> module ids done on that device
    var sessions: [SessionRecord] = []
    var selections: [String: [String: Int]] = [:]   // v3.6: experiment name -> chosen motion -> target reps

    var id: Int { number }
    var code: String { String(format: "P%02d", number) }

    init(number: Int, firstName: String, profile: [String: String]) {
        self.number = number
        self.firstName = firstName
        self.profile = profile
    }

    // older roster.json files have no modulesByDevice: fill in defaults instead of failing (and losing the roster)
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        number = try c.decode(Int.self, forKey: .number)
        firstName = try c.decode(String.self, forKey: .firstName)
        profile = try c.decodeIfPresent([String: String].self, forKey: .profile) ?? [:]
        coreDone = try c.decodeIfPresent([String: [String]].self, forKey: .coreDone) ?? [:]
        modulesDone = try c.decodeIfPresent([String].self, forKey: .modulesDone) ?? []
        modulesByDevice = try c.decodeIfPresent([String: [String]].self, forKey: .modulesByDevice) ?? [:]
        sessions = try c.decodeIfPresent([SessionRecord].self, forKey: .sessions) ?? []
        selections = try c.decodeIfPresent([String: [String: Int]].self, forKey: .selections) ?? [:]
    }

    func coreBlocksDone(device: String) -> [String] { coreDone[device] ?? [] }
    func modulesDone(device: String, perDevice: Bool) -> [String] { perDevice ? (modulesByDevice[device] ?? []) : modulesDone }

    var summary: String {
        var parts: [String] = []
        if sessions.isEmpty { parts.append("no sessions yet") }
        for s in sessions {
            parts.append("\(s.code.split(separator: "_").last ?? "") \(s.device): \(s.status)")
        }
        parts.append("modules done: " + (modulesDone.isEmpty ? "none" : modulesDone.sorted().joined(separator: ",")))
        return parts.joined(separator: " | ")
    }
}

struct Roster: Codable {
    var participants: [Participant] = []
}

final class RosterStore: ObservableObject {
    @Published private(set) var roster = Roster()
    private(set) var url: URL

    init(dataRoot: URL) {
        url = dataRoot.appendingPathComponent("roster.json")
        load()
    }

    func moveTo(dataRoot: URL) {
        url = dataRoot.appendingPathComponent("roster.json")
        load()
    }

    func load() {
        let dec = JSONDecoder()
        dec.dateDecodingStrategy = .iso8601
        if let data = try? Data(contentsOf: url), let r = try? dec.decode(Roster.self, from: data) {
            roster = r
        } else {
            roster = Roster()
        }
    }

    func save() {
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        enc.dateEncodingStrategy = .iso8601
        if let data = try? enc.encode(roster) { try? data.write(to: url, options: .atomic) }
    }

    var nextNumber: Int { (roster.participants.map(\.number).max() ?? 0) + 1 }

    /// number: the participant number the team assigned. Each phone/Mac keeps its own roster, so numbers must be
    /// agreed across devices (P01 Ghanshyam, P02 ...). nil = next free number on this device.
    func add(firstName: String, profile: [String: String], number: Int? = nil) -> Participant? {
        let n = number ?? nextNumber
        guard n > 0, participant(n) == nil else { return nil }
        let p = Participant(number: n, firstName: firstName, profile: profile)
        roster.participants.append(p)
        save()
        return p
    }

    func participant(_ number: Int) -> Participant? { roster.participants.first { $0.number == number } }

    /// v3.5: take a person off the list. Their session folders are MOVED (never deleted) into
    /// <data folder>/removed/<code>_<time>/ together with their roster entry (participant.json), so it can be undone.
    func remove(_ number: Int, dataRoot: URL) -> String {
        guard let p = participant(number) else { return "No participant \(number)." }
        let stamp = DateFormatter()
        stamp.dateFormat = "yyyyMMdd_HHmmss"
        let dest = dataRoot.appendingPathComponent("removed/\(p.code)_\(stamp.string(from: Date()))")
        let fm = FileManager.default
        try? fm.createDirectory(at: dest, withIntermediateDirectories: true)
        var moved = 0
        for s in p.sessions {
            let src = dataRoot.appendingPathComponent(s.folder)
            if fm.fileExists(atPath: src.path), (try? fm.moveItem(at: src, to: dest.appendingPathComponent(s.folder))) != nil {
                moved += 1
            }
        }
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        enc.dateEncodingStrategy = .iso8601
        if let d = try? enc.encode(p) { try? d.write(to: dest.appendingPathComponent("participant.json")) }
        roster.participants.removeAll { $0.number == number }
        save()
        return "Removed \(p.firstName) (\(p.code)); \(moved) session folder(s) moved to removed/\(dest.lastPathComponent)."
    }

    /// v3.5: fix a typo in the first name or the profile (the number stays: it is in the session folder names).
    func edit(_ number: Int, firstName: String, profile: [String: String]) {
        let name = firstName.trimmingCharacters(in: .whitespaces)
        update(number) { p in
            if !name.isEmpty { p.firstName = name }
            for (k, v) in profile { p.profile[k] = v }
        }
    }

    /// v3.5: a wrong number can be changed only before the person has recorded anything.
    func renumber(_ number: Int, to new: Int) -> Bool {
        guard new > 0, participant(new) == nil, let p = participant(number), p.sessions.isEmpty else { return false }
        update(number) { $0.number = new }
        return true
    }

    func update(_ number: Int, _ change: (inout Participant) -> Void) {
        guard let i = roster.participants.firstIndex(where: { $0.number == number }) else { return }
        change(&roster.participants[i])
        save()
    }
}
