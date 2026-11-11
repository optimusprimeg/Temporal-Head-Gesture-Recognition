// v3.1 "Forest" live mode: the teammates' / receiver's way, so both approaches run side by side in one app.
//   detector  port of secret_receiver_20_event.py: start when |rotation| >= start for `onset` samples (with a
//             `pre`-sample pre-buffer), keep while >= keep, end after `endSamples` quiet samples or at maxSamples,
//             drop events shorter than minSamples, then a cooldown. All numbers come from forest_model.json.
//   features  the receiver's 96: 12 channels (yaw pitch roll, rotation, user acceleration, gravity) x 8 statistics
//             on the centred 100-sample crop (benchmark_all.receiver_96)
//   model     a random forest exported from scikit-learn (algorithm/scripts/export_forest_model.py), trained on
//             windows cut by THIS detector from stitched recordings (training on whole takes made live miss ~85 %)
//   gate      top class not idle/none and probability >= minConfidence
// The forest's classes are whole gestures (e.g. tilt_2x_left), so in this mode a class IS the command.
// forest_model.json is read from the data folder (replace it without a rebuild). Foundation only.

import Foundation

struct ForestModel: Codable {
    struct Tree: Codable {
        var left: [Int]
        var right: [Int]
        var feature: [Int]
        var threshold: [Double]
        var value: [[Double]]        // per node: class fractions
    }
    struct DetectorParams: Codable {
        var start: Double = 0.60
        var keep: Double = 0.20
        var endSamples: Int = 25
        var onset: Int = 3
        var pre: Int = 15
        var minSamples: Int = 40
        var maxSamples: Int = 150
        var cooldownS: Double = 1.5
    }

    var version: String
    var featureSet: String           // "receiver96"
    var classes: [String]
    var trees: [Tree]
    var detector: DetectorParams
    var minConfidence: Double
    var crop: Int                    // 100

    static func decode(_ data: Data) throws -> ForestModel {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(ForestModel.self, from: data)
    }

    static func load(dataRoot: URL) -> (ForestModel?, String) {
        let user = dataRoot.appendingPathComponent("forest_model.json")
        let (url, whereFrom): (URL?, String) = FileManager.default.fileExists(atPath: user.path)
            ? (user, "data folder") : (Bundle.main.url(forResource: "forest_model", withExtension: "json"), "built in")
        guard let u = url, let d = try? Data(contentsOf: u) else {
            return (nil, "Forest: no forest_model.json (data folder or built in)")
        }
        do {
            let m = try decode(d)
            return (m, "Forest: \(whereFrom) (\(m.version), \(m.trees.count) trees, \(m.classes.count) classes)")
        } catch {
            return (nil, "Forest: forest_model.json (\(whereFrom)) is broken: \(error.localizedDescription)")
        }
    }

    /// Mean of the trees' class fractions (scikit-learn predict_proba). Features are compared as Float32, as
    /// scikit-learn does.
    func probabilities(_ x: [Double]) -> [Double] {
        var p = [Double](repeating: 0, count: classes.count)
        for t in trees {
            var n = 0
            while t.left[n] >= 0 {
                let f = Double(Float(x[t.feature[n]]))
                n = f <= t.threshold[n] ? t.left[n] : t.right[n]
            }
            let v = t.value[n]
            let s = v.reduce(0, +)
            for k in 0..<min(v.count, p.count) { p[k] += s > 0 ? v[k] / s : 0 }
        }
        return p.map { $0 / Double(max(1, trees.count)) }
    }
}

enum Receiver96 {
    /// rows: samples x 12 channels in the order yaw pitch roll rotX rotY rotZ accX accY accZ gravX gravY gravZ.
    static func features(_ rows: [[Double]], crop: Int = 100) -> [Double] {
        var x = rows
        if x.count > crop {
            let s = (x.count - crop) / 2
            x = Array(x[s..<(s + crop)])
        }
        let n = x.count
        guard n >= 2 else { return [Double](repeating: 0, count: 96) }
        var out: [Double] = []
        for j in 0..<12 {
            let v = x.map { $0[j] }
            let mean = v.reduce(0, +) / Double(n)
            let std = (v.map { ($0 - mean) * ($0 - mean) }.reduce(0, +) / Double(n)).squareRoot()
            let mn = v.min()!, mx = v.max()!
            let jerk = zip(v.dropFirst(), v).map { $0 - $1 }
            let jm = jerk.reduce(0, +) / Double(jerk.count)
            let jstd = (jerk.map { ($0 - jm) * ($0 - jm) }.reduce(0, +) / Double(jerk.count)).squareRoot()
            let jmax = jerk.map(abs).max() ?? 0
            var power = 0.0                                  // sum |FFT(v)[k]|^2 for k < n/2, divided by n
            for k in 0..<(n / 2) {
                var re = 0.0, im = 0.0
                let w = -2 * Double.pi * Double(k) / Double(n)
                for (t, val) in v.enumerated() { re += val * cos(w * Double(t)); im += val * sin(w * Double(t)) }
                power += re * re + im * im
            }
            out += [mean, std, mn, mx, mx - mn, jstd, jmax, power / Double(n)]
        }
        return out.map { $0.isFinite ? $0 : 0 }
    }
}

struct ForestResult {
    var startNs: Int64
    var endNs: Int64
    var label: String
    var confidence: Double
    var accepted: Bool
    var proba: [Double]
}

/// Fed with every sample on the motion queue (Recorder). Does nothing while no model is set.
final class ForestEngine {
    var onResult: ((ForestResult) -> Void)?          // motion queue
    private let lock = NSLock()
    private var model: ForestModel?
    private var pre: [(Int64, [Double])] = []
    private var event: [(Int64, [Double])] = []
    private var recording = false
    private var onset = 0, quiet = 0
    private var cooldownUntil: Int64 = 0

    func setModel(_ m: ForestModel?) {
        lock.lock(); model = m; pre = []; event = []; recording = false; onset = 0; quiet = 0; lock.unlock()
    }

    /// row = yaw pitch roll rotX rotY rotZ accX accY accZ gravX gravY gravZ
    func push(ns: Int64, row: [Double]) {
        lock.lock()
        guard let m = model else { lock.unlock(); return }
        let p = m.detector
        let speed = (row[3] * row[3] + row[4] * row[4] + row[5] * row[5]).squareRoot()
        var finished: [(Int64, [Double])]? = nil
        if ns < cooldownUntil {
            pre.append((ns, row)); if pre.count > p.pre { pre.removeFirst() }
        } else if !recording {
            pre.append((ns, row)); if pre.count > p.pre { pre.removeFirst() }
            onset = speed >= p.start ? onset + 1 : 0
            if onset >= p.onset {
                recording = true
                event = pre
                quiet = 0
                onset = 0
            }
        } else {
            event.append((ns, row))
            quiet = speed < p.keep ? quiet + 1 : 0
            if quiet >= p.endSamples || event.count >= p.maxSamples {
                if event.count >= p.minSamples { finished = event }
                recording = false
                event = []
                pre = []
                cooldownUntil = ns + Int64(p.cooldownS * 1e9)
            }
        }
        lock.unlock()
        guard let ev = finished else { return }
        let x = Receiver96.features(ev.map(\.1), crop: m.crop)
        let pr = m.probabilities(x)
        let top = pr.indices.max { pr[$0] < pr[$1] } ?? 0
        let label = top < m.classes.count ? m.classes[top] : "?"
        let ok = label != "idle" && label != "none" && pr[top] >= m.minConfidence
        onResult?(ForestResult(startNs: ev.first!.0, endNs: ev.last!.0, label: label, confidence: pr[top],
                               accepted: ok, proba: pr))
    }
}
