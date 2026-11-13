// Experiment files (v3): everything about a protocol lives in a JSON file, not in the app. The app lists every
// *.json in <data folder>/experiments/ and the experimenter picks one per session. Built-in experiments (pilot,
// selftest) are written there on first start and refreshed when the app brings a newer built-in version, unless
// the file was edited (an edited file must get its own "version", which is then left alone).
//
// A file holds: motions, commands, timing, the core blocks (everyone, once per AirPods model), optional modules,
// and the ordering rules:
//   counterbalance   groups of core block ids whose order rotates by participant number
//   requireOneOf     groups of module ids: each person does at least one module of each group
//   modulesPerDevice track optional modules per AirPods model (true) or per person (false)
//   fillModule       module whose first block (rounds) fills leftover time
// Block kinds: rounds, commands, pairs, self_paced, negatives, rewear, free (start/done with your own instructions),
// message (an instruction screen). Any field may be left out: defaults are filled in, so hand-written files stay
// short. A broken file is refused with a list of what is wrong (validate()).

import Foundation

struct MotionDef: Codable, Hashable {
    var id: String
    var instruction: String   // shown on screen
    var spoken: String        // spoken through the AirPods before the beep
    // v3.1 (all optional in the file)
    var expect: Int? = nil    // motions the detector should see (1 = single, 2 = double); nil = 1; 0 = not checked
    var group: String? = nil  // head / face / touch / breath / other. Only "head" singles get the rule check.
    var demo: String? = nil   // head animation: a motions8 id or several, comma-separated ("tilt_left,tilt_left");
                              // nil = id itself. A clip <data folder>/experiments/media/<id>.gif wins when present.
    // v3.3 instruction card + scheduling
    var how: String? = nil    // one line: how to do it (shown under the title)
    var avoid: String? = nil  // one line: what not to do
    var every: Int? = nil     // rounds: in every n-th round only (2 = half the reps); nil = every round
    var check: String? = nil  // the single head motion our rules/model call it (tilt_1x_left -> "tilt_left")
    var ref: String? = nil    // v3.4: web link to real examples ("Confused?" button); a link only, nothing is stored

    init(id: String, instruction: String, spoken: String, expect: Int? = nil, group: String? = nil, demo: String? = nil) {
        self.id = id; self.instruction = instruction; self.spoken = spoken
        self.expect = expect; self.group = group; self.demo = demo
    }
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        instruction = try c.decodeIfPresent(String.self, forKey: .instruction) ?? id.replacingOccurrences(of: "_", with: " ").uppercased()
        spoken = try c.decodeIfPresent(String.self, forKey: .spoken) ?? id.replacingOccurrences(of: "_", with: " ")
        expect = try c.decodeIfPresent(Int.self, forKey: .expect)
        group = try c.decodeIfPresent(String.self, forKey: .group)
        demo = try c.decodeIfPresent(String.self, forKey: .demo)
        how = try c.decodeIfPresent(String.self, forKey: .how)
        avoid = try c.decodeIfPresent(String.self, forKey: .avoid)
        every = try c.decodeIfPresent(Int.self, forKey: .every)
        check = try c.decodeIfPresent(String.self, forKey: .check)
        ref = try c.decodeIfPresent(String.self, forKey: .ref)
    }
    /// how + avoid as one line for the screen ("" if neither is set)
    var card: String {
        [how, avoid.map { "Don't: \($0)" }].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: "   ·   ")
    }
    var expectedCount: Int { expect ?? 1 }
    var isHead: Bool { (group ?? "head") == "head" }
}

struct CommandDef: Codable, Hashable {
    var first: String
    var then: String
    var message: String
}

struct Activity: Codable, Hashable {
    var text: String
    var seconds: Double
}

enum BlockKind: String, Codable {
    case rounds, commands, pairs, selfPaced = "self_paced", negatives, rewear, free, message
}

struct BlockDef: Codable, Hashable {
    var id: String
    var kind: BlockKind
    var title: String
    var condition: String = "sitting"
    var rounds: Int = 0             // rounds
    var n: Int = 0                  // commands: how many; self_paced: commands per list
    var lists: Int = 0              // self_paced
    var gaps: [Double] = []         // pairs: pause between the two motions (s)
    var pairsPerGap: Int = 0        // pairs
    var activities: [Activity] = [] // negatives
    var motions: [String]? = nil    // nil = all motions of the plan
    var text: String? = nil         // free / message: instructions; rounds / commands: replaces the default instructions
    var estimateS: Double? = nil    // free: expected duration (time planning only)
    var minRounds: Int? = nil       // rounds: may be cut down to this many when the time is short (nil = never cut)
    var roundStart: Int? = nil      // v3.4 (planner only): rounds already recorded in earlier sessions; numbering continues

    init(id: String, kind: BlockKind, title: String, condition: String = "sitting", rounds: Int = 0, n: Int = 0,
         lists: Int = 0, gaps: [Double] = [], pairsPerGap: Int = 0, activities: [Activity] = [],
         motions: [String]? = nil, text: String? = nil, estimateS: Double? = nil) {
        self.id = id; self.kind = kind; self.title = title; self.condition = condition; self.rounds = rounds
        self.n = n; self.lists = lists; self.gaps = gaps; self.pairsPerGap = pairsPerGap; self.activities = activities
        self.motions = motions; self.text = text; self.estimateS = estimateS
    }

    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        kind = try c.decode(BlockKind.self, forKey: .kind)
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? id
        condition = try c.decodeIfPresent(String.self, forKey: .condition) ?? "sitting"
        rounds = try c.decodeIfPresent(Int.self, forKey: .rounds) ?? 0
        n = try c.decodeIfPresent(Int.self, forKey: .n) ?? 0
        lists = try c.decodeIfPresent(Int.self, forKey: .lists) ?? 0
        gaps = try c.decodeIfPresent([Double].self, forKey: .gaps) ?? []
        pairsPerGap = try c.decodeIfPresent(Int.self, forKey: .pairsPerGap) ?? 0
        activities = try c.decodeIfPresent([Activity].self, forKey: .activities) ?? []
        motions = try c.decodeIfPresent([String].self, forKey: .motions)
        text = try c.decodeIfPresent(String.self, forKey: .text)
        estimateS = try c.decodeIfPresent(Double.self, forKey: .estimateS)
        minRounds = try c.decodeIfPresent(Int.self, forKey: .minRounds)
        roundStart = try c.decodeIfPresent(Int.self, forKey: .roundStart)
    }
}

struct ModuleDef: Codable, Hashable {
    var id: String          // "A" ... "G"
    var title: String
    var tests: String
    var rotate: Bool        // in the per-participant rotation (the fill module is not)
    var blocks: [BlockDef]

    init(id: String, title: String, tests: String, rotate: Bool, blocks: [BlockDef]) {
        self.id = id; self.title = title; self.tests = tests; self.rotate = rotate; self.blocks = blocks
    }
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? id
        tests = try c.decodeIfPresent(String.self, forKey: .tests) ?? ""
        rotate = try c.decodeIfPresent(Bool.self, forKey: .rotate) ?? true
        blocks = try c.decode([BlockDef].self, forKey: .blocks)
    }
}

struct Timing: Codable, Hashable {
    var readyS: Double = 0.8          // pause before the GO beep
    var windowS: Double = 4.0         // time reserved for one motion after GO
    var commandWindowS: Double = 6.0  // time reserved for a two-motion command
    var gapMinS: Double = 2.5         // random quiet gap after each window
    var gapMaxS: Double = 5.0
    var idlePerRound: Int = 2
    var breakEveryRounds: Int = 5
    var speechS: Double = 1.3         // estimated length of a spoken cue (for time planning only)
    // v3.1 trial checks
    var retakeOnce: Bool = true       // a trial that fails the check is repeated once, right away
    var smallPeakRot: Double = 0.15   // rad/s: a head motion below this peak is flagged "too_small" (flag only)
    var postureJumpDeg: Double = 25   // head pitch/roll change since the previous cue above this: flag "posture_jump"

    init() {}
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        let t = Timing()
        readyS = try c.decodeIfPresent(Double.self, forKey: .readyS) ?? t.readyS
        windowS = try c.decodeIfPresent(Double.self, forKey: .windowS) ?? t.windowS
        commandWindowS = try c.decodeIfPresent(Double.self, forKey: .commandWindowS) ?? t.commandWindowS
        gapMinS = try c.decodeIfPresent(Double.self, forKey: .gapMinS) ?? t.gapMinS
        gapMaxS = try c.decodeIfPresent(Double.self, forKey: .gapMaxS) ?? t.gapMaxS
        idlePerRound = try c.decodeIfPresent(Int.self, forKey: .idlePerRound) ?? t.idlePerRound
        breakEveryRounds = try c.decodeIfPresent(Int.self, forKey: .breakEveryRounds) ?? t.breakEveryRounds
        speechS = try c.decodeIfPresent(Double.self, forKey: .speechS) ?? t.speechS
        retakeOnce = try c.decodeIfPresent(Bool.self, forKey: .retakeOnce) ?? t.retakeOnce
        smallPeakRot = try c.decodeIfPresent(Double.self, forKey: .smallPeakRot) ?? t.smallPeakRot
        postureJumpDeg = try c.decodeIfPresent(Double.self, forKey: .postureJumpDeg) ?? t.postureJumpDeg
    }
}

struct StudyPlan: Codable, Hashable {
    var name: String = "Experiment"
    var about: String = ""
    var version: String
    var motions: [MotionDef]
    var commands: [CommandDef]
    var timing: Timing = Timing()
    var practicePerMotionFirst: Int = 2   // practice trials per motion in a person's first session
    var practicePerMotionLater: Int = 1
    var core: [BlockDef]
    var modules: [ModuleDef] = []
    var counterbalance: [[String]] = []   // core block id groups whose order rotates by participant number
    var requireOneOf: [[String]] = []     // module id groups: at least one of each per person
    var modulesPerDevice: Bool = false
    var fillModule: String? = "G"

    func motion(_ id: String) -> MotionDef? { motions.first { $0.id == id } }

    init(name: String, about: String, version: String, motions: [MotionDef], commands: [CommandDef], timing: Timing,
         practicePerMotionFirst: Int, practicePerMotionLater: Int, core: [BlockDef], modules: [ModuleDef],
         counterbalance: [[String]] = [], requireOneOf: [[String]] = [], modulesPerDevice: Bool = false,
         fillModule: String? = "G") {
        self.name = name; self.about = about; self.version = version; self.motions = motions; self.commands = commands
        self.timing = timing; self.practicePerMotionFirst = practicePerMotionFirst
        self.practicePerMotionLater = practicePerMotionLater; self.core = core; self.modules = modules
        self.counterbalance = counterbalance; self.requireOneOf = requireOneOf
        self.modulesPerDevice = modulesPerDevice; self.fillModule = fillModule
    }

    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        name = try c.decodeIfPresent(String.self, forKey: .name) ?? "Experiment"
        about = try c.decodeIfPresent(String.self, forKey: .about) ?? ""
        version = try c.decodeIfPresent(String.self, forKey: .version) ?? "unversioned"
        motions = try c.decodeIfPresent([MotionDef].self, forKey: .motions) ?? StudyPlan.motions8
        commands = try c.decodeIfPresent([CommandDef].self, forKey: .commands) ?? []
        timing = try c.decodeIfPresent(Timing.self, forKey: .timing) ?? Timing()
        practicePerMotionFirst = try c.decodeIfPresent(Int.self, forKey: .practicePerMotionFirst) ?? 2
        practicePerMotionLater = try c.decodeIfPresent(Int.self, forKey: .practicePerMotionLater) ?? 1
        core = try c.decodeIfPresent([BlockDef].self, forKey: .core) ?? []
        modules = try c.decodeIfPresent([ModuleDef].self, forKey: .modules) ?? []
        counterbalance = try c.decodeIfPresent([[String]].self, forKey: .counterbalance) ?? []
        requireOneOf = try c.decodeIfPresent([[String]].self, forKey: .requireOneOf) ?? []
        modulesPerDevice = try c.decodeIfPresent(Bool.self, forKey: .modulesPerDevice) ?? false
        fillModule = try c.decodeIfPresent(String.self, forKey: .fillModule) ?? "G"
    }

    /// Everything wrong with the file (empty = fine).
    func validate() -> [String] {
        var e: [String] = []
        let motionIDs = Set(motions.map(\.id))
        if motions.isEmpty { e.append("no motions") }
        if motionIDs.count != motions.count { e.append("two motions have the same id") }
        for m in motions where (m.expect ?? 1) < 0 || (m.expect ?? 1) > 4 { e.append("motion \(m.id): expect must be 0...4") }
        for m in motions where (m.every ?? 1) < 1 { e.append("motion \(m.id): every must be at least 1") }
        for c in commands {
            if !motionIDs.contains(c.first) { e.append("command \(c.message): unknown motion '\(c.first)'") }
            if !motionIDs.contains(c.then) { e.append("command \(c.message): unknown motion '\(c.then)'") }
            if c.first == c.then { e.append("command \(c.message): the same motion twice is never recognised") }
        }
        let allBlocks = core + modules.flatMap(\.blocks)
        var seen = Set<String>()
        for b in allBlocks {
            if seen.contains(b.id) { e.append("block id '\(b.id)' is used twice") }
            seen.insert(b.id)
            for m in b.motions ?? [] where !motionIDs.contains(m) { e.append("block \(b.id): unknown motion '\(m)'") }
            switch b.kind {
            case .rounds: if b.rounds < 1 { e.append("block \(b.id): rounds must be at least 1") }
                if let m = b.minRounds, m < 1 || m > b.rounds { e.append("block \(b.id): minRounds must be 1...rounds") }
            case .commands, .selfPaced:
                if commands.isEmpty { e.append("block \(b.id): the file has no commands") }
                if b.n < 1 { e.append("block \(b.id): n must be at least 1") }
            case .pairs: if b.gaps.isEmpty || b.pairsPerGap < 1 { e.append("block \(b.id): needs gaps and pairsPerGap") }
                if (b.motions ?? motions.map(\.id)).count < 2 { e.append("block \(b.id): pairs need at least 2 motions") }
            case .negatives: if b.activities.isEmpty { e.append("block \(b.id): no activities") }
            case .free, .message: if (b.text ?? "").isEmpty { e.append("block \(b.id): needs a text") }
            case .rewear: break
            }
        }
        let moduleIDs = Set(modules.map(\.id))
        if moduleIDs.count != modules.count { e.append("two modules have the same id") }
        let coreIDs = Set(core.map(\.id))
        for g in counterbalance { for id in g where !coreIDs.contains(id) { e.append("counterbalance: '\(id)' is not a core block") } }
        for g in requireOneOf { for id in g where !moduleIDs.contains(id) { e.append("requireOneOf: no module '\(id)'") } }
        if let f = fillModule, !f.isEmpty, modules.first(where: { $0.id == f }) == nil, !modules.isEmpty, f != "G" {
            e.append("fillModule: no module '\(f)'")
        }
        return e
    }
}

// ---------------------------------------------------------------------------------------------- experiment files
struct ExperimentFile: Identifiable {
    var file: String             // file name in the experiments folder
    var plan: StudyPlan?
    var errors: [String]
    var id: String { file }
    var label: String { plan.map { "\($0.name) (\(file))" } ?? "\(file): INVALID" }
}

enum Experiments {
    static func folder(_ dataRoot: URL) -> URL { dataRoot.appendingPathComponent("experiments") }

    static func encode(_ p: StudyPlan) -> Data? {
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        return try? enc.encode(p)
    }

    /// Writes the built-in experiments (new, or older built-in versions nobody edited), then lists every file.
    static func load(dataRoot: URL) -> [ExperimentFile] {
        let dir = folder(dataRoot)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        for (file, plan) in StudyPlan.builtins {
            let url = dir.appendingPathComponent(file)
            var write = true
            if let d = try? Data(contentsOf: url), let old = try? JSONDecoder().decode(StudyPlan.self, from: d) {
                write = old.version.hasSuffix("-builtin") && old.version != plan.version
            } else if FileManager.default.fileExists(atPath: url.path) {
                write = false                               // broken user edit: show the error, do not overwrite
            }
            if write, let d = encode(plan) { try? d.write(to: url, options: .atomic) }
        }
        installBundled(into: dir)
        let names = ((try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? [])
            .filter { $0.hasSuffix(".json") }.sorted()
        return names.map { name in
            let url = dir.appendingPathComponent(name)
            guard let d = try? Data(contentsOf: url) else { return ExperimentFile(file: name, plan: nil, errors: ["cannot read"]) }
            do {
                let p = try JSONDecoder().decode(StudyPlan.self, from: d)
                let errs = p.validate()
                return ExperimentFile(file: name, plan: errs.isEmpty ? p : nil, errors: errs)
            } catch {
                return ExperimentFile(file: name, plan: nil, errors: ["not valid JSON for an experiment: \(describe(error))"])
            }
        }
    }

    /// v3.4: the experiment files shipped inside the app (ours/mac_app/experiments/*.json, copied by build.sh) are
    /// put into the data folder's experiments folder: when missing, or when the copy there is an older shipped
    /// version nobody edited (its checksum is remembered). An edited copy is never overwritten.
    static func installBundled(into dir: URL) {
        guard let src = Bundle.main.resourceURL?.appendingPathComponent("experiments"),
              let names = try? FileManager.default.contentsOfDirectory(atPath: src.path) else { return }
        for name in names where name.hasSuffix(".json") {
            guard let new = try? Data(contentsOf: src.appendingPathComponent(name)) else { continue }
            let dest = dir.appendingPathComponent(name), key = "bundledExperiment." + name
            if let old = try? Data(contentsOf: dest) {
                guard old != new else { UserDefaults.standard.set(checksum(new), forKey: key); continue }
                if let shipped = UserDefaults.standard.string(forKey: key) {
                    guard shipped == checksum(old) else { continue }          // edited after we shipped it: keep
                } else {
                    // imported by hand before v3.4: replace it, keeping the old file as <name>.bak
                    try? FileManager.default.removeItem(at: dest.appendingPathExtension("bak"))
                    try? FileManager.default.copyItem(at: dest, to: dest.appendingPathExtension("bak"))
                }
            }
            if (try? new.write(to: dest, options: .atomic)) != nil {
                UserDefaults.standard.set(checksum(new), forKey: key)
            }
        }
    }

    static func checksum(_ d: Data) -> String {           // FNV-1a, stable across launches
        var h: UInt64 = 0xcbf2_9ce4_8422_2325
        for b in d { h = (h ^ UInt64(b)) &* 0x100_0000_01b3 }
        return String(h, radix: 16)
    }

    /// The demo clip of a motion: <data folder>/experiments/media/<id>.gif (yours win), else the one shipped in the app.
    static func clip(_ id: String, dataRoot: URL) -> URL? {
        guard !id.isEmpty else { return nil }
        let mine = folder(dataRoot).appendingPathComponent("media/\(id).gif")
        if FileManager.default.fileExists(atPath: mine.path) { return mine }
        if let b = Bundle.main.resourceURL?.appendingPathComponent("experiments/media/\(id).gif"),
           FileManager.default.fileExists(atPath: b.path) { return b }
        return nil
    }

    static func describe(_ error: Error) -> String {
        switch error {
        case DecodingError.keyNotFound(let k, let ctx):
            return "missing '\(k.stringValue)' at \(ctx.codingPath.map(\.stringValue).joined(separator: "."))"
        case DecodingError.typeMismatch(_, let ctx), DecodingError.valueNotFound(_, let ctx):
            return "wrong value at \(ctx.codingPath.map(\.stringValue).joined(separator: ".")): \(ctx.debugDescription)"
        case DecodingError.dataCorrupted(let ctx):
            return "\(ctx.debugDescription) at \(ctx.codingPath.map(\.stringValue).joined(separator: "."))"
        default: return error.localizedDescription
        }
    }
}

// ---------------------------------------------------------------------------------------------- built-in experiments
extension StudyPlan {
    static let motions8: [MotionDef] = [
        MotionDef(id: "nod_down", instruction: "NOD DOWN once: chin down and straight back up to the front (don't hold it down)", spoken: "nod down"),
        MotionDef(id: "look_up", instruction: "LOOK UP once: chin up and straight back to the front (don't hold it up)", spoken: "look up"),
        MotionDef(id: "tilt_left", instruction: "TILT LEFT once: left ear toward left shoulder and straight back (don't hold)", spoken: "tilt left"),
        MotionDef(id: "tilt_right", instruction: "TILT RIGHT once: right ear toward right shoulder and straight back (don't hold)", spoken: "tilt right"),
        MotionDef(id: "turn_left", instruction: "TURN LEFT once: look left and straight back to the front (don't hold)", spoken: "turn left"),
        MotionDef(id: "turn_right", instruction: "TURN RIGHT once: look right and straight back to the front (don't hold)", spoken: "turn right"),
        MotionDef(id: "circle_cw", instruction: "CIRCLE CLOCKWISE once: your nose draws ONE clock on the wall in front, 12-3-6-9-12, then stop at front", spoken: "circle clockwise"),
        MotionDef(id: "circle_ccw", instruction: "CIRCLE COUNTER-CLOCKWISE once: your nose draws ONE clock, 12-9-6-3-12, then stop at front", spoken: "circle counter clockwise"),
    ]

    // Same placeholder dictionary as collector/config.py COMMANDS (final list after the pilot).
    static let commands20: [CommandDef] = [
        ("tilt_left", "nod_down", "GO FORWARD"), ("tilt_right", "nod_down", "FALL BACK"),
        ("tilt_left", "tilt_right", "HOLD POSITION"), ("tilt_right", "tilt_left", "MOVE"),
        ("circle_cw", "nod_down", "NEED BACKUP"), ("circle_ccw", "nod_down", "ABORT"),
        ("turn_left", "nod_down", "ENEMY LEFT"), ("turn_right", "nod_down", "ENEMY RIGHT"),
        ("look_up", "nod_down", "ACK"), ("look_up", "tilt_left", "YES"), ("look_up", "tilt_right", "NO"),
        ("circle_cw", "tilt_left", "MOVE LEFT"), ("circle_cw", "tilt_right", "MOVE RIGHT"),
        ("turn_left", "look_up", "WAIT"), ("turn_right", "look_up", "READY"),
        ("nod_down", "circle_cw", "REGROUP"), ("nod_down", "circle_ccw", "COVER ME"),
        ("tilt_left", "circle_ccw", "STOP"), ("tilt_right", "circle_cw", "CLEAR"),
        ("look_up", "circle_ccw", "REPEAT"),
    ].map { CommandDef(first: $0.0, then: $0.1, message: $0.2) }

    static let pauseText = "Each command = first motion, back to the front, a SHORT STILL PAUSE (about half a second), then the second motion. After the beep."

    /// Pilot v3: the v2.2 plan + the fixes from the independent check (PROJECT_REVIEW.md, website status page):
    /// sitting/small counterbalanced, no-gesture time split early/late and raised to 8 min, re-wear or posture
    /// required, modules tracked per AirPods model, pause instruction for commands.
    static let pilot: StudyPlan = {
        let small = "small: as small as you think a computer could still notice"
        let core: [BlockDef] = [
            BlockDef(id: "core.enrollment", kind: .rounds, title: "Enrollment", condition: "sitting, slow and clear", rounds: 2),
            BlockDef(id: "core.sitting", kind: .rounds, title: "Sitting", condition: "sitting", rounds: 6),
            BlockDef(id: "core.negatives_a", kind: .negatives, title: "No gestures (1)", activities: [
                Activity(text: "TALK: read the text aloud or chat with the experimenter", seconds: 90),
                Activity(text: "LISTEN and nod along naturally while the experimenter talks", seconds: 60),
                Activity(text: "LOOK BEHIND: turn your whole body to look behind you, a few times, then face front", seconds: 40),
                Activity(text: "USE YOUR PHONE: scroll, type, look around", seconds: 50),
            ]),
            BlockDef(id: "core.small", kind: .rounds, title: "Small (covert)", condition: small, rounds: 2),
            BlockDef(id: "core.commands", kind: .commands, title: "Commands", condition: "sitting", n: 10, text: pauseText),
            BlockDef(id: "core.self_paced", kind: .selfPaced, title: "Commands at your own pace", condition: "sitting", n: 5, lists: 1),
            BlockDef(id: "core.negatives_b", kind: .negatives, title: "No gestures (2)", activities: [
                Activity(text: "TALK: tell the experimenter about your day", seconds: 90),
                Activity(text: "LOOK AROUND the room as if searching for something", seconds: 40),
                Activity(text: "STAND UP and SIT DOWN a few times", seconds: 40),
                Activity(text: "DRINK some water or eat a snack, normally", seconds: 40),
                Activity(text: "WATCH the video and nod along if you agree", seconds: 50),
            ]),
        ]
        let modules: [ModuleDef] = [
            ModuleDef(id: "A", title: "Re-wear", tests: "H1 wear", rotate: true, blocks: [
                BlockDef(id: "A.rewear", kind: .rewear, title: "Re-wear"),
                BlockDef(id: "A.sitting", kind: .rounds, title: "Sitting after re-wear", condition: "sitting (after re-wear)", rounds: 4),
            ]),
            ModuleDef(id: "B", title: "Speed and size", tests: "H3, H4", rotate: true, blocks: [
                BlockDef(id: "B.slow", kind: .rounds, title: "Slow", condition: "slow", rounds: 1),
                BlockDef(id: "B.fast", kind: .rounds, title: "Fast", condition: "fast", rounds: 1),
                BlockDef(id: "B.small", kind: .rounds, title: "Small (covert)", condition: small, rounds: 2),
            ]),
            ModuleDef(id: "C", title: "Posture", tests: "H1 posture", rotate: true, blocks: [
                BlockDef(id: "C.standing", kind: .rounds, title: "Standing", condition: "standing", rounds: 2),
                BlockDef(id: "C.offset", kind: .rounds, title: "Head already turned", condition: "keep your head a little tilted or turned, do the motion from there", rounds: 2),
            ]),
            ModuleDef(id: "D", title: "Walking", tests: "H1, H6, body vs head turn", rotate: true, blocks: [
                BlockDef(id: "D.walking", kind: .rounds, title: "Walking", condition: "walking slowly around the room, turning at the corners", rounds: 2),
                BlockDef(id: "D.commands", kind: .commands, title: "Commands while walking", condition: "walking slowly around the room", n: 10, text: pauseText),
                BlockDef(id: "D.negatives", kind: .negatives, title: "Walking, no gestures", activities: [
                    Activity(text: "WALK around the room at a normal pace, turning at the corners, no gestures", seconds: 90),
                    Activity(text: "WALK and TURN AROUND: walk, stop, turn your whole body, walk back. No gestures", seconds: 60),
                ]),
            ]),
            ModuleDef(id: "E", title: "More commands", tests: "H2, H3 (pauses)", rotate: true, blocks: [
                BlockDef(id: "E.pairs", kind: .pairs, title: "Two motions back to back", gaps: [0.3, 0.6, 1.0], pairsPerGap: 3),
                BlockDef(id: "E.commands", kind: .commands, title: "Commands", n: 10, text: pauseText),
                BlockDef(id: "E.self_paced", kind: .selfPaced, title: "Commands at your own pace", n: 5, lists: 1),
            ]),
            ModuleDef(id: "F", title: "Daily-life negatives", tests: "H6", rotate: true, blocks: [
                BlockDef(id: "F.negatives", kind: .negatives, title: "Daily life, no gestures", activities: [
                    Activity(text: "CHEW (gum or a snack)", seconds: 90),
                    Activity(text: "USE YOUR PHONE: scroll, type, look around", seconds: 90),
                    Activity(text: "READ the text aloud", seconds: 90),
                    Activity(text: "CHAT with someone, look at them while you talk", seconds: 90),
                    Activity(text: "WATCH the video and nod along if you agree", seconds: 90),
                ]),
            ]),
            ModuleDef(id: "G", title: "Extra sitting rounds", tests: "precision", rotate: false, blocks: [
                BlockDef(id: "G.sitting", kind: .rounds, title: "Extra sitting rounds", condition: "sitting", rounds: 1),
            ]),
        ]
        return StudyPlan(name: "Pilot v3", about: "Pilot protocol: 8 motions, 20 placeholder commands. Core about 33 min with setup; optional modules fill the rest.",
                         version: "pilot-v3-builtin", motions: motions8, commands: commands20, timing: Timing(),
                         practicePerMotionFirst: 2, practicePerMotionLater: 1, core: core, modules: modules,
                         counterbalance: [["core.sitting", "core.small"]], requireOneOf: [["A", "C"]],
                         modulesPerDevice: true, fillModule: "G")
    }()

    /// Self-test for the developer (P01), with the analysis PC reading the data live: the open questions about
    /// commands (pause length, axis-change cut, same-family pairs, fast doubles), plus no-gesture and walking time.
    static let selftest: StudyPlan = {
        let core: [BlockDef] = [
            BlockDef(id: "st.slow", kind: .rounds, title: "Single motions, slow", condition: "slow", rounds: 1),
            BlockDef(id: "st.normal", kind: .rounds, title: "Single motions, normal", condition: "sitting", rounds: 1),
            BlockDef(id: "st.fast", kind: .rounds, title: "Single motions, fast", condition: "fast", rounds: 1),
            BlockDef(id: "st.pairs", kind: .pairs, title: "Two motions at set pauses", gaps: [0.0, 0.3, 0.5, 1.0], pairsPerGap: 3),
            BlockDef(id: "st.nopause", kind: .free, title: "Commands with NO pause",
                     text: "Do these 6 commands as fast as feels natural, with NO pause between the two motions, a few seconds apart:\n1. tilt left, nod down\n2. turn right, look up\n3. look up, tilt left\n4. nod down, circle cw\n5. turn left, nod down\n6. tilt right, circle cw\nPress Done when finished.", estimateS: 60),
            BlockDef(id: "st.samefamily", kind: .free, title: "Same-family pairs",
                     text: "Do each pair 3 times WITH a short pause, then 3 times WITHOUT a pause:\n1. tilt left, then tilt right\n2. look up, then nod down\nPress Done when finished.", estimateS: 70),
            BlockDef(id: "st.doubles", kind: .free, title: "Fast doubles",
                     text: "Do each 3 times, as a quick double (no pause):\n1. tilt left, tilt left\n2. nod down, nod down\nPress Done when finished.", estimateS: 40),
            BlockDef(id: "st.commands", kind: .commands, title: "Commands", n: 10, text: pauseText),
            BlockDef(id: "st.negatives", kind: .negatives, title: "No gestures", activities: [
                Activity(text: "TALK: talk about anything", seconds: 60),
                Activity(text: "LISTEN and nod along naturally", seconds: 40),
                Activity(text: "LOOK BEHIND with your whole body, a few times", seconds: 30),
                Activity(text: "USE YOUR PHONE: scroll, type", seconds: 40),
            ]),
            BlockDef(id: "st.walk", kind: .rounds, title: "Walking", condition: "walking slowly around the room, turning at the corners", rounds: 1),
            BlockDef(id: "st.walkcmd", kind: .commands, title: "Commands while walking", condition: "walking slowly around the room", n: 6, text: pauseText),
            BlockDef(id: "st.walkneg", kind: .negatives, title: "Walking, no gestures", activities: [
                Activity(text: "WALK around the room, turning at the corners, no gestures", seconds: 60),
            ]),
        ]
        return StudyPlan(name: "Self-test (developer)", about: "About 25 min. For tuning the pause, the axis-change cut and the walking cues with the data read live on the analysis PC.",
                         version: "selftest-v1-builtin", motions: motions8, commands: commands20, timing: Timing(),
                         practicePerMotionFirst: 0, practicePerMotionLater: 0, core: core, modules: [], fillModule: nil)
    }()

    static let builtins: [(String, StudyPlan)] = [("pilot.json", pilot), ("selftest.json", selftest)]
}
