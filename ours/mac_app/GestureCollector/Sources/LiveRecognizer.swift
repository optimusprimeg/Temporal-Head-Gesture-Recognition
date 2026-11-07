// Live command recogniser: the logic, Foundation only (Tests/main.swift compiles this file alone and checks it
// against Python on real P01 events: Tests/parity.json, made by algorithm/scripts/export_live_model.py).
//
//   head frame   port of gesturekit/frames.py   (gravity just before the event + heading from 3 calibration nods)
//   features     port of gesturekit/features.py (axis shares, linearity, first swing per axis, loop per plane)
//   kind         Rules: dominant axis share >= axis_share -> nod/tilt/turn, else |loop| >= loop_min -> circle, else none
//                Model: logistic regression from live_model.json (standardise, softmax)
//   direction    one sign per kind (nod: first_lobe_x > 0 -> nod_down, ...), from live_model.json
//   gate         Rules: kind != none. Model: also top probability >= min_confidence and margin >= min_margin
//   pairs        port of gesturekit/decode.py PairDecoder (second motion must START within 1.5 s of the first's END)

import Foundation

typealias V3 = SIMD3<Double>

// ---------------------------------------------------------------------------------------------- 3x3 matrices
struct M3 {
    var r0: V3, r1: V3, r2: V3

    static let identity = M3(r0: V3(1, 0, 0), r1: V3(0, 1, 0), r2: V3(0, 0, 1))

    func apply(_ v: V3) -> V3 { V3((r0 * v).sum(), (r1 * v).sum(), (r2 * v).sum()) }

    static func * (a: M3, b: M3) -> M3 {
        let c0 = V3(b.r0.x, b.r1.x, b.r2.x), c1 = V3(b.r0.y, b.r1.y, b.r2.y), c2 = V3(b.r0.z, b.r1.z, b.r2.z)
        func row(_ r: V3) -> V3 { V3((r * c0).sum(), (r * c1).sum(), (r * c2).sum()) }
        return M3(r0: row(a.r0), r1: row(a.r1), r2: row(a.r2))
    }

    static func + (a: M3, b: M3) -> M3 { M3(r0: a.r0 + b.r0, r1: a.r1 + b.r1, r2: a.r2 + b.r2) }
    static func * (a: M3, s: Double) -> M3 { M3(r0: a.r0 * s, r1: a.r1 * s, r2: a.r2 * s) }
}

private func norm(_ v: V3) -> Double { (v * v).sum().squareRoot() }
private func cross(_ a: V3, _ b: V3) -> V3 {
    V3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)
}
private func sgn(_ x: Double) -> Double { x > 0 ? 1 : (x < 0 ? -1 : 0) }

// ---------------------------------------------------------------------------------------------- head frame
enum HeadFrame {
    /// Rotation taking direction v onto direction target (frames.rotation_to).
    static func rotationTo(_ v0: V3, _ t0: V3) -> M3 {
        let v = v0 / (norm(v0) + 1e-12), t = t0 / norm(t0)
        let axis = cross(v, t), c = (v * t).sum()
        if norm(axis) < 1e-8 {
            if c > 0 { return .identity }
            var perp = abs(v.x) < 0.9 ? cross(v, V3(1, 0, 0)) : cross(v, V3(0, 1, 0))
            perp /= norm(perp)
            let o = M3(r0: perp * perp.x, r1: perp * perp.y, r2: perp * perp.z)
            return o * 2 + M3.identity * -1
        }
        let k = M3(r0: V3(0, -axis.z, axis.y), r1: V3(axis.z, 0, -axis.x), r2: V3(-axis.y, axis.x, 0))
        return M3.identity + k + (k * k) * (1 / (1 + c))
    }

    /// Rotation taking 'up' (= -gravity) onto +Z. gDown: gravity direction, pointing down, earbud axes.
    static func upAlignment(_ gDown: V3) -> M3 { rotationTo(-gDown, V3(0, 0, 1)) }

    static func rotZ(_ a: Double) -> M3 {
        M3(r0: V3(cos(a), -sin(a), 0), r1: V3(sin(a), cos(a), 0), r2: V3(0, 0, 1))
    }

    /// Earbud -> head axes (x nod axis, y = z cross x, z up). heading nil: gravity alignment only.
    static func matrix(heading: Double?, gDown: V3) -> M3 {
        let up = upAlignment(gDown)
        guard let h = heading else { return up }
        return rotZ(-h) * up
    }

    /// Mean gravity direction of the samples before the event (frames.gravity_before).
    static func gravityDown(_ grav: [V3]) -> V3 {
        guard !grav.isEmpty else { return V3(0, 0, -1) }
        let g = grav.reduce(V3(0, 0, 0), +) / Double(grav.count)
        return g / (norm(g) + 1e-12)
    }

    /// Heading of the nod axis from calibration nods (frames.calibrate): each nod = (gravity before, gyro samples).
    /// Chin down first: the first swing about +X is positive.
    static func calibrateHeading(nods: [(gDown: V3, gyro: [V3])], firstSwingFrac: Double = 0.3) -> Double? {
        var xy: [[(Double, Double)]] = []
        for n in nods {
            let r = upAlignment(n.gDown)
            xy.append(n.gyro.map { v -> (Double, Double) in let w = r.apply(v); return (w.x, w.y) })
        }
        let all = xy.flatMap { $0 }
        guard all.count >= 3 else { return nil }
        let mx = all.map(\.0).reduce(0, +) / Double(all.count), my = all.map(\.1).reduce(0, +) / Double(all.count)
        var sxx = 0.0, syy = 0.0, sxy = 0.0
        for (x, y) in all { sxx += (x - mx) * (x - mx); syy += (y - my) * (y - my); sxy += (x - mx) * (y - my) }
        let theta = 0.5 * atan2(2 * sxy, sxx - syy)      // principal axis of the horizontal rotation
        var axis = (cos(theta), sin(theta))
        var votes = 0.0
        for g in xy {
            let v = g.map { $0.0 * axis.0 + $0.1 * axis.1 }
            let peak = v.map(abs).max() ?? 0
            if let i = v.firstIndex(where: { abs($0) > firstSwingFrac * peak }) { votes += sgn(v[i]) }
        }
        if votes < 0 { axis = (-axis.0, -axis.1) }
        return atan2(axis.1, axis.0)
    }
}

// ---------------------------------------------------------------------------------------------- features
enum LiveFeatures {
    /// Head-frame rotation rate of one event -> named features (gesturekit axis + signed sets, plus |loop|).
    static func compute(rot: [V3], fs: Double) -> [String: Double] {
        var f: [String: Double] = [:]
        let e = rot.reduce(V3(0, 0, 0)) { $0 + $1 * $1 }
        let total = e.sum() + 1e-12
        f["share_x"] = e.x / total; f["share_y"] = e.y / total; f["share_z"] = e.z / total
        f["linearity"] = linearity(rot)
        let x = rot.map(\.x), y = rot.map(\.y), z = rot.map(\.z)
        f["first_lobe_x"] = firstLobe(x) / fs
        f["first_lobe_y"] = firstLobe(y) / fs
        f["first_lobe_z"] = firstLobe(z) / fs
        f["loop_xy"] = loop(x, y); f["loop_xz"] = loop(x, z); f["loop_yz"] = loop(y, z)
        for p in ["xy", "xz", "yz"] { f["abs_loop_\(p)"] = abs(f["loop_\(p)"]!) }
        f["duration_s"] = Double(rot.count) / fs
        f["peak_rot"] = rot.map { norm($0) }.max() ?? 0
        return f
    }

    /// Largest eigenvalue / sum of eigenvalues of the 3x3 covariance (1 = rotation about one fixed axis).
    static func linearity(_ rot: [V3]) -> Double {
        let n = Double(rot.count)
        guard rot.count > 2 else { return 1 / (1 + 1e-12) }
        let m = rot.reduce(V3(0, 0, 0), +) / n
        var a00 = 0.0, a11 = 0.0, a22 = 0.0, a01 = 0.0, a02 = 0.0, a12 = 0.0
        for r in rot {
            let d = r - m
            a00 += d.x * d.x; a11 += d.y * d.y; a22 += d.z * d.z
            a01 += d.x * d.y; a02 += d.x * d.z; a12 += d.y * d.z
        }
        let s = 1 / (n - 1)
        a00 *= s; a11 *= s; a22 *= s; a01 *= s; a02 *= s; a12 *= s
        let tr = a00 + a11 + a22
        let p1 = a01 * a01 + a02 * a02 + a12 * a12
        var top: Double
        if p1 < 1e-30 {
            top = max(a00, a11, a22)
        } else {                                            // symmetric 3x3 eigenvalues, closed form
            let q = tr / 3
            let p2 = (a00 - q) * (a00 - q) + (a11 - q) * (a11 - q) + (a22 - q) * (a22 - q) + 2 * p1
            let p = (p2 / 6).squareRoot()
            let b00 = (a00 - q) / p, b11 = (a11 - q) / p, b22 = (a22 - q) / p
            let b01 = a01 / p, b02 = a02 / p, b12 = a12 / p
            let det = b00 * (b11 * b22 - b12 * b12) - b01 * (b01 * b22 - b12 * b02) + b02 * (b01 * b12 - b11 * b02)
            let r = min(1, max(-1, det / 2))
            top = q + 2 * p * cos(acos(r) / 3)
        }
        return top / (tr + 1e-12)
    }

    /// Signed area of the first swing (features._first_lobe): the run of same-sign samples around the first sample
    /// above frac of the peak.
    static func firstLobe(_ v: [Double], frac: Double = 0.3) -> Double {
        let peak = v.map(abs).max() ?? 0
        guard let i = v.firstIndex(where: { abs($0) > frac * peak }) else { return 0 }
        let s = sgn(v[i])
        var a = i
        while a > 0 && sgn(v[a - 1]) == s { a -= 1 }
        var b = i
        while b < v.count && sgn(v[b]) == s { b += 1 }
        return v[a..<b].reduce(0, +)
    }

    /// Signed area of the closed path (u, w) as a share of the circle at its peak radius (features._loop): +1 for
    /// one full counter-clockwise circle, ~0 for a one-axis motion; independent of event length and sample rate.
    static func loop(_ u: [Double], _ w: [Double]) -> Double {
        guard !u.isEmpty else { return 0 }
        var area = 0.0, peak = 0.0
        for i in 0..<u.count {
            let j = (i + 1) % u.count
            area += u[i] * w[j] - u[j] * w[i]
            peak = max(peak, u[i] * u[i] + w[i] * w[i])
        }
        return 0.5 * area / (Double.pi * peak + 1e-9)
    }
}

// ---------------------------------------------------------------------------------------------- model + rules
struct LiveModel: Codable {
    struct Rules: Codable { var axisShare: Double; var loopMin: Double }
    struct Gate: Codable { var minConfidence: Double; var minMargin: Double }
    struct Direction: Codable { var feature: String; var positive: String; var negative: String }

    var version: String
    var features: [String]
    var classes: [String]
    var mean: [Double]
    var scale: [Double]
    var coef: [[Double]]
    var intercept: [Double]
    var rules: Rules
    var gate: Gate
    var direction: [String: Direction]
    var pairTimeoutS: Double

    static func decode(_ data: Data) throws -> LiveModel {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(LiveModel.self, from: data)
    }

    /// Class probabilities (multinomial logistic regression, as sklearn).
    func probabilities(_ f: [String: Double]) -> [Double] {
        let z = features.enumerated().map { (i, name) in ((f[name] ?? 0) - mean[i]) / scale[i] }
        let logits = coef.enumerated().map { (k, w) in zip(w, z).map(*).reduce(0, +) + intercept[k] }
        let m = logits.max() ?? 0
        let ex = logits.map { exp($0 - m) }
        let s = ex.reduce(0, +)
        return ex.map { $0 / s }
    }

    func ruleKind(_ f: [String: Double]) -> String {
        let shares = [f["share_x"] ?? 0, f["share_y"] ?? 0, f["share_z"] ?? 0]
        let i = shares.firstIndex(of: shares.max()!)!     // first maximum, as numpy argmax
        if shares[i] >= rules.axisShare { return ["nod", "tilt", "turn"][i] }
        let loops = [f["abs_loop_xy"] ?? 0, f["abs_loop_xz"] ?? 0, f["abs_loop_yz"] ?? 0]
        return loops.max()! >= rules.loopMin ? "circle" : "none"
    }

    func motion(kind: String, _ f: [String: Double]) -> String {
        guard kind != "none", let d = direction[kind] else { return "none" }
        return (f[d.feature] ?? 0) > 0 ? d.positive : d.negative
    }
}

enum RecognizerMode: String, CaseIterable, Codable { case rules = "Rules", model = "Model" }

struct Decision {
    var kind: String
    var motion: String
    var accepted: Bool
    var confidence: Double      // model: top probability; rules: 1
    var margin: Double
}

/// Both modes are always computed (and logged); `mode` only chooses which one drives the commands.
func decide(_ f: [String: Double], model: LiveModel) -> (rules: Decision, model: Decision, proba: [Double]) {
    let rk = model.ruleKind(f)
    let rules = Decision(kind: rk, motion: model.motion(kind: rk, f), accepted: rk != "none", confidence: 1, margin: 1)
    let p = model.probabilities(f)
    let order = p.indices.sorted { p[$0] > p[$1] }
    let top = order[0]
    let mk = model.classes[top]
    let margin = p[top] - (order.count > 1 ? p[order[1]] : 0)
    let ok = mk != "none" && p[top] >= model.gate.minConfidence && margin >= model.gate.minMargin
    let md = Decision(kind: mk, motion: model.motion(kind: mk, f), accepted: ok, confidence: p[top], margin: margin)
    return (rules, md, p)
}

// ---------------------------------------------------------------------------------------------- pair decoder
struct LiveCommand {
    var first: String
    var second: String
    var message: String
    var tStart: Double
    var tEnd: Double
}

struct PairDecoder {
    var commands: [String: String]          // "first>second" -> message
    var timeoutS: Double = 1.5
    var allowSameTwice = false
    private(set) var pending: (motion: String, tStart: Double, tEnd: Double)?

    init(commands: [String: String], timeoutS: Double = 1.5) {
        self.commands = commands
        self.timeoutS = timeoutS
    }

    mutating func reset() { pending = nil }

    /// Drops a pending first motion whose time ran out. Returns true if one was dropped.
    @discardableResult
    mutating func tick(_ now: Double) -> Bool {
        if let p = pending, now - p.tEnd > timeoutS { pending = nil; return true }
        return false
    }

    /// One accepted motion (in time order) -> a command, or nil.
    mutating func push(_ motion: String, tStart: Double, tEnd: Double) -> LiveCommand? {
        tick(tStart)
        guard let first = pending else { pending = (motion, tStart, tEnd); return nil }
        pending = nil
        let same = first.motion == motion && !allowSameTwice
        guard !same, let msg = commands["\(first.motion)>\(motion)"] else {
            pending = (motion, tStart, tEnd)        // may be the start of a new command
            return nil
        }
        return LiveCommand(first: first.motion, second: motion, message: msg, tStart: first.tStart, tEnd: tEnd)
    }
}

/// Sample rate the way gesturekit snaps it (100, 50 or 25 Hz) from the event's own timestamps.
func snappedRate(samples: Int, seconds: Double) -> Double {
    guard samples > 1, seconds > 0 else { return 50 }
    let r = Double(samples - 1) / seconds
    return [100.0, 50.0, 25.0].min { abs($0 - r) < abs($1 - r) }!
}
