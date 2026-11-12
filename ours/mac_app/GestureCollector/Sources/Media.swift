// v3.3 demo clips: an animated GIF per motion in <data folder>/experiments/media/<motion id>.gif plays in a loop in
// place of the 3D head demo. Clips are files, so adding or replacing one needs no rebuild
// (algorithm/scripts/make_gesture_clips.py draws the built-in cartoon set). Mac and iPhone (ImageIO).

import Foundation
import ImageIO
import SwiftUI

final class ClipCache {
    static let shared = ClipCache()
    private let lock = NSLock()
    private var store: [URL: (frames: [CGImage], delays: [Double])] = [:]

    /// Frames and per-frame delays (s) of a GIF, decoded once. nil if the file is missing or not an image.
    func clip(_ url: URL) -> (frames: [CGImage], delays: [Double])? {
        lock.lock()
        if let c = store[url] { lock.unlock(); return c }
        lock.unlock()
        guard let src = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
        let n = CGImageSourceGetCount(src)
        var frames: [CGImage] = [], delays: [Double] = []
        for i in 0..<n {
            guard let img = CGImageSourceCreateImageAtIndex(src, i, nil) else { continue }
            var d = 0.1
            if let props = CGImageSourceCopyPropertiesAtIndex(src, i, nil) as? [CFString: Any],
               let gif = props[kCGImagePropertyGIFDictionary] as? [CFString: Any] {
                let u = gif[kCGImagePropertyGIFUnclampedDelayTime] as? Double ?? 0
                let c = gif[kCGImagePropertyGIFDelayTime] as? Double ?? 0
                d = u > 0.01 ? u : (c > 0.01 ? c : 0.1)
            }
            frames.append(img)
            delays.append(d)
        }
        guard !frames.isEmpty else { return nil }
        lock.lock()
        store[url] = (frames, delays)
        lock.unlock()
        return (frames, delays)
    }
}

struct AnimatedClip: View {
    let url: URL

    var body: some View {
        if let c = ClipCache.shared.clip(url) {
            let total = max(0.1, c.delays.reduce(0, +))
            TimelineView(.animation) { ctx in
                Image(decorative: c.frames[frameIndex(c.delays, t: ctx.date.timeIntervalSinceReferenceDate, total: total)], scale: 1)
                    .resizable()
                    .scaledToFit()
            }
        } else {
            Text("clip unreadable").font(.caption).foregroundColor(.secondary)
        }
    }

    private func frameIndex(_ delays: [Double], t: Double, total: Double) -> Int {
        var x = t.truncatingRemainder(dividingBy: total)
        for (i, d) in delays.enumerated() {
            if x < d { return i }
            x -= d
        }
        return delays.count - 1
    }
}
