// A 3D head (SceneKit, built from basic shapes: head, nose, eyes, ears, mouth; no assets) that can
//  - demonstrate a motion in a loop (MotionDemo, "DO THIS"), and
//  - mirror the participant's own head from the AirPods angles (LiveHead, "YOU").
// Shown as a MIRROR: the participant's left is on the left of the screen.
// Display angles: pitch > 0 = chin down, roll > 0 = head tilts to the screen's right, yaw > 0 = face turns to the
// screen's right. Live mapping from the AirPods attitude (checked on P01's data: nod down lowers pitch, turn left
// raises yaw, tilt left lowers roll); the earbud's own mounting can still bend it a little.

import SceneKit
import SwiftUI
#if os(macOS)
import AppKit
typealias ViewRepresentable = NSViewRepresentable
typealias SCNFloat = CGFloat
#else
import UIKit
typealias ViewRepresentable = UIViewRepresentable
typealias SCNFloat = Float
#endif

struct Head3D: ViewRepresentable {
    var pitch = 0.0, roll = 0.0, yaw = 0.0
    var tint: PlatformColor = .systemOrange

    #if os(macOS)
    func makeNSView(context: Context) -> SCNView { makeView() }
    func updateNSView(_ v: SCNView, context: Context) { update(v) }
    #else
    func makeUIView(context: Context) -> SCNView { makeView() }
    func updateUIView(_ v: SCNView, context: Context) { update(v) }
    #endif

    func makeView() -> SCNView {
        let v = SCNView()
        v.scene = Head3D.makeScene(tint: tint)
        v.backgroundColor = .clear
        v.autoenablesDefaultLighting = true
        v.allowsCameraControl = false
        v.antialiasingMode = .multisampling4X
        v.rendersContinuously = false
        return v
    }

    func update(_ v: SCNView) {
        guard let head = v.scene?.rootNode.childNode(withName: "head", recursively: false) else { return }
        // SceneKit: rotation about +x by +a turns the face (+z, toward the camera) down; about +y by +a turns it to
        // the screen's right; about +z by +a tilts it to the screen's LEFT (counter-clockwise), hence -roll.
        head.eulerAngles = SCNVector3(SCNFloat(pitch), SCNFloat(yaw), SCNFloat(-roll))
    }

    static func makeScene(tint: PlatformColor) -> SCNScene {
        let scene = SCNScene()
        let head = SCNNode()
        head.name = "head"
        func node(_ g: SCNGeometry, _ color: PlatformColor, _ pos: SCNVector3, scale: SCNVector3 = SCNVector3(1, 1, 1)) -> SCNNode {
            g.firstMaterial?.diffuse.contents = color
            let n = SCNNode(geometry: g)
            n.position = pos
            n.scale = scale
            return n
        }
        #if os(macOS)
        let skin = tint.blended(withFraction: 0.55, of: .white) ?? tint
        #else
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        tint.getRed(&r, green: &g, blue: &b, alpha: &a)
        let skin = UIColor(red: r + (1 - r) * 0.55, green: g + (1 - g) * 0.55, blue: b + (1 - b) * 0.55, alpha: a)
        #endif
        head.addChildNode(node(SCNSphere(radius: 1), skin, SCNVector3(0, 0, 0), scale: SCNVector3(0.82, 1.05, 0.92)))
        let nose = node(SCNCone(topRadius: 0, bottomRadius: 0.16, height: 0.42), tint, SCNVector3(0, -0.05, 0.98))
        nose.eulerAngles = SCNVector3(SCNFloat.pi / 2, 0, 0)          // point the cone toward the camera
        head.addChildNode(nose)
        for x in [-0.3, 0.3] {
            head.addChildNode(node(SCNSphere(radius: 0.09), .black, SCNVector3(SCNFloat(x), 0.25, 0.8)))
            head.addChildNode(node(SCNSphere(radius: 0.2), skin, SCNVector3(SCNFloat(x) * 2.75, 0.05, 0),
                                   scale: SCNVector3(0.45, 1.0, 0.8)))   // ears
        }
        head.addChildNode(node(SCNBox(width: 0.42, height: 0.06, length: 0.06, chamferRadius: 0.03),
                               PlatformColor.darkGray, SCNVector3(0, -0.48, 0.8)))
        scene.rootNode.addChildNode(head)
        let cam = SCNNode()
        cam.camera = SCNCamera()
        cam.camera?.fieldOfView = 40
        cam.position = SCNVector3(0, 0, 4.6)
        scene.rootNode.addChildNode(cam)
        return scene
    }
}

enum MotionPose {
    /// Display angles at time t (s) for a motion demo: the motion takes `dur` s, then a pause until the cycle ends.
    static func angles(_ motion: String, t: Double) -> (Double, Double, Double) {
        let cycle = 3.0
        let isCircle = motion.hasPrefix("circle")
        let dur = isCircle ? 2.0 : 1.2
        let u = t.truncatingRemainder(dividingBy: cycle) / dur
        guard u < 1 else { return (0, 0, 0) }
        let bump = sin(Double.pi * u)                  // go and come straight back
        switch motion {
        case "nod_down", "calib_nod": return (0.45 * bump, 0, 0)
        case "look_up": return (-0.45 * bump, 0, 0)
        case "tilt_left": return (0, -0.4 * bump, 0)
        case "tilt_right": return (0, 0.4 * bump, 0)
        case "turn_left": return (0, 0, -0.6 * bump)
        case "turn_right": return (0, 0, 0.6 * bump)
        case "circle_cw", "circle_ccw":
            let th = 2 * Double.pi * u                     // 12 -> 3 -> 6 -> 9 (cw, as the person sees the wall)
            let env = min(1, 5 * u, 5 * (1 - u))           // start and end at the front
            let dir = motion == "circle_cw" ? 1.0 : -1.0
            return (-0.35 * cos(th) * env, 0, dir * 0.35 * sin(th) * env)
        default: return (0, 0, 0)
        }
    }

    static func isMotion(_ m: String) -> Bool {
        let parts = m.split(separator: ",").map { String($0).trimmingCharacters(in: .whitespaces) }
        return !parts.isEmpty && parts.allSatisfy {
            ["nod_down", "calib_nod", "look_up", "tilt_left", "tilt_right", "turn_left", "turn_right", "circle_cw", "circle_ccw"].contains($0)
        }
    }

    /// v3.3: "tilt_left,tilt_left" = the parts one after another (0.9 s each, circles 2 s), then a pause.
    static func sequenceAngles(_ m: String, t: Double) -> (Double, Double, Double) {
        let parts = m.split(separator: ",").map { String($0).trimmingCharacters(in: .whitespaces) }
        guard parts.count > 1 else { return angles(m, t: t) }
        let lens = parts.map { $0.hasPrefix("circle") ? 2.0 : 0.9 }
        let total = lens.reduce(0, +) + 1.5
        var x = t.truncatingRemainder(dividingBy: total)
        for (p, l) in zip(parts, lens) {
            if x < l {
                let dur = p.hasPrefix("circle") ? 2.0 : 1.2      // angles() plays one motion in `dur` of a 3 s cycle
                return angles(p, t: x / l * dur)
            }
            x -= l
        }
        return (0, 0, 0)
    }
}

struct MotionDemo: View {
    var motion: String

    var body: some View {
        TimelineView(.animation) { ctx in
            let a = MotionPose.sequenceAngles(motion, t: ctx.date.timeIntervalSinceReferenceDate)
            Head3D(pitch: a.0, roll: a.1, yaw: a.2, tint: .systemBlue)
        }
    }
}

/// The participant's head, live, relative to the pose captured with "Set front".
struct LiveHead: View {
    @ObservedObject var recorder: Recorder
    var reference: HeadAngles

    var body: some View {
        let a = recorder.angles
        Head3D(pitch: -(a.pitch - reference.pitch), roll: a.roll - reference.roll, yaw: -(a.yaw - reference.yaw),
               tint: .systemOrange)
    }
}

/// "DO THIS" (demo) and "YOU" (live) side by side.
struct TwoHeads: View {
    var motion: String
    @ObservedObject var recorder: Recorder
    var reference: HeadAngles
    var clip: URL? = nil              // v3.3: experiments/media/<id>.gif, shown instead of the 3D demo when present

    var body: some View {
        HStack(spacing: 16) {
            VStack {
                Text("DO THIS").font(.headline).foregroundColor(.blue)
                if let c = clip, FileManager.default.fileExists(atPath: c.path) { AnimatedClip(url: c) }
                else if MotionPose.isMotion(motion) { MotionDemo(motion: motion) } else { Head3D(tint: .systemBlue) }
            }.frame(width: Platform.isPhone ? 150 : 230, height: Platform.isPhone ? 180 : 260)
            VStack {
                Text("YOU").font(.headline).foregroundColor(.orange)
                LiveHead(recorder: recorder, reference: reference)
            }.frame(width: Platform.isPhone ? 150 : 230, height: Platform.isPhone ? 180 : 260)
        }
    }
}
