// A simple cartoon head (head, ears, eyes, nose, mouth: basic shapes, no assets) that can
//  - demonstrate a motion in a loop (MotionDemo), and
//  - mirror the participant's own head from the AirPods angles (LiveHead).
// Shown as a MIRROR: the participant's left is on the left of the screen.
// Display angles: pitch > 0 = chin down, roll > 0 = head tilts to the screen's right, yaw > 0 = face turns to the
// screen's right. (Signs of the live mirror are to be checked on the Mac; flip them in LiveHead if needed.)

import SwiftUI

struct HeadShape: View {
    var pitch = 0.0, roll = 0.0, yaw = 0.0
    var tint: Color = .orange

    var body: some View {
        ZStack {
            HStack(spacing: 124) {
                Capsule().fill(tint.opacity(0.5)).frame(width: 16, height: 38)
                Capsule().fill(tint.opacity(0.5)).frame(width: 16, height: 38)
            }
            Ellipse().fill(tint.opacity(0.25)).frame(width: 124, height: 154)
                .overlay(Ellipse().stroke(Color.primary.opacity(0.7), lineWidth: 2))
            HStack(spacing: 34) {
                Circle().fill(Color.primary).frame(width: 12, height: 12)
                Circle().fill(Color.primary).frame(width: 12, height: 12)
            }.offset(y: -20)
            Capsule().fill(tint).frame(width: 12, height: 30).offset(y: 8)
            Capsule().fill(Color.primary.opacity(0.7)).frame(width: 38, height: 5).offset(y: 44)
        }
        .rotation3DEffect(.radians(yaw), axis: (x: 0, y: 1, z: 0), perspective: 0.5)
        .rotation3DEffect(.radians(-pitch), axis: (x: 1, y: 0, z: 0), perspective: 0.5)
        .rotationEffect(.radians(roll))
        .frame(width: 230, height: 230)
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
            return (-0.35 * cos(th) * env + 0.0, 0, dir * 0.35 * sin(th) * env)
        default: return (0, 0, 0)
        }
    }

    static func isMotion(_ m: String) -> Bool {
        ["nod_down", "calib_nod", "look_up", "tilt_left", "tilt_right", "turn_left", "turn_right", "circle_cw", "circle_ccw"].contains(m)
    }
}

struct MotionDemo: View {
    var motion: String

    var body: some View {
        TimelineView(.animation) { ctx in
            let a = MotionPose.angles(motion, t: ctx.date.timeIntervalSinceReferenceDate)
            HeadShape(pitch: a.0, roll: a.1, yaw: a.2, tint: .blue)
        }
    }
}

/// The participant's head, live, relative to the pose captured with "Set front".
struct LiveHead: View {
    @ObservedObject var recorder: Recorder
    var reference: HeadAngles

    var body: some View {
        let a = recorder.angles
        HeadShape(pitch: -(a.pitch - reference.pitch), roll: (a.roll - reference.roll), yaw: -(a.yaw - reference.yaw))
    }
}
