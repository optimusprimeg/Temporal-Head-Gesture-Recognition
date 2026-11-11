// Parity check for the Forest live mode: the Swift receiver-96 features and forest must match Python.
//   swiftc Sources/ForestModel.swift Tests/forest/main.swift -o forest_parity && ./forest_parity forest_model.json Tests/forest_parity.json
// Both JSON files are written by algorithm/scripts/export_forest_model.py.

import Foundation

struct FCase: Decodable { var rows: [[Double]]; var features: [Double]; var proba: [Double] }
struct FHolder: Decodable { var cases: [FCase] }

let args = CommandLine.arguments
let modelPath = args.count > 1 ? args[1] : "forest_model.json"
let casePath = args.count > 2 ? args[2] : "Tests/forest_parity.json"
let fm = try ForestModel.decode(try Data(contentsOf: URL(fileURLWithPath: modelPath)))
let fcases = try JSONDecoder().decode(FHolder.self, from: try Data(contentsOf: URL(fileURLWithPath: casePath))).cases

var bad = 0, worstF = 0.0, worstP = 0.0, worstAt = ""
for (i, c) in fcases.enumerated() {
    let f = Receiver96.features(c.rows, crop: fm.crop)
    for (k, (a, b)) in zip(f, c.features).enumerated() {
        let e = abs(a - b) / (1e-9 + 1e-6 * abs(b) + 1e-12)        // in units of (1e-9 absolute + 1 ppm relative)
        if e > worstF { worstF = e; worstAt = "case \(i) feature \(k): Swift \(a) Python \(b)" }
    }
    let p = fm.probabilities(c.features)          // forest alone, on Python's features
    for (a, b) in zip(p, c.proba) { worstP = max(worstP, abs(a - b)) }
    let topS = p.indices.max { p[$0] < p[$1] }!, topP = c.proba.indices.max { c.proba[$0] < c.proba[$1] }!
    if topS != topP { bad += 1; print("case \(i): Swift says \(fm.classes[topS]), Python \(fm.classes[topP])") }
}
print(String(format: "%d cases, worst feature error %.1f tolerance units, worst probability error %.2e, top-class mismatches %d",
             fcases.count, worstF, worstP, bad))
print("worst feature: \(worstAt)")
exit(bad == 0 && worstP < 0.02 && worstF < 1000 ? 0 : 1)
