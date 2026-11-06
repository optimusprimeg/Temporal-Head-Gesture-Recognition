// AirPods motion through CMHeadphoneMotionManager. Writes every sample to the current segment file
// (stream_NNN.csv) and reports rate, streaming earbud, |g|, head angles (for the live head), earbud switches and
// data gaps. Same columns and units as the AirPods Check app and gesturekit: m/s^2, rad/s, rad, Apple's raw axes.
//
// Clock: sensor_ns = (boot time in epoch + CMDeviceMotion.timestamp). Cue times use the SAME clock
// (boot time + systemUptime at the beep), so cues and samples need no alignment.

import CoreMotion
import Foundation

let G = 9.80665
let BOOT_TO_EPOCH: Double = Date().timeIntervalSince1970 - ProcessInfo.processInfo.systemUptime
let STREAM_HEADER = "sensor_ns,host_ns,yaw,pitch,roll,quatX,quatY,quatZ,quatW,rotX,rotY,rotZ,accX,accY,accZ,gravX,gravY,gravZ,sensor_location\n"

func sensorNowNs() -> Int64 { Int64((BOOT_TO_EPOCH + ProcessInfo.processInfo.systemUptime) * 1e9) }
func hostNowNs() -> Int64 { Int64(Date().timeIntervalSince1970 * 1e9) }

struct HeadAngles: Equatable {
    var pitch = 0.0, roll = 0.0, yaw = 0.0
}

final class Recorder: NSObject, ObservableObject, CMHeadphoneMotionManagerDelegate {
    // main thread only
    @Published var status = "Starting..."
    @Published var connected = false
    @Published var rateHz = 0.0
    @Published var location = "-"
    @Published var gravityNorm = 0.0
    @Published var angles = HeadAngles()
    @Published var segmentSamples = 0
    @Published var segmentPath = ""

    var onSwitch: ((String, String) -> Void)?   // (from, to), called on the main thread
    var onGap: ((Double) -> Void)?               // gap length in s, called on the main thread

    private let manager = CMHeadphoneMotionManager()
    private let queue: OperationQueue = {
        let q = OperationQueue()
        q.maxConcurrentOperationCount = 1
        q.name = "airpods-motion"
        return q
    }()

    // shared with the motion queue (lock)
    private let lock = NSLock()
    private var file: FileHandle?
    private var latest: CMDeviceMotion?
    private var countSinceTick = 0
    private var totalSamples = 0
    private var written = 0
    private var lastLocation: String?
    private var lastTimestamp: Double?
    private var pendingSwitch: (String, String)?
    private var pendingGap: Double?

    private var tickCount = 0
    private var lastRateTime = Date()
    private let startTime = Date()

    override init() {
        super.init()
        manager.delegate = self
        start()
        Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in self?.tick() }
    }

    func start() {
        guard manager.isDeviceMotionAvailable else {
            status = "Headphone motion is not available on this Mac (needs macOS 14+)."
            return
        }
        if CMHeadphoneMotionManager.authorizationStatus() == .denied {
            status = "Permission DENIED: System Settings > Privacy & Security > Motion & Fitness"
        }
        manager.startDeviceMotionUpdates(to: queue) { [weak self] motion, error in
            guard let self = self else { return }
            if let error = error {
                DispatchQueue.main.async { self.status = "Error: \(error.localizedDescription)" }
                return
            }
            if let m = motion { self.handle(m) }
        }
    }

    static func locationName(_ m: CMDeviceMotion) -> String {
        switch m.sensorLocation {
        case .headphoneLeft: return "left"
        case .headphoneRight: return "right"
        case .default: return "default"
        @unknown default: return "unknown"
        }
    }

    // motion queue
    private func handle(_ m: CMDeviceMotion) {
        let a = m.attitude, q = a.quaternion, r = m.rotationRate, u = m.userAcceleration, g = m.gravity
        let sensorNs = Int64((BOOT_TO_EPOCH + m.timestamp) * 1e9)
        let loc = Recorder.locationName(m)
        let vals: [Double] = [a.yaw, a.pitch, a.roll, q.x, q.y, q.z, q.w, r.x, r.y, r.z,
                              u.x * G, u.y * G, u.z * G, g.x * G, g.y * G, g.z * G]
        let line = "\(sensorNs),\(hostNowNs())," + vals.map { String($0) }.joined(separator: ",") + ",\(loc)\n"
        lock.lock()
        if let last = lastLocation, last != loc { pendingSwitch = (last, loc) }
        if let lt = lastTimestamp, m.timestamp - lt > 1.0 { pendingGap = m.timestamp - lt }
        lastLocation = loc
        lastTimestamp = m.timestamp
        latest = m
        countSinceTick += 1
        totalSamples += 1
        if let f = file, let d = line.data(using: .utf8) {
            f.write(d)
            written += 1
        }
        lock.unlock()
    }

    // main thread, every 0.1 s
    private func tick() {
        tickCount += 1
        lock.lock()
        let m = latest, n = countSinceTick, total = totalSamples, w = written
        let sw = pendingSwitch, gap = pendingGap
        pendingSwitch = nil
        pendingGap = nil
        if tickCount % 10 == 0 { countSinceTick = 0 }
        lock.unlock()

        if let sw = sw { onSwitch?(sw.0, sw.1) }
        if let gap = gap { onGap?(gap) }
        segmentSamples = w
        if tickCount % 10 == 0 {
            let now = Date()
            rateHz = Double(n) / now.timeIntervalSince(lastRateTime)
            lastRateTime = now
            if total == 0 && now.timeIntervalSince(startTime) > 3 {
                status = connected ? "AirPods connected but no data: put BOTH AirPods in."
                                   : "No AirPods data: connect AirPods to THIS Mac and wear them."
            } else if total > 0 {
                status = rateHz > 40 ? "Receiving data OK" : (rateHz > 0 ? "Data rate is LOW" : "Data STOPPED")
            }
        }
        if let m = m {
            let g = m.gravity
            gravityNorm = (g.x * g.x + g.y * g.y + g.z * g.z).squareRoot() * G
            location = Recorder.locationName(m)
            angles = HeadAngles(pitch: m.attitude.pitch, roll: m.attitude.roll, yaw: m.attitude.yaw)
        }
    }

    var healthy: Bool { rateHz > 40 && abs(gravityNorm - 9.81) < 0.5 }

    // ------------------------------------------------------------------ segment files
    func startSegment(at url: URL) throws {
        FileManager.default.createFile(atPath: url.path, contents: STREAM_HEADER.data(using: .utf8))
        let h = try FileHandle(forWritingTo: url)
        h.seekToEndOfFile()
        lock.lock()
        try? file?.close()
        file = h
        written = 0
        lock.unlock()
        segmentPath = url.path
    }

    func stopSegment() {
        lock.lock()
        try? file?.synchronize()
        try? file?.close()
        file = nil
        lock.unlock()
    }

    func flush() {
        lock.lock()
        try? file?.synchronize()
        lock.unlock()
    }

    func headphoneMotionManagerDidConnect(_ manager: CMHeadphoneMotionManager) {
        DispatchQueue.main.async { self.connected = true }
    }

    func headphoneMotionManagerDidDisconnect(_ manager: CMHeadphoneMotionManager) {
        DispatchQueue.main.async { self.connected = false; self.status = "AirPods DISCONNECTED" }
    }
}
