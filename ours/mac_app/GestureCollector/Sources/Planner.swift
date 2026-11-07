// Turns an experiment file + participant + device + time budget into a flat list of steps (APP_V2_PLAN.md 3b).
// Rules: the core (not yet done on this device) comes first and is never cut, its counterbalanced groups in the
// participant's own order; optional modules follow in the participant's rotated order (Williams Latin square over
// the rotating modules, by participant number; a required group's module first if none of it is done yet) and are
// added only whole and only if they fit; the fill module fills leftover time. All random choices come from a seed stored in
// the session, so a session can be resumed with exactly the same steps.

import Foundation

struct SeededRNG: RandomNumberGenerator {
    private var state: UInt64
    init(seed: UInt64) { state = seed &+ 0x9E37_79B9_7F4A_7C15 }
    mutating func next() -> UInt64 {
        state &+= 0x9E37_79B9_7F4A_7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
        z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
        return z ^ (z >> 31)
    }
}

enum StepKind: String, Codable {
    case message        // instruction screen, experimenter presses Continue
    case cue            // spoken + beeps + window (calibration, practice, rounds, pairs, commands)
    case activity       // negatives: do an activity for N seconds
    case manualStart    // self-paced list / re-wear / free block: logged start, experimenter presses Done
    case manualEnd      // logged end
}

struct Step: Codable, Hashable {
    var module: String          // "core", "A"... ("setup" for calibration/practice)
    var block: String           // block id, e.g. "core.sitting"
    var kind: StepKind
    var cueKind: String = ""    // cue log kind: calibration, practice, rounds, pairs, commands, negatives, self_paced, rewear
    var round: Int = 0
    var step: Int = 0
    var motion: String = ""
    var condition: String = ""
    var windowS: Double = 0
    var gapAfterS: Double = 0
    var readyS: Double = 0      // 0 = no ready beep (second motion of a pair)
    var spoken: String = ""
    var text: String = ""
    var sub: String = ""
    var note: String = ""
    var endsBlock: Bool = false
    var endsModule: Bool = false
    var uid: Int? = nil         // planned trial id (a repeated trial keeps it; inserted calibrations have none)
}

struct SessionPlan: Codable {
    var steps: [Step]
    var coreBlocks: [String]      // core blocks planned
    var modules: [String]         // optional modules planned (in order)
    var fillerRounds: Int
    var estimateS: Double
    var warnings: [String]
}

enum Planner {
    /// Williams design: row r = r, r+1, r-1, r+2, r-2, ... (mod n). Balanced first-order carryover for even n.
    /// A module with a re-wear block is never last (it recalibrates; better followed by something).
    static func moduleOrder(number: Int, rotating: [String], available: [String], neverLast: Set<String> = []) -> [String] {
        let n = rotating.count
        guard n > 0 else { return [] }
        let r = ((number - 1) % n + n) % n
        var offsets = [0]
        var k = 1
        while offsets.count < n {
            offsets.append(k)
            if offsets.count < n { offsets.append(-k) }
            k += 1
        }
        var order = offsets.map { rotating[((r + $0) % n + n) % n] }
        if order.count > 1, let last = order.last, neverLast.contains(last) { order.swapAt(order.count - 1, order.count - 2) }
        return order.filter { available.contains($0) }
    }

    /// Core blocks in this participant's order: each counterbalance group's blocks swap places by rotation.
    static func coreOrder(_ core: [BlockDef], groups: [[String]], number: Int) -> [BlockDef] {
        var out = core
        for g in groups {
            let positions = out.indices.filter { g.contains(out[$0].id) }
            guard positions.count > 1 else { continue }
            let blocks = positions.map { out[$0] }
            let r = ((number - 1) % blocks.count + blocks.count) % blocks.count
            for (i, p) in positions.enumerated() { out[p] = blocks[(i + r) % blocks.count] }
        }
        return out
    }

    /// Device order (crossover): odd numbers start with the first device of the list, even with the second.
    static func suggestedDevice(number: Int, done: [String], devices: [String]) -> String {
        let order: [String] = number % 2 == 1 ? devices : Array(devices.reversed())
        return order.first { !done.contains($0) } ?? order[0]
    }

    static func duration(_ s: Step, _ t: Timing) -> Double {
        switch s.kind {
        case .message: return 15
        case .cue: return (s.spoken.isEmpty ? 0 : t.speechS) + s.readyS + s.windowS + s.gapAfterS
        case .activity: return s.windowS + 4
        case .manualStart: return s.windowS > 0 ? s.windowS : (s.cueKind == "rewear" ? 45 : 70)
        case .manualEnd: return 0
        }
    }

    static func estimate(_ steps: [Step], _ t: Timing) -> Double { steps.reduce(0) { $0 + duration($1, t) } }

    // ------------------------------------------------------------------ step builders
    static func calibration(module: String, reason: String) -> [Step] {
        var s: [Step] = [
            Step(module: module, block: "calibration", kind: .message,
                 text: "CALIBRATION", sub: "\(reason)Sit upright, look straight ahead, both AirPods in. Keep them in from now on."),
            Step(module: module, block: "calibration", kind: .cue, cueKind: "calibration", motion: "still",
                 condition: "sitting", windowS: 4, gapAfterS: 1, readyS: 0.8, spoken: "stay still",
                 text: "STAY STILL", sub: "4 seconds, looking straight ahead"),
        ]
        for i in 1...3 {
            s.append(Step(module: module, block: "calibration", kind: .cue, cueKind: "calibration", step: i,
                          motion: "calib_nod", condition: "sitting", windowS: 2, gapAfterS: 1, readyS: 0.8,
                          spoken: i == 1 ? "nod" : "", text: "NOD \(i) of 3",
                          sub: "chin DOWN first, straight back up to the front, don't hold it down"))
        }
        s.append(Step(module: module, block: "calibration", kind: .cue, cueKind: "calibration", motion: "look_left_right",
                      condition: "sitting", windowS: 5, gapAfterS: 1, readyS: 0.8, spoken: "look left, right, front",
                      text: "LOOK LEFT, THEN RIGHT, THEN FRONT", sub: "slowly", endsBlock: true))
        return s
    }

    static func practice(plan: StudyPlan, perMotion: Int) -> [Step] {
        guard perMotion > 0 else { return [] }
        var s = [Step(module: "setup", block: "practice", kind: .message, text: "PRACTICE",
                      sub: "Each motion \(perMotion)x. Watch the head on the screen, then do it after the high beep. One smooth go, straight back to the front.")]
        for m in plan.motions {
            for k in 1...perMotion {
                s.append(Step(module: "setup", block: "practice", kind: .cue, cueKind: "practice", round: k,
                              motion: m.id, condition: "sitting", windowS: plan.timing.windowS, gapAfterS: 2.5,
                              readyS: plan.timing.readyS, spoken: m.spoken, text: m.instruction, sub: "practice \(k) of \(perMotion)"))
            }
        }
        s[s.count - 1].endsBlock = true
        return s
    }

    static func block(_ b: BlockDef, module: String, plan: StudyPlan, rng: inout SeededRNG) -> [Step] {
        let t = plan.timing
        let motionIDs = b.motions ?? plan.motions.map(\.id)
        let gap = { (rng: inout SeededRNG) in Double.random(in: t.gapMinS...t.gapMaxS, using: &rng) }
        var s: [Step] = []
        switch b.kind {
        case .rounds:
            s.append(Step(module: module, block: b.id, kind: .message, text: b.title.uppercased(),
                          sub: b.text ?? "\(b.rounds) round(s). Condition: \(b.condition). Do the motion right after the high beep, in one smooth go, straight back to the front (don't hold), then keep still."))
            for r in 1...max(1, b.rounds) {
                var seq = motionIDs + Array(repeating: "idle", count: t.idlePerRound)
                seq.shuffle(using: &rng)
                for m in seq {
                    let def = plan.motion(m)
                    s.append(Step(module: module, block: b.id, kind: .cue, cueKind: "rounds", round: r, motion: m,
                                  condition: b.condition, windowS: t.windowS, gapAfterS: gap(&rng), readyS: t.readyS,
                                  spoken: m == "idle" ? "nothing" : (def?.spoken ?? m),
                                  text: m == "idle" ? "NOTHING: stay natural" : (def?.instruction ?? m),
                                  sub: "[\(b.condition)]  round \(r) of \(b.rounds)"))
                }
                if r % t.breakEveryRounds == 0 && r < b.rounds {
                    s.append(Step(module: module, block: b.id, kind: .message, text: "SHORT BREAK",
                                  sub: "Relax, keep the AirPods in. Continue when ready."))
                }
            }
        case .commands:
            s.append(Step(module: module, block: b.id, kind: .message, text: b.title.uppercased(),
                          sub: "Condition: \(b.condition). " + (b.text ?? "Each command = first motion, then second motion, at your normal pace, after the beep.")))
            var cmds = plan.commands
            cmds.shuffle(using: &rng)
            for (i, c) in cmds.prefix(max(0, b.n)).enumerated() {
                let a = plan.motion(c.first)?.spoken ?? c.first, z = plan.motion(c.then)?.spoken ?? c.then
                s.append(Step(module: module, block: b.id, kind: .cue, cueKind: "commands", round: i + 1,
                              motion: "\(c.first)>\(c.then)", condition: b.condition, windowS: t.commandWindowS,
                              gapAfterS: gap(&rng), readyS: t.readyS, spoken: "\(a), then \(z)",
                              text: "COMMAND: \(c.message)", sub: "\(c.first.uppercased())  then  \(c.then.uppercased())", note: c.message))
            }
        case .pairs:
            s.append(Step(module: module, block: b.id, kind: .message, text: b.title.uppercased(),
                          sub: "Two motions: the first on the first beep, the second on the second beep."))
            var k = 0
            for g in b.gaps {
                for _ in 0..<max(0, b.pairsPerGap) {
                    k += 1
                    var ms = motionIDs
                    ms.shuffle(using: &rng)
                    let (a, z) = (ms[0], ms[1])
                    let sa = plan.motion(a)?.spoken ?? a, sz = plan.motion(z)?.spoken ?? z
                    s.append(Step(module: module, block: b.id, kind: .cue, cueKind: "pairs", round: k, step: 1, motion: a,
                                  condition: "sitting", windowS: 1.0 + g, gapAfterS: 0, readyS: t.readyS,
                                  spoken: "\(sa), then \(sz)", text: "\(a.uppercased())  then  \(z.uppercased())",
                                  sub: "pause between them about \(g) s", note: "gap_s=\(g)"))
                    s.append(Step(module: module, block: b.id, kind: .cue, cueKind: "pairs", round: k, step: 2, motion: z,
                                  condition: "sitting", windowS: t.windowS, gapAfterS: gap(&rng), readyS: 0,
                                  text: "\(a.uppercased())  then  \(z.uppercased())", sub: "second motion now", note: "gap_s=\(g)"))
                }
            }
        case .selfPaced:
            for l in 1...max(1, b.lists) {
                var cmds = plan.commands
                cmds.shuffle(using: &rng)
                let items = Array(cmds.prefix(max(1, b.n)))
                let list = items.enumerated().map { "\($0.offset + 1). \($0.element.message): \($0.element.first.uppercased()) then \($0.element.then.uppercased())" }
                s.append(Step(module: module, block: b.id, kind: .manualStart, cueKind: "self_paced", round: l, step: 0,
                              motion: items.map { "\($0.first)>\($0.then)" }.joined(separator: ";"), condition: b.condition,
                              text: "SEND THESE COMMANDS IN ORDER, at your own pace, a few seconds apart",
                              sub: list.joined(separator: "\n"), note: "start"))
                s.append(Step(module: module, block: b.id, kind: .manualEnd, cueKind: "self_paced", round: l, step: 1,
                              motion: "end", condition: b.condition, note: "end"))
            }
        case .negatives:
            s.append(Step(module: module, block: b.id, kind: .message, text: "NO-GESTURE BLOCK",
                          sub: "Do NOT do any of the gestures. Just do each activity naturally until the double beep."))
            for a in b.activities {
                s.append(Step(module: module, block: b.id, kind: .activity, cueKind: "negatives", motion: "none",
                              condition: a.text, windowS: a.seconds, spoken: a.text.components(separatedBy: ":").first ?? a.text,
                              text: a.text, sub: "\(Int(a.seconds)) s"))
            }
        case .free:
            s.append(Step(module: module, block: b.id, kind: .manualStart, cueKind: "free", step: 0, motion: "free",
                          condition: b.condition, windowS: b.estimateS ?? 0, spoken: b.title.lowercased(),
                          text: b.title.uppercased(), sub: b.text ?? "", note: "start"))
            s.append(Step(module: module, block: b.id, kind: .manualEnd, cueKind: "free", step: 1, motion: "free",
                          condition: b.condition, note: "end"))
        case .message:
            s.append(Step(module: module, block: b.id, kind: .message, text: b.title.uppercased(), sub: b.text ?? ""))
        case .rewear:
            s.append(Step(module: module, block: b.id, kind: .manualStart, cueKind: "rewear", step: 0, motion: "rewear",
                          text: "RE-WEAR", sub: "Take BOTH AirPods out, put them back in as usual. Then press Done.", note: "start"))
            s.append(Step(module: module, block: b.id, kind: .manualEnd, cueKind: "rewear", step: 1, motion: "rewear", note: "end"))
            s += calibration(module: module, reason: "After re-wear. ")
        }
        if !s.isEmpty { s[s.count - 1].endsBlock = true }
        return s
    }

    static func module(_ m: ModuleDef, plan: StudyPlan, rng: inout SeededRNG) -> [Step] {
        var s: [Step] = []
        for b in m.blocks { s += block(b, module: m.id, plan: plan, rng: &rng) }
        if !s.isEmpty { s[s.count - 1].endsModule = true }
        return s
    }

    // ------------------------------------------------------------------ the session
    static func plan(study: StudyPlan, participant: Participant, device: String, budgetMin: Double,
                     seed: UInt64, fillWithExtraRounds: Bool = true) -> SessionPlan {
        var rng = SeededRNG(seed: seed)
        let t = study.timing
        var warnings: [String] = []
        let budget = budgetMin * 60 - 60   // keep 1 min for the closing
        let firstSession = participant.sessions.isEmpty

        var steps = calibration(module: "setup", reason: "")
        steps += practice(plan: study, perMotion: firstSession ? study.practicePerMotionFirst : study.practicePerMotionLater)

        let doneCore = participant.coreBlocksDone(device: device)
        let coreTodo = coreOrder(study.core, groups: study.counterbalance, number: participant.number)
            .filter { !doneCore.contains($0.id) }
        var core: [Step] = []
        for b in coreTodo { core += block(b, module: "core", plan: study, rng: &rng) }
        if !core.isEmpty { core[core.count - 1].endsModule = true }
        steps += core
        if estimate(steps, t) > budget {
            warnings.append(String(format: "The core needs about %.0f min, more than the time given. Data will be marked incomplete if it does not finish.", estimate(steps, t) / 60))
        }

        let done = participant.modulesDone(device: device, perDevice: study.modulesPerDevice)
        let rotating = study.modules.filter(\.rotate).map(\.id)
        let available = rotating.filter { !done.contains($0) }
        let neverLast = Set(study.modules.filter { m in m.blocks.contains { $0.kind == .rewear } }.map(\.id))
        var order = moduleOrder(number: participant.number, rotating: rotating, available: available, neverLast: neverLast)
        for g in study.requireOneOf.reversed() where !g.contains(where: { done.contains($0) }) {
            if let first = order.first(where: { g.contains($0) }) {   // required group not done yet: its module first
                order.removeAll { $0 == first }
                order.insert(first, at: 0)
            }
        }
        var chosen: [String] = []
        for id in order {
            guard let m = study.modules.first(where: { $0.id == id }) else { continue }
            var probe = rng
            let ms = module(m, plan: study, rng: &probe)
            if estimate(steps + ms, t) <= budget {
                steps += ms
                rng = probe
                chosen.append(id)
            }
        }

        var filler = 0
        if fillWithExtraRounds, let fid = study.fillModule, let g = study.modules.first(where: { $0.id == fid }),
           let gb = g.blocks.first, gb.kind == .rounds {
            while true {
                var b = gb
                b.rounds = filler + 1
                var probe = rng
                let gs = block(b, module: fid, plan: study, rng: &probe)
                if estimate(steps + gs, t) > budget || filler >= 8 { break }
                filler += 1
            }
            if filler > 0 {
                var b = gb
                b.rounds = filler
                var gs = block(b, module: fid, plan: study, rng: &rng)
                gs[gs.count - 1].endsModule = true
                steps += gs
            }
        }
        steps.append(Step(module: "closing", block: "closing", kind: .cue, cueKind: "calibration", motion: "still",
                          condition: "sitting", windowS: 10, gapAfterS: 0, readyS: 0.8, spoken: "stay still",
                          text: "LAST: STAY STILL", sub: "10 seconds", endsBlock: true))
        for i in steps.indices { steps[i].uid = i + 1 }
        return SessionPlan(steps: steps, coreBlocks: coreTodo.map(\.id), modules: chosen, fillerRounds: filler,
                           estimateS: estimate(steps, t), warnings: warnings)
    }
}
