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

    func update(_ number: Int, _ change: (inout Participant) -> Void) {
        guard let i = roster.participants.firstIndex(where: { $0.number == number }) else { return }
        change(&roster.participants[i])
        save()
    }
}
