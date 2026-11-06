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
    var sessions: [SessionRecord] = []

    var id: Int { number }
    var code: String { String(format: "P%02d", number) }

    func coreBlocksDone(device: String) -> [String] { coreDone[device] ?? [] }

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

    func add(firstName: String, profile: [String: String]) -> Participant {
        let p = Participant(number: nextNumber, firstName: firstName, profile: profile)
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
