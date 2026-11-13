// v3.7 optional scene video: the Mac's webcam (iPhone: the front camera) films the participant during a session.
// Uses: show later pilots real people doing each gesture, check labels ("did they really do X?"), document the setup.
//
// Files (one per segment, like stream_NNN.csv):
//   <data folder>/video/<session folder>/scene_NNN.mp4   HEVC (H.265; H.264 if the device has no HEVC encoder),
//                                                        small = 480p ~0.6 Mbit/s (~0.25 GB/h), normal = 720p
//                                                        ~1.2 Mbit/s (~0.5 GB/h), 15 fps, no audio. OUTSIDE the session folder, so the
//                                                        session zip never carries faces unless added on purpose.
//   <session folder>/scene_NNN_frames.csv                frame,video_s,sensor_ns: every written frame's time in the
//                                                        video and on the sensor clock (same clock as cues.csv
//                                                        sensor_ns_est), so any cue can be cut out exactly.
// Only with the participant's video consent (roster) and the session's "Record scene video" switch.

import AVFoundation
import Foundation
import SwiftUI
#if os(macOS)
import AppKit
#else
import UIKit
#endif

final class SceneCamera: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    let dir: URL
    let framesDir: URL
    let quality: String
    private let session = AVCaptureSession()
    private let queue = DispatchQueue(label: "gesturecollector.scene")
    private var configured = false
    private var recording = false
    private var writer: AVAssetWriter?
    private var input: AVAssetWriterInput?
    private var frames: FileHandle?
    private var startPTS: CMTime?
    private var frameIndex = 0
    private var fileName = ""
    private var log: @Sendable (String) -> Void = { _ in }

    init(dir: URL, framesDir: URL, quality: String = "small") {
        self.dir = dir
        self.framesDir = framesDir
        self.quality = quality
    }

    /// Small enough for hours of sessions; a face doing a gesture needs neither 30 fps nor high bitrate.
    private var small: Bool { quality != "normal" }

    /// Camera permission (asks the first time). done runs on the main thread.
    static func requestAccess(_ done: @escaping (Bool) -> Void) {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: done(true)
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { ok in DispatchQueue.main.async { done(ok) } }
        default: done(false)
        }
    }

    static var available: Bool { device != nil }

    static var device: AVCaptureDevice? {
        #if os(iOS)
        return AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .front)
        #else
        return AVCaptureDevice.default(for: .video)
        #endif
    }

    // ------------------------------------------------------------------ control (any thread)
    func start(segment: Int, log: @escaping @Sendable (String) -> Void) {
        queue.async {
            self.log = log
            self.begin(segment)
        }
    }

    /// Synchronous: the camera is free when this returns (iOS: one capture session at a time).
    func stop() {
        queue.sync { self.end() }
    }

    // ------------------------------------------------------------------ on the camera queue
    private func configure() -> Bool {
        guard let dev = SceneCamera.device, let inp = try? AVCaptureDeviceInput(device: dev) else { return false }
        session.beginConfiguration()
        defer { session.commitConfiguration() }
        #if os(iOS)
        session.automaticallyConfiguresApplicationAudioSession = false   // keep the cue audio setup as it is
        #endif
        let want: AVCaptureSession.Preset = small ? .vga640x480 : .hd1280x720
        session.sessionPreset = session.canSetSessionPreset(want) ? want : .medium
        guard session.canAddInput(inp) else { return false }
        session.addInput(inp)
        // 15 fps is plenty for gestures (the file size is set by the bitrate; iPhone only, the Mac keeps its default)
        #if os(iOS)
        if (try? dev.lockForConfiguration()) != nil {
            let fps15 = CMTime(value: 1, timescale: 15)
            if dev.activeFormat.videoSupportedFrameRateRanges.contains(where: { $0.minFrameDuration <= fps15 && fps15 <= $0.maxFrameDuration }) {
                dev.activeVideoMinFrameDuration = fps15
                dev.activeVideoMaxFrameDuration = fps15
            }
            dev.unlockForConfiguration()
        }
        #endif
        let out = AVCaptureVideoDataOutput()
        out.alwaysDiscardsLateVideoFrames = true
        out.setSampleBufferDelegate(self, queue: queue)
        guard session.canAddOutput(out) else { return false }
        session.addOutput(out)
        #if os(iOS)
        if let c = out.connection(with: .video), c.isVideoOrientationSupported { c.videoOrientation = .portrait }
        #endif
        return true
    }

    private func begin(_ segment: Int) {
        guard AVCaptureDevice.authorizationStatus(for: .video) == .authorized else {
            log("no camera permission: not recorded (System Settings > Privacy > Camera)")
            return
        }
        if !configured {
            configured = configure()
            guard configured else { log("no usable camera: not recorded"); return }
        }
        let fm = FileManager.default
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        fileName = String(format: "scene_%03d.mp4", segment)
        let url = dir.appendingPathComponent(fileName)
        try? fm.removeItem(at: url)
        guard let w = try? AVAssetWriter(outputURL: url, fileType: .mp4) else { log("could not create \(fileName)"); return }
        writer = w
        input = nil
        startPTS = nil
        frameIndex = 0
        let fURL = framesDir.appendingPathComponent(String(format: "scene_%03d_frames.csv", segment))
        fm.createFile(atPath: fURL.path, contents: "frame,video_s,sensor_ns\n".data(using: .utf8))
        frames = try? FileHandle(forWritingTo: fURL)
        frames?.seekToEndOfFile()
        recording = true
        for _ in 0..<5 where !session.isRunning {      // the preview may still be letting go of the camera
            session.startRunning()
            if !session.isRunning { Thread.sleep(forTimeInterval: 0.3) }
        }
        log(session.isRunning ? "recording \(dir.lastPathComponent)/\(fileName)" : "camera did not start: \(fileName) may be empty")
    }

    private func end() {
        guard recording else { if session.isRunning { session.stopRunning() }; return }
        recording = false
        try? frames?.close()
        frames = nil
        let name = fileName, n = frameIndex, logger = log
        if let w = writer, let i = input, w.status == .writing {
            i.markAsFinished()
            w.finishWriting { _ = w; logger("saved \(name) (\(n) frames)") }   // keep the writer alive until done
        } else {
            writer?.cancelWriting()
            logger("no frames recorded for \(name)")
        }
        writer = nil
        input = nil
        session.stopRunning()
    }

    /// The frame's capture time on the sensor clock (CMDeviceMotion timestamps are seconds since boot, as is the
    /// host time clock), so scene_NNN_frames.csv lines up with cues.csv and stream_NNN.csv.
    private func sensorNs(_ pts: CMTime) -> Int64 {
        let clock = session.synchronizationClock ?? CMClockGetHostTimeClock()
        let host = CMSyncConvertTime(pts, from: clock, to: CMClockGetHostTimeClock())
        let s = CMTimeGetSeconds(host)
        // some external webcams give no clock relation: never crash on NaN, use the arrival time instead
        guard host.isValid, s.isFinite else { return sensorNowNs() }
        return Int64((BOOT_TO_EPOCH + s) * 1e9)
    }

    func captureOutput(_ output: AVCaptureOutput, didOutput sb: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard recording, let w = writer else { return }
        let pts = CMSampleBufferGetPresentationTimeStamp(sb)
        if input == nil {
            guard let fd = CMSampleBufferGetFormatDescription(sb) else { return }
            let dim = CMVideoFormatDescriptionGetDimensions(fd)
            let width = Int(dim.width), height = Int(dim.height)   // as delivered (portrait on iPhone if rotated)
            func settings(_ codec: AVVideoCodecType, _ bps: Int) -> [String: Any] {
                [AVVideoCodecKey: codec, AVVideoWidthKey: width, AVVideoHeightKey: height,
                 AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: bps,
                                                   AVVideoMaxKeyFrameIntervalKey: 30,
                                                   AVVideoExpectedSourceFrameRateKey: 15]]
            }
            // HEVC at about half the H.264 bitrate for the same look; H.264 when there is no HEVC encoder
            let hevcOK = w.canApply(outputSettings: settings(.hevc, 1), forMediaType: .video)
            let codec: AVVideoCodecType = hevcOK ? .hevc : .h264
            let bps = (small ? 600_000 : 1_200_000) * (hevcOK ? 1 : 2)
            let i = AVAssetWriterInput(mediaType: .video, outputSettings: settings(codec, bps))
            i.expectsMediaDataInRealTime = true
            guard w.canAdd(i) else { log("video writer refused the format"); recording = false; return }
            w.add(i)
            log("\(width)x\(height) \(hevcOK ? "HEVC" : "H.264") \(bps / 1000) kbit/s")
            guard w.startWriting() else {
                log("video writer failed: \(w.error?.localizedDescription ?? "?")")
                recording = false
                return
            }
            w.startSession(atSourceTime: pts)
            input = i
            startPTS = pts
        }
        guard let i = input, i.isReadyForMoreMediaData, let t0 = startPTS else { return }   // busy: frame dropped, no row
        if i.append(sb) {
            let videoS = CMTimeGetSeconds(CMTimeSubtract(pts, t0))
            let line = "\(frameIndex),\(String(format: "%.4f", videoS)),\(sensorNs(pts))\n"
            if let d = line.data(using: .utf8) { frames?.write(d) }
            frameIndex += 1
        }
    }
}

// ---------------------------------------------------------------------------------------------------- preview
/// Live camera picture on the device-check screen, to aim the camera before the session (not recorded).
final class CameraPreviewModel: ObservableObject {
    let session = AVCaptureSession()
    private let queue = DispatchQueue(label: "gesturecollector.preview")
    private var configured = false

    func start() {
        queue.async {
            if !self.configured {
                guard let dev = SceneCamera.device, let inp = try? AVCaptureDeviceInput(device: dev),
                      self.session.canAddInput(inp) else { return }
                self.session.beginConfiguration()
                self.session.sessionPreset = .medium
                self.session.addInput(inp)
                self.session.commitConfiguration()
                self.configured = true
            }
            if !self.session.isRunning { self.session.startRunning() }
        }
    }

    /// Synchronous on purpose: the session's recorder needs the camera right after (iOS allows one user).
    func stop() {
        queue.sync { if self.session.isRunning { self.session.stopRunning() } }
    }
}

#if os(macOS)
/// v3.7.1: an ordinary layer-BACKED view with the preview as a sublayer (not a layer-hosting view), and it never
/// takes part in hit testing: the v3.7.0 crash (macOS 27, SwiftUI hit test of a trackpad pressure event) was in
/// SwiftUI's hit testing of embedded AppKit views while the camera was on.
final class PreviewNSView: NSView {
    let preview: AVCaptureVideoPreviewLayer
    init(session: AVCaptureSession) {
        preview = AVCaptureVideoPreviewLayer(session: session)
        super.init(frame: .zero)
        wantsLayer = true
        preview.videoGravity = .resizeAspect
        layer?.addSublayer(preview)
    }
    required init?(coder: NSCoder) { nil }
    override func layout() {
        super.layout()
        preview.frame = bounds
    }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
}

struct CameraPreview: NSViewRepresentable {
    let session: AVCaptureSession
    func makeNSView(context: Context) -> PreviewNSView { PreviewNSView(session: session) }
    func updateNSView(_ nsView: PreviewNSView, context: Context) {}
}
#else
final class PreviewUIView: UIView {
    override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
}

struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession
    func makeUIView(context: Context) -> PreviewUIView {
        let v = PreviewUIView()
        if let l = v.layer as? AVCaptureVideoPreviewLayer {
            l.session = session
            l.videoGravity = .resizeAspect
        }
        return v
    }
    func updateUIView(_ uiView: PreviewUIView, context: Context) {}
}
#endif
