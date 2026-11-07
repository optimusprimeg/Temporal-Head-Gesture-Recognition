// Live motion detector: a Swift port of gesturekit/detect.py (same parameters, quiet_scale 3), fed sample by
// sample from the motion queue. After each cue the runner asks how many motions happened in the cue window and
// shows feedback ("one motion ✓", "do it ONCE", "no motion seen"). v2.1: feedback + logging only, no retakes.
//
// Score per sample = mean|rot| / quietRot + mean|Δacc| / quietJerk over 0.1 s. Start when the score stays above
// kOn x quietScore for 0.06 s, end after 0.4 s below kOff x quietScore; events of 0.3-4 s (longer ones are cut).
// Quiet levels come from the calibration still pose (median), x3 as in DetectorConfig.quiet_scale.

import Foundation

struct LiveEvent {
    var startNs: Int64
    var endNs: Int64
    var energy: Double      // sum of |rot|^2 over the event (to tell a real motion from a twitch)
    var durationS: Double { Double(endNs - startNs) / 1e9 }
}

struct LiveVerdict {
    var count: Int          // motions in the window (twitches below 25 % of the largest one not counted)
    var ok: Bool
    var text: String
}

final class LiveDetector {
    // parameters (DetectorConfig defaults at 50 Hz)
    private let nSmooth = 5, nOnset = 3, nEnd = 20, nPre = 10, nMin = 15, nMax = 200
    private let kOn = 4.0, kOff = 2.0, quietScale = 3.0

    private let lock = NSLock()
    private var qRot = 0.013 * 3, qJerk = 0.0175 * 3, qScore = 2.0   // until calibrated: values of P01's still pose
    private var gBuf: [Double] = [], jBuf: [Double] = []
    private var prev: (Double, Double, Double)?
    private var lastNs: Int64?
    private var recording = false
    private var onset = 0, quietRun = 0
    private var startNs: Int64 = 0, lastActiveNs: Int64 = 0, samplesInEvent = 0
    private var energy = 0.0
    private var history: [Int64] = []        // sample times of the last nPre + nOnset samples (event pre-roll)
    private var events: [LiveEvent] = []
    private var closedQueue: [LiveEvent] = []  // events closed since the last takeClosed() (live recogniser)
    private var capture: [(Double, Double)]?
    private(set) var calibrated = false

    // ------------------------------------------------------------------ calibration (still pose)
    func beginQuietCapture() { lock.lock(); capture = []; lock.unlock() }

    /// Sets the quiet levels from the captured still pose. Returns false if too few samples.
    @discardableResult
    func endQuietCapture() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard let c = capture, c.count >= 50 else { capture = nil; return false }
        capture = nil
        func median(_ v: [Double]) -> Double { let s = v.sorted(); return s[s.count / 2] }
        let r = median(c.map(\.0)) + 1e-4, j = median(c.map(\.1)) + 1e-4
        qScore = median(c.map { $0.0 / r + $0.1 / j })
        qRot = r * quietScale
        qJerk = j * quietScale
        calibrated = true
        return true
    }

    // ------------------------------------------------------------------ samples (motion queue)
    func push(sensorNs: Int64, rot: (Double, Double, Double), acc: (Double, Double, Double)) {
        lock.lock()
        defer { lock.unlock() }
        if let l = lastNs, sensorNs - l > 100_000_000 { reset(closeAt: l) }   // data gap: end what was open
        lastNs = sensorNs
        let g = (rot.0 * rot.0 + rot.1 * rot.1 + rot.2 * rot.2).squareRoot()
        var j = 0.0
        if let p = prev {
            let d0 = acc.0 - p.0, d1 = acc.1 - p.1, d2 = acc.2 - p.2
            j = (d0 * d0 + d1 * d1 + d2 * d2).squareRoot()
        }
        prev = acc
        capture?.append((g, j))
        gBuf.append(g); if gBuf.count > nSmooth { gBuf.removeFirst() }
        jBuf.append(j); if jBuf.count > nSmooth { jBuf.removeFirst() }
        history.append(sensorNs); if history.count > nPre + nOnset { history.removeFirst() }
        let s = gBuf.reduce(0, +) / Double(gBuf.count) / qRot + jBuf.reduce(0, +) / Double(jBuf.count) / qJerk

        if !recording {
            onset = s > kOn * qScore ? onset + 1 : 0
            if onset >= nOnset {
                recording = true
                quietRun = 0
                startNs = history.first ?? sensorNs
                lastActiveNs = sensorNs
                samplesInEvent = history.count
                energy = g * g
            }
            return
        }
        samplesInEvent += 1
        energy += g * g
        if s > kOff * qScore { quietRun = 0; lastActiveNs = sensorNs } else { quietRun += 1 }
        if quietRun >= nEnd {
            close(endNs: lastActiveNs)
        } else if samplesInEvent >= nMax {
            close(endNs: sensorNs)
            recording = true                 // motion goes on: start the next piece right away
            startNs = sensorNs
            samplesInEvent = 0
            energy = 0
        }
    }

    private func close(endNs: Int64) {
        if Double(endNs - startNs) / 1e9 >= Double(nMin) / 50.0 {
            events.append(LiveEvent(startNs: startNs, endNs: endNs, energy: energy))
            if events.count > 200 { events.removeFirst(events.count - 200) }
            closedQueue.append(events[events.count - 1])
            if closedQueue.count > 50 { closedQueue.removeFirst(closedQueue.count - 50) }
        }
        recording = false
        onset = 0
    }

    private func reset(closeAt: Int64) {
        if recording { close(endNs: closeAt) }
        gBuf.removeAll(); jBuf.removeAll(); history.removeAll()
        prev = nil
        onset = 0
    }

    /// Events that ended since the last call (the live recogniser takes each event once, right after it ends).
    func takeClosed() -> [LiveEvent] {
        lock.lock()
        defer { lock.unlock() }
        let out = closedQueue
        closedQueue.removeAll()
        return out
    }

    // ------------------------------------------------------------------ questions from the runner (main thread)
    func events(startingFrom a: Int64, to b: Int64) -> [LiveEvent] {
        lock.lock()
        defer { lock.unlock() }
        var out = events.filter { $0.startNs >= a && $0.startNs < b }
        if recording && startNs >= a && startNs < b, let l = lastNs {   // still moving: count it as running
            out.append(LiveEvent(startNs: startNs, endNs: l, energy: energy))
        }
        return out
    }

    /// Verdict for one cue window. expected = 1 (motion), 2 (command), 0 (idle / still).
    func verdict(from a: Int64, to b: Int64, expected: Int) -> LiveVerdict {
        let ev = events(startingFrom: a, to: b)
        let biggest = ev.map(\.energy).max() ?? 0
        let real = ev.filter { $0.energy >= 0.25 * biggest }
        let n = real.count
        let longest = real.map(\.durationS).max() ?? 0
        switch expected {
        case 0:
            return n == 0 ? LiveVerdict(count: 0, ok: true, text: "✓ still")
                          : LiveVerdict(count: n, ok: false, text: "We saw a movement: stay natural, no gesture")
        case 2:
            if n == 0 { return LiveVerdict(count: 0, ok: false, text: "No motion seen") }
            if n == 1 { return LiveVerdict(count: 1, ok: false, text: "We saw one motion: a command is TWO motions") }
            if n == 2 { return LiveVerdict(count: 2, ok: true, text: "✓ two motions") }
            return LiveVerdict(count: n, ok: false, text: "We saw \(n) motions: just the two, once each")
        default:
            if n == 0 { return LiveVerdict(count: 0, ok: false, text: "No motion seen: a bit bigger next time") }
            if longest >= 3.9 { return LiveVerdict(count: n, ok: false, text: "Too long: ONE smooth go, straight back, don't repeat or hold") }
            if n == 1 { return LiveVerdict(count: 1, ok: true, text: "✓ one motion") }
            return LiveVerdict(count: n, ok: false, text: "We saw \(n) motions: do it ONCE")
        }
    }
}
