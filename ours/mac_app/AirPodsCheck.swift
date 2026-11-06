// AirPods Motion Check (macOS 14+)
//
// Reads AirPods head motion through Apple's CMHeadphoneMotionManager and
//  - shows live values, the sample rate and which earbud is sending,
//  - optionally saves everything to a CSV in ~/Documents/AirPodsCheck/,
//  - optionally pushes it to our collector (ours/collector/collector_v3.py) in Sensor Logger's JSON format.
//
// Units: Apple gives gravity and user acceleration in g; we write them in m/s^2 (x 9.80665) so the files match
// Sensor Logger and the rest of our pipeline. Rotation rate rad/s, angles rad. Values are written exactly as
// Apple gives them (no axis flips). Build: bash build.sh

import AppKit
import CoreMotion
import SwiftUI

private let G = 9.80665
private let csvHeader = "sensor_ns,host_ns,yaw,pitch,roll,quatX,quatY,quatZ,quatW,rotX,rotY,rotZ,accX,accY,accZ,gravX,gravY,gravZ,sensor_location\n"

final class Recorder: NSObject, ObservableObject, CMHeadphoneMotionManagerDelegate {
    // Shown in the window (main thread only)
    @Published var status = "Starting..."
    @Published var connected = false
    @Published var rateHz = 0.0
    @Published var location = "-"
    @Published var lines: [String] = []
    @Published var recording = false
    @Published var savedSamples = 0
    @Published var filePath = ""
    @Published var pushURL = "http://192.168.1.10:8000/data"
    @Published var pushOn = false { didSet { lock.lock(); pushEnabled = pushOn; pending.removeAll(); lock.unlock() } }
    @Published var pushStatus = ""

    private let manager = CMHeadphoneMotionManager()
    private let queue: OperationQueue = {
        let q = OperationQueue()
        q.maxConcurrentOperationCount = 1
        q.name = "airpods-motion"
        return q
    }()

    // Shared between the motion queue and the main thread (guarded by lock)
    private let lock = NSLock()
    private var latest: CMDeviceMotion?
    private var countSinceTick = 0
    private var totalSamples = 0
    private var savedCount = 0
    private var file: FileHandle?
    private var pushEnabled = false
    private var pending: [[String: Any]] = []

    private let bootToEpoch = Date().timeIntervalSince1970 - ProcessInfo.processInfo.systemUptime
    private var lastRateTime = Date()
    private var tickCount = 0
    private var startTime = Date()

    override init() {
        super.init()
        manager.delegate = self
        start()
        Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in self?.tick() }
    }

    func start() {
        let auth: String
        switch CMHeadphoneMotionManager.authorizationStatus() {
        case .authorized: auth = "authorized"
        case .denied: auth = "DENIED - allow it in System Settings > Privacy & Security > Motion & Fitness"
        case .restricted: auth = "restricted"
        case .notDetermined: auth = "not asked yet (a permission prompt should appear)"
        @unknown default: auth = "unknown"
        }
        guard manager.isDeviceMotionAvailable else {
            status = "Headphone motion NOT available on this Mac (needs macOS 14+). Permission: \(auth)"
            return
        }
        status = "Waiting for AirPods... Permission: \(auth)"
        startTime = Date()
        manager.startDeviceMotionUpdates(to: queue) { [weak self] motion, error in
            guard let self = self else { return }
            if let error = error {
                DispatchQueue.main.async { self.status = "Error: \(error.localizedDescription)" }
                return
            }
            if let m = motion { self.handle(m) }
        }
    }

    // Motion queue
    private func handle(_ m: CMDeviceMotion) {
        let a = m.attitude, q = a.quaternion, r = m.rotationRate, u = m.userAcceleration, g = m.gravity
        let sensorNs = Int64((bootToEpoch + m.timestamp) * 1e9)
        let hostNs = Int64(Date().timeIntervalSince1970 * 1e9)
        let loc = Recorder.locationName(m)
        let vals: [Double] = [a.yaw, a.pitch, a.roll, q.x, q.y, q.z, q.w, r.x, r.y, r.z,
                              u.x * G, u.y * G, u.z * G, g.x * G, g.y * G, g.z * G]
        lock.lock()
        latest = m
        countSinceTick += 1
        totalSamples += 1
        if let f = file {
            let line = "\(sensorNs),\(hostNs)," + vals.map { String($0) }.joined(separator: ",") + ",\(loc)\n"
            f.write(line.data(using: .utf8)!)
            savedCount += 1
        }
        if pushEnabled && pending.count < 5000 {
            let keys = ["yaw", "pitch", "roll", "quaternionX", "quaternionY", "quaternionZ", "quaternionW",
                        "rotationRateX", "rotationRateY", "rotationRateZ", "accelerationX", "accelerationY",
                        "accelerationZ", "gravityX", "gravityY", "gravityZ"]
            var v: [String: Any] = [:]
            for (k, x) in zip(keys, vals) { v[k] = x }
            pending.append(["name": "headphone", "time": sensorNs, "values": v])
        }
        lock.unlock()
    }

    static func locationName(_ m: CMDeviceMotion) -> String {
        switch m.sensorLocation {
        case .headphoneLeft: return "left"
        case .headphoneRight: return "right"
        case .default: return "default"
        @unknown default: return "unknown"
        }
    }

    // Main thread, every 0.1 s
    private func tick() {
        tickCount += 1
        lock.lock()
        let m = latest
        let n = countSinceTick
        let total = totalSamples
        let saved = savedCount
        var batch: [[String: Any]] = []
        if tickCount % 3 == 0 { batch = pending; pending.removeAll() }
        if tickCount % 10 == 0 { countSinceTick = 0 }
        lock.unlock()

        if tickCount % 10 == 0 {
            let now = Date()
            rateHz = Double(n) / now.timeIntervalSince(lastRateTime)
            lastRateTime = now
            if total == 0 && now.timeIntervalSince(startTime) > 3 {
                status = connected
                    ? "AirPods connected but no data: put BOTH AirPods in your ears."
                    : "No AirPods data yet: connect AirPods to THIS Mac (Control Center > Sound) and wear them."
            } else if total > 0 {
                status = rateHz > 40 ? "Receiving data OK" : (rateHz > 0 ? "Receiving data, but rate is low" : "Data stopped")
            }
        }
        savedSamples = saved
        if let m = m {
            let a = m.attitude, q = a.quaternion, r = m.rotationRate, u = m.userAcceleration, g = m.gravity
            location = Recorder.locationName(m)
            let f = { (x: Double) in String(format: "%+8.3f", x) }
            let gm = (g.x * g.x + g.y * g.y + g.z * g.z).squareRoot() * G
            lines = [
                "rotation rate  (rad/s)  x \(f(r.x))  y \(f(r.y))  z \(f(r.z))",
                "user accel     (m/s^2)  x \(f(u.x * G))  y \(f(u.y * G))  z \(f(u.z * G))",
                "gravity        (m/s^2)  x \(f(g.x * G))  y \(f(g.y * G))  z \(f(g.z * G))   |g| \(f(gm))",
                "quaternion              x \(f(q.x))  y \(f(q.y))  z \(f(q.z))  w \(f(q.w))",
                "angles         (rad)    yaw \(f(a.yaw))  pitch \(f(a.pitch))  roll \(f(a.roll))",
                "samples received        \(total)",
            ]
        }
        if !batch.isEmpty { push(batch) }
    }

    private func push(_ batch: [[String: Any]]) {
        guard let url = URL(string: pushURL),
              let body = try? JSONSerialization.data(withJSONObject: ["payload": batch]) else {
            pushStatus = "Bad push URL"
            return
        }
        var req = URLRequest(url: url, timeoutInterval: 2)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body
        URLSession.shared.dataTask(with: req) { [weak self] _, resp, err in
            let msg: String
            if let err = err { msg = "Push failed: \(err.localizedDescription)" }
            else { msg = "Push OK (HTTP \((resp as? HTTPURLResponse)?.statusCode ?? 0))" }
            DispatchQueue.main.async { self?.pushStatus = msg }
        }.resume()
    }

    func toggleRecording() {
        if recording {
            lock.lock(); try? file?.close(); file = nil; lock.unlock()
            recording = false
            return
        }
        let dir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Documents/AirPodsCheck")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let stamp = DateFormatter()
        stamp.dateFormat = "yyyyMMdd_HHmmss"
        let url = dir.appendingPathComponent("airpods_\(stamp.string(from: Date())).csv")
        FileManager.default.createFile(atPath: url.path, contents: csvHeader.data(using: .utf8))
        guard let h = try? FileHandle(forWritingTo: url) else {
            status = "Could not create \(url.path)"
            return
        }
        h.seekToEndOfFile()
        lock.lock(); file = h; savedCount = 0; lock.unlock()
        filePath = url.path
        recording = true
    }

    func showFile() {
        guard !filePath.isEmpty else { return }
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: filePath)])
    }

    func headphoneMotionManagerDidConnect(_ manager: CMHeadphoneMotionManager) {
        DispatchQueue.main.async { self.connected = true }
    }

    func headphoneMotionManagerDidDisconnect(_ manager: CMHeadphoneMotionManager) {
        DispatchQueue.main.async { self.connected = false; self.status = "AirPods disconnected" }
    }
}

struct ContentView: View {
    @EnvironmentObject var rec: Recorder

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("AirPods Motion Check").font(.title2).bold()
            Text(rec.status).foregroundColor(rec.rateHz > 40 ? .green : .orange)
            HStack(spacing: 24) {
                Label(rec.connected ? "connected" : "not connected", systemImage: "airpodspro")
                Text(String(format: "rate %.0f Hz", rec.rateHz))
                Text("earbud: \(rec.location)")
            }
            GroupBox {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(rec.lines, id: \.self) { Text($0).font(.system(.body, design: .monospaced)) }
                    if rec.lines.isEmpty { Text("no samples yet").foregroundColor(.secondary) }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            Text("Check: |g| should be about 9.81; rotation should jump when you nod; rate about 50 Hz.")
                .font(.caption).foregroundColor(.secondary)
            Divider()
            HStack {
                Button(rec.recording ? "Stop saving CSV" : "Save to CSV") { rec.toggleRecording() }
                if rec.recording { Text("\(rec.savedSamples) samples") }
                Button("Show file") { rec.showFile() }.disabled(rec.filePath.isEmpty)
            }
            if !rec.filePath.isEmpty { Text(rec.filePath).font(.caption).textSelection(.enabled) }
            Divider()
            Toggle("Send to collector (collector_v3.py)", isOn: $rec.pushOn)
            TextField("http://<PC IP>:8000/data", text: $rec.pushURL).textFieldStyle(.roundedBorder)
                .disabled(rec.pushOn)
            if !rec.pushStatus.isEmpty { Text(rec.pushStatus).font(.caption) }
            Spacer()
        }
        .padding(20)
    }
}

@main
struct AirPodsCheckApp: App {
    @StateObject private var rec = Recorder()

    var body: some Scene {
        WindowGroup("AirPods Motion Check") {
            ContentView().environmentObject(rec).frame(minWidth: 640, minHeight: 560)
        }
    }
}
