// The few things that differ between the Mac app and the iPhone app. Everything else is shared code.
//   Mac:    data folder ~/Documents/GestureCollector (changeable), system sounds, Finder, ditto zip, system_profiler
//   iPhone: the app's Documents folder (visible in the Files app: On My iPhone > Gesture Collector), short tones
//           played through the AirPods, share sheet for the zip, headphones name from the audio route, screen kept on

import AVFoundation
import Foundation
import SwiftUI
#if os(macOS)
import AppKit
typealias PlatformColor = NSColor
#else
import UIKit
typealias PlatformColor = UIColor
#endif

enum Platform {
    #if os(macOS)
    static let isPhone = false
    static let name = "macOS"
    #else
    static let isPhone = true
    static let name = "iOS"
    #endif

    static var osVersion: String {
        let v = ProcessInfo.processInfo.operatingSystemVersion
        return "\(name) \(v.majorVersion).\(v.minorVersion).\(v.patchVersion)"
    }

    /// Hardware model: "Mac14,2", "iPhone15,3", ...
    static var deviceModel: String {
        #if os(macOS)
        var size = 0
        sysctlbyname("hw.model", nil, &size, nil, 0)
        guard size > 0 else { return "unknown" }
        var buf = [CChar](repeating: 0, count: size)
        sysctlbyname("hw.model", &buf, &size, nil, 0)
        return String(cString: buf)
        #else
        var u = utsname()
        uname(&u)
        return withUnsafeBytes(of: &u.machine) { raw in
            String(decoding: raw.prefix { $0 != 0 }, as: UTF8.self)
        }
        #endif
    }

    static var defaultDataRoot: URL {
        #if os(macOS)
        return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Documents/GestureCollector")
        #else
        return FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        #endif
    }

    // ------------------------------------------------------------------ audio
    /// iPhone: play speech and beeps through the AirPods even with the silent switch on.
    static func configureAudio() {
        #if os(iOS)
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio, options: [])
        try? AVAudioSession.sharedInstance().setActive(true)
        #endif
    }

    #if os(iOS)
    private static var players: [String: AVAudioPlayer] = [:]

    /// A short sine tone as an in-memory WAV (no sound files needed).
    private static func tone(_ hz: Double, _ seconds: Double) -> Data {
        let rate = 44_100, n = Int(Double(rate) * seconds)
        var pcm = Data(capacity: n * 2)
        for i in 0..<n {
            let t = Double(i) / Double(rate)
            let env = min(1, min(t, seconds - t) / 0.01)                    // 10 ms fade in/out, no clicks
            var v = Int16(sin(2 * Double.pi * hz * t) * env * 0.5 * Double(Int16.max))
            withUnsafeBytes(of: &v) { pcm.append(contentsOf: $0) }
        }
        var d = Data()
        func u32(_ x: UInt32) { var y = x.littleEndian; withUnsafeBytes(of: &y) { d.append(contentsOf: $0) } }
        func u16(_ x: UInt16) { var y = x.littleEndian; withUnsafeBytes(of: &y) { d.append(contentsOf: $0) } }
        d.append(contentsOf: Array("RIFF".utf8)); u32(UInt32(36 + pcm.count)); d.append(contentsOf: Array("WAVE".utf8))
        d.append(contentsOf: Array("fmt ".utf8)); u32(16); u16(1); u16(1); u32(UInt32(rate)); u32(UInt32(rate * 2)); u16(2); u16(16)
        d.append(contentsOf: Array("data".utf8)); u32(UInt32(pcm.count)); d.append(pcm)
        return d
    }
    #endif

    /// Named sounds: "Tink" (ready / motion), "Pop" (GO), "Bottle" (end), "Glass" (command).
    static func sound(_ name: String) {
        #if os(macOS)
        NSSound(named: NSSound.Name(name))?.play()
        #else
        let spec: [String: (Double, Double)] = ["Tink": (1320, 0.06), "Pop": (880, 0.12), "Bottle": (520, 0.18), "Glass": (1046, 0.25)]
        let (hz, s) = spec[name] ?? (880, 0.1)
        if players[name] == nil { players[name] = try? AVAudioPlayer(data: tone(hz, s)) }
        players[name]?.currentTime = 0
        players[name]?.play()
        #endif
    }

    /// Keep the screen on during a session (iPhone; the Mac does not sleep while the app is in front).
    static func keepAwake(_ on: Bool) {
        #if os(iOS)
        UIApplication.shared.isIdleTimerDisabled = on
        #endif
    }

    // ------------------------------------------------------------------ files
    /// Zip of a folder, next to it.
    static func zip(folder: URL) -> URL? {
        let dest = folder.deletingLastPathComponent().appendingPathComponent(folder.lastPathComponent + ".zip")
        try? FileManager.default.removeItem(at: dest)
        #if os(macOS)
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
        p.arguments = ["-c", "-k", "--keepParent", folder.path, dest.path]
        do { try p.run(); p.waitUntilExit() } catch { return nil }
        return p.terminationStatus == 0 ? dest : nil
        #else
        var result: URL?
        var err: NSError?
        NSFileCoordinator().coordinate(readingItemAt: folder, options: .forUploading, error: &err) { tmp in
            if (try? FileManager.default.copyItem(at: tmp, to: dest)) != nil { result = dest }
        }
        return result
        #endif
    }

    static func reveal(_ url: URL) {
        #if os(macOS)
        NSWorkspace.shared.activateFileViewerSelecting([url])
        #endif
    }

    // ------------------------------------------------------------------ which headphones
    /// Mac: name, product ID and firmware from `system_profiler SPBluetoothDataType -json`.
    /// iPhone: the name of the current audio output (e.g. "Rahul's AirPods Pro").
    static func headphones() -> [String: String] {
        #if os(macOS)
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/sbin/system_profiler")
        p.arguments = ["SPBluetoothDataType", "-json"]
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = FileHandle.nullDevice
        do { try p.run() } catch { return ["error": "system_profiler failed"] }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = root["SPBluetoothDataType"] as? [[String: Any]] else { return ["error": "no Bluetooth info"] }
        for item in items {
            for dev in (item["device_connected"] as? [[String: Any]]) ?? [] {
                for (name, value) in dev {
                    guard let props = value as? [String: Any] else { continue }
                    let minor = props["device_minorType"] as? String ?? ""
                    if name.localizedCaseInsensitiveContains("airpods") || minor == "Headphones" {
                        return ["name": name,
                                "productID": props["device_productID"] as? String ?? "",
                                "vendorID": props["device_vendorID"] as? String ?? "",
                                "firmware": props["device_firmwareVersion"] as? String ?? "",
                                "minorType": minor]
                    }
                }
            }
        }
        return ["error": "no connected headphones found"]
        #else
        configureAudio()
        let outs = AVAudioSession.sharedInstance().currentRoute.outputs
        if let o = outs.first(where: { $0.portType == .bluetoothA2DP || $0.portType == .bluetoothHFP || $0.portType == .bluetoothLE }) {
            return ["name": o.portName, "port": o.portType.rawValue]
        }
        return ["error": "no Bluetooth headphones in the audio route (connect the AirPods to this iPhone)"]
        #endif
    }
}

/// Lays children side by side on the Mac and stacked on the iPhone (narrow screen).
struct AdaptiveStack<Content: View>: View {
    var spacing: CGFloat = 12
    @ViewBuilder var content: () -> Content

    var body: some View {
        if Platform.isPhone {
            VStack(alignment: .leading, spacing: spacing, content: content)
        } else {
            HStack(alignment: .top, spacing: spacing, content: content)
        }
    }
}
