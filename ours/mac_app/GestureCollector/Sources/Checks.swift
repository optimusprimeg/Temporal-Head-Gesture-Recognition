// v3.1 trial checks: did the person do the motion that was asked? Three independent opinions, majority vote.
//   rule   our live rules (axis share / loop + first-swing sign) on the head-frame event. Head singles only.
//   model  live_model.json's answer, when it knows that motion.
//   dtw    nearest of this person's own templates (practice trials that passed), dynamic time warping on the
//          head-frame rotation, each template scaled to unit RMS so size and speed matter less than shape.
// A check that has no opinion (motion unknown to it, no templates yet) does not vote. The trial is "mismatch" when
// at least 2 checks voted and the majority disagree with the cue. A mismatch or a wrong motion count gives one retake
// (Timing.retakeOnce). Nothing is ever deleted: the first attempt stays in cues.csv with its flags.
// Foundation only.

import Foundation

enum DTW {
    /// Mean per-step distance along the best warping path (Sakoe-Chiba band of 1/3 of the longer length).
    static func distance(_ a: [V3], _ b: [V3]) -> Double {
        let n = a.count, m = b.count
        guard n > 1, m > 1 else { return .infinity }
        let band = max(abs(n - m), max(n, m) / 3)
        var prev = [Double](repeating: .infinity, count: m + 1)
        var cur = prev
        prev[0] = 0
        for i in 1...n {
            cur = [Double](repeating: .infinity, count: m + 1)
            let lo = max(1, i - band), hi = min(m, i + band)
            if lo <= hi {
                for j in lo...hi {
                    let d = a[i - 1] - b[j - 1]
                    let c = (d * d).sum().squareRoot()
                    cur[j] = c + min(prev[j], cur[j - 1], prev[j - 1])
                }
            }
            prev = cur
        }
        return prev[m] / Double(n + m)
    }

    /// Every 2nd sample (50 -> 25 Hz) and unit RMS: shape, not size.
    static func prepare(_ x: [V3]) -> [V3] {
        let s = stride(from: 0, to: x.count, by: 2).map { x[$0] }
        let rms = (s.map { ($0 * $0).sum() }.reduce(0, +) / Double(max(1, s.count))).squareRoot()
        return rms > 1e-6 ? s.map { $0 / rms } : s
    }
}

struct TemplateStore {
    private(set) var byMotion: [String: [[V3]]] = [:]
    let maxPerMotion = 5

    mutating func add(_ motion: String, _ headRot: [V3]) {
        guard headRot.count >= 8 else { return }
        var list = byMotion[motion] ?? []
        list.append(DTW.prepare(headRot))
        if list.count > maxPerMotion { list.removeFirst(list.count - maxPerMotion) }
        byMotion[motion] = list
    }

    /// Nearest motion, or nil when fewer than 2 motions have templates (nothing to compare against).
    func nearest(_ headRot: [V3]) -> (motion: String, distance: Double)? {
        guard byMotion.count >= 2, headRot.count >= 8 else { return nil }
        let x = DTW.prepare(headRot)
        var best: (String, Double)? = nil
        for (m, list) in byMotion {
            for t in list {
                let d = DTW.distance(x, t)
                if best == nil || d < best!.1 { best = (m, d) }
            }
        }
        return best.map { (motion: $0.0, distance: $0.1) }
    }
}

struct TrialCheck {
    var rule = ""          // the rules' motion name ("" = no opinion)
    var model = ""         // the model's motion name ("" = no opinion)
    var dtw = ""           // nearest template's motion ("" = no opinion)
    var peakRot = 0.0
    var flags: [String] = []

    /// "ok", "mismatch", "unsure" (only one check could vote and it disagreed) or "" (no check could vote).
    /// v3.7: only the rules and the model vote. The DTW match is still logged (check_dtw) but no longer votes: its
    /// templates come from practice, which only the first session has, so sessions were not checked the same way.
    func vote(expected: String) -> String {
        let votes = [rule, model].filter { !$0.isEmpty }
        guard !votes.isEmpty else { return "" }
        let disagree = votes.filter { $0 != expected }.count
        // two voters: both disagree = mismatch (retake), one disagrees = unsure (flag only)
        if votes.count == 2 { return disagree == 2 ? "mismatch" : (disagree == 1 ? "unsure" : "ok") }
        return disagree == 0 ? "ok" : "unsure"
    }
}

/// Motions our rules and the logistic model can name (the 8 single head motions).
let RULE_MOTIONS: Set<String> = ["nod_down", "look_up", "tilt_left", "tilt_right", "turn_left", "turn_right",
                                 "circle_cw", "circle_ccw"]
