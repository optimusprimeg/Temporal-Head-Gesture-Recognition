// Study plan: motions, commands, timing, the core and the optional modules (APP_V2_PLAN.md sections 3 and 3b).
// The default plan is written here; the app also saves it as plan.json in the data folder, and a plan.json found
// there is used instead (change the vocabulary after the pilot without rebuilding the app).

import Foundation

struct MotionDef: Codable, Hashable {
    var id: String
    var instruction: String   // shown on screen
    var spoken: String        // spoken through the AirPods before the beep
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
    case rounds, commands, pairs, selfPaced = "self_paced", negatives, rewear
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
}

struct ModuleDef: Codable, Hashable {
    var id: String          // "A" ... "G"
    var title: String
    var tests: String
    var rotate: Bool        // in the per-participant rotation (G is only filler)
    var blocks: [BlockDef]
}

struct Timing: Codable, Hashable {
    var readyS: Double = 0.8          // ready beep -> GO beep
    var windowS: Double = 4.0         // time reserved for one motion after GO
    var commandWindowS: Double = 6.0  // time reserved for a two-motion command
    var gapMinS: Double = 2.5         // random quiet gap after each window
    var gapMaxS: Double = 5.0
    var idlePerRound: Int = 2
    var breakEveryRounds: Int = 5
    var speechS: Double = 1.3         // estimated length of a spoken cue (for time planning only)
}

struct StudyPlan: Codable, Hashable {
    var version: String
    var motions: [MotionDef]
    var commands: [CommandDef]
    var timing: Timing
    var practicePerMotionFirst: Int   // practice trials per motion in a person's first session
    var practicePerMotionLater: Int
    var core: [BlockDef]
    var modules: [ModuleDef]

    func motion(_ id: String) -> MotionDef? { motions.first { $0.id == id } }
}

extension StudyPlan {
    static let defaultPlan: StudyPlan = {
        let motions = [
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
        let pairs: [(String, String, String)] = [
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
        ]
        let commands = pairs.map { CommandDef(first: $0.0, then: $0.1, message: $0.2) }
        let core: [BlockDef] = [
            BlockDef(id: "core.enrollment", kind: .rounds, title: "Enrollment", condition: "sitting, slow and clear", rounds: 2),
            BlockDef(id: "core.sitting", kind: .rounds, title: "Sitting", condition: "sitting", rounds: 6),
            BlockDef(id: "core.small", kind: .rounds, title: "Small (covert)", condition: "small: as small as you think a computer could still notice", rounds: 2),
            BlockDef(id: "core.commands", kind: .commands, title: "Commands", condition: "sitting", n: 10),
            BlockDef(id: "core.self_paced", kind: .selfPaced, title: "Commands at your own pace", condition: "sitting", n: 5, lists: 1),
            BlockDef(id: "core.negatives", kind: .negatives, title: "No gestures", activities: [
                Activity(text: "TALK: read the text aloud or chat with the experimenter", seconds: 120),
                Activity(text: "LISTEN and nod along naturally while the experimenter talks", seconds: 60),
            ]),
        ]
        let modules: [ModuleDef] = [
            ModuleDef(id: "A", title: "Re-wear", tests: "H1 wear", rotate: true, blocks: [
                BlockDef(id: "A.rewear", kind: .rewear, title: "Re-wear"),
                BlockDef(id: "A.sitting", kind: .rounds, title: "Sitting after re-wear", condition: "sitting (after re-wear)", rounds: 4),
            ]),
            ModuleDef(id: "B", title: "Speed and size", tests: "H4 covert", rotate: true, blocks: [
                BlockDef(id: "B.slow", kind: .rounds, title: "Slow", condition: "slow", rounds: 1),
                BlockDef(id: "B.fast", kind: .rounds, title: "Fast", condition: "fast", rounds: 1),
                BlockDef(id: "B.small", kind: .rounds, title: "Small (covert)", condition: "small: as small as you think a computer could still notice", rounds: 2),
            ]),
            ModuleDef(id: "C", title: "Posture", tests: "H1 posture", rotate: true, blocks: [
                BlockDef(id: "C.standing", kind: .rounds, title: "Standing", condition: "standing", rounds: 2),
                BlockDef(id: "C.offset", kind: .rounds, title: "Head already turned", condition: "keep your head a little tilted or turned, do the motion from there", rounds: 2),
            ]),
            ModuleDef(id: "D", title: "Walking", tests: "H1, H6", rotate: true, blocks: [
                BlockDef(id: "D.walking", kind: .rounds, title: "Walking", condition: "walking in place", rounds: 2),
                BlockDef(id: "D.negatives", kind: .negatives, title: "Walking, no gestures", activities: [
                    Activity(text: "WALK in place or around, no gestures", seconds: 120),
                ]),
            ]),
            ModuleDef(id: "E", title: "More commands", tests: "H2, H3", rotate: true, blocks: [
                BlockDef(id: "E.pairs", kind: .pairs, title: "Two motions back to back", gaps: [0.3, 0.6, 1.0], pairsPerGap: 3),
                BlockDef(id: "E.commands", kind: .commands, title: "Commands", n: 10),
                BlockDef(id: "E.self_paced", kind: .selfPaced, title: "Commands at your own pace", n: 5, lists: 1),
            ]),
            ModuleDef(id: "F", title: "Daily-life negatives", tests: "H6", rotate: true, blocks: [
                BlockDef(id: "F.negatives", kind: .negatives, title: "Daily life, no gestures", activities: [
                    Activity(text: "CHEW (gum or a snack)", seconds: 90),
                    Activity(text: "DRINK some water, normally", seconds: 60),
                    Activity(text: "USE YOUR PHONE: scroll, type, look around", seconds: 90),
                    Activity(text: "READ the text aloud", seconds: 90),
                    Activity(text: "WATCH the video and nod along if you agree", seconds: 90),
                ]),
            ]),
            ModuleDef(id: "G", title: "Extra sitting rounds", tests: "precision", rotate: false, blocks: [
                BlockDef(id: "G.sitting", kind: .rounds, title: "Extra sitting rounds", condition: "sitting", rounds: 1),
            ]),
        ]
        return StudyPlan(version: "v2.0-placeholder-vocab", motions: motions, commands: commands, timing: Timing(),
                         practicePerMotionFirst: 2, practicePerMotionLater: 1, core: core, modules: modules)
    }()

    /// plan.json in the data folder if present (and valid), else the default (which is then written there).
    static func load(dataRoot: URL) -> (StudyPlan, String) {
        let url = dataRoot.appendingPathComponent("plan.json")
        if let data = try? Data(contentsOf: url) {
            if let plan = try? JSONDecoder().decode(StudyPlan.self, from: data) {
                return (plan, "plan.json from the data folder (\(plan.version))")
            }
            return (defaultPlan, "plan.json in the data folder is INVALID, using the built-in plan")
        }
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        if let data = try? enc.encode(defaultPlan) { try? data.write(to: url) }
        return (defaultPlan, "built-in plan (\(defaultPlan.version)), saved as plan.json")
    }
}
