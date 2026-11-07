// Parity check: the Swift live recogniser must give the same head frame, features, model probabilities and
// decisions as Python (gesturekit) on real P01 events. Run by the GitHub build:
//   swiftc Sources/LiveRecognizer.swift Tests/main.swift -o parity && ./parity Tests/parity.json
// parity.json is written by algorithm/scripts/export_live_model.py.

import Foundation

struct Case: Decodable {
    var fs: Double
    var pre: Int
    var heading: Double
    var rot: [[Double]]
    var grav: [[Double]]
    var valid: [Int]
    var features: [String: Double]
    var proba: [Double]
    var rule_kind: String
    var rule_motion: String
    var model_kind: String
}

struct ModelHolder: Decodable { var cases: [Case] }

let path = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "Tests/parity.json"
let data = try Data(contentsOf: URL(fileURLWithPath: path))
let raw = try JSONSerialization.jsonObject(with: data) as! [String: Any]
let model = try LiveModel.decode(try JSONSerialization.data(withJSONObject: raw["model"]!))
let cases = try JSONDecoder().decode(ModelHolder.self, from: data).cases

func v3(_ a: [Double]) -> V3 { V3(a[0], a[1], a[2]) }
var failures = 0, worstFeature = 0.0, worstProb = 0.0
for (n, c) in cases.enumerated() {
    let preIdx = (0..<c.pre).filter { c.valid[$0] == 1 }
    let g = HeadFrame.gravityDown((preIdx.isEmpty ? Array(0..<max(c.pre, 1)) : preIdx).map { v3(c.grav[$0]) })
    let m = HeadFrame.matrix(heading: c.heading, gDown: g)
    let rot = c.rot[c.pre...].map { m.apply(v3($0)) }
    let f = LiveFeatures.compute(rot: rot, fs: c.fs)
    for (k, want) in c.features {
        let got = f[k] ?? .nan
        let err = abs(got - want) / max(1e-3, abs(want))
        worstFeature = max(worstFeature, err)
        if !(err < 1e-4) { failures += 1; print("case \(n) \(k): swift \(got) python \(want)") }
    }
    let d = decide(f, model: model)
    for (a, b) in zip(d.proba, c.proba) {
        worstProb = max(worstProb, abs(a - b))
        if !(abs(a - b) < 1e-4) { failures += 1; print("case \(n) proba: swift \(d.proba) python \(c.proba)"); break }
    }
    if d.rules.kind != c.rule_kind || d.rules.motion != c.rule_motion {
        failures += 1; print("case \(n) rules: swift \(d.rules.kind)/\(d.rules.motion) python \(c.rule_kind)/\(c.rule_motion)")
    }
    if d.model.kind != c.model_kind { failures += 1; print("case \(n) model kind: swift \(d.model.kind) python \(c.model_kind)") }
}

// pair decoder: same rules as gesturekit/decode.py
var dec = PairDecoder(commands: ["tilt_left>nod_down": "GO FORWARD"], timeoutS: 1.5)
let checks: [(String, Double, Double, String?)] = [
    ("tilt_left", 0, 1, nil), ("nod_down", 2, 3, "GO FORWARD"),         // second starts 1.0 s after first ends
    ("tilt_left", 10, 11, nil), ("nod_down", 13, 14, nil),             // 2.0 s later: too late, nod is new first
    ("nod_down", 14.5, 15, nil), ("tilt_left", 20, 21, nil), ("tilt_left", 21.5, 22, nil),  // same twice: no
]
for (i, ck) in checks.enumerated() {
    let got = dec.push(ck.0, tStart: ck.1, tEnd: ck.2)?.message
    if got != ck.3 { failures += 1; print("pair step \(i): got \(got ?? "nil") want \(ck.3 ?? "nil")") }
}

// calibration heading: synthetic nods about a known horizontal axis must give that heading back (sign: chin down first)
let trueHeading = 0.7
let axis = V3(cos(trueHeading), sin(trueHeading), 0)
let nod = (0..<40).map { i -> V3 in axis * sin(Double(i) / 39 * 2 * Double.pi) * 2 }  // positive swing first
let h = HeadFrame.calibrateHeading(nods: [(V3(0, 0, -1), nod), (V3(0, 0, -1), nod), (V3(0, 0, -1), nod)]) ?? .nan
if !(abs(h - trueHeading) < 1e-6) { failures += 1; print("calibration heading \(h), want \(trueHeading)") }

print(String(format: "%d cases, worst feature error %.2e (relative), worst probability error %.2e, failures %d",
             cases.count, worstFeature, worstProb, failures))
exit(failures == 0 ? 0 : 1)
