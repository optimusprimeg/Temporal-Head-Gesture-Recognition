// Screens: start (participant + time) -> device check (live head) -> plan review -> run -> done.

import AppKit
import SwiftUI

struct RootView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        Group {
            switch model.screen {
            case .start: StartView()
            case .check: CheckView()
            case .review: ReviewView()
            case .run: if let r = model.runner { RunView(runner: r) } else { StartView() }
            case .done: DoneView()
            case .live: if let l = model.live { LiveView(live: l) } else { StartView() }
            }
        }
        .padding(20)
        .frame(minWidth: 900, minHeight: 680)
    }
}

// ---------------------------------------------------------------------------------------------------- start
struct StartView: View {
    @EnvironmentObject var model: AppModel
    @EnvironmentObject var roster: RosterStore
    @State private var firstName = ""
    @State private var age = "18-24"
    @State private var hand = "right"
    @State private var glasses = false
    @State private var wear = ""
    @State private var consent = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text("Gesture Collector").font(.largeTitle).bold()
                    Spacer()
                    Text("v\(APP_VERSION)").foregroundColor(.secondary)
                }
                HStack {
                    Text("Data folder: \(model.dataRoot.path)").font(.caption).textSelection(.enabled)
                    Button("Change...") { model.chooseDataRoot() }
                    Button("Open") { NSWorkspace.shared.open(model.dataRoot) }
                }
                Text("Plan: \(model.planSource)").font(.caption).foregroundColor(.secondary)
                HStack {
                    Button("Live recognizer: try commands") { model.openLive() }
                    Text("Recognises commands from the AirPods in real time (Rules or Model). Not part of a session.")
                        .font(.caption).foregroundColor(.secondary)
                }

                let res = model.resumable
                if !res.isEmpty {
                    GroupBox("Unfinished sessions (app was closed or crashed)") {
                        ForEach(Array(res.enumerated()), id: \.offset) { pair in
                            let item = pair.element
                            HStack {
                                Text("\(item.1.meta.firstName) \(item.1.meta.session) on \(item.1.meta.device): step \(item.1.index) of \(item.1.steps.count)")
                                Spacer()
                                Button("Resume") { model.resume(item.0, item.1) }
                                Button("Close as incomplete") { model.closeResumable(item.0, item.1) }
                            }
                        }
                    }
                }

                GroupBox("New participant") {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            TextField("First name only", text: $firstName).frame(width: 220)
                            Text("will be \(String(format: "P%02d", roster.nextNumber))").foregroundColor(.secondary)
                        }
                        HStack {
                            Picker("Age", selection: $age) {
                                ForEach(["under 18", "18-24", "25-34", "35-49", "50+"], id: \.self) { Text($0) }
                            }.frame(width: 180)
                            Picker("Hand", selection: $hand) {
                                ForEach(["right", "left", "both"], id: \.self) { Text($0) }
                            }.frame(width: 160)
                            Toggle("Glasses", isOn: $glasses)
                        }
                        TextField("How they usually wear AirPods (optional)", text: $wear)
                        Toggle("Consent: we record head motion only (no audio/video), stored with your first name and participant number for the CS724 project.", isOn: $consent)
                        Button("Add participant") {
                            model.addParticipant(firstName: firstName, profile: ["age": age, "hand": hand,
                                                 "glasses": glasses ? "yes" : "no", "wear": wear, "consent": "yes"])
                            firstName = ""; wear = ""; consent = false
                        }.disabled(!consent || firstName.trimmingCharacters(in: .whitespaces).isEmpty)
                    }.padding(6)
                }

                GroupBox("Session") {
                    VStack(alignment: .leading, spacing: 8) {
                        Picker("Participant", selection: Binding(get: { model.participantNumber ?? 0 },
                                                                 set: { model.select($0 == 0 ? nil : $0) })) {
                            Text("choose...").tag(0)
                            ForEach(roster.roster.participants) { p in
                                Text("\(p.firstName) (\(p.code))").tag(p.number)
                            }
                        }.frame(width: 360)
                        if let p = model.participant {
                            Text(p.summary).font(.caption).foregroundColor(.secondary)
                            Picker("AirPods", selection: $model.device) {
                                ForEach(AppModel.devices, id: \.self) { Text($0) }
                            }.frame(width: 360)
                            Text("Suggested for \(p.code) by the crossover order. Change only if that model is not available (it is logged).")
                                .font(.caption).foregroundColor(.secondary)
                            HStack {
                                Text("Time available:")
                                Stepper(value: $model.budgetMin, in: 15...120, step: 5) {
                                    Text("\(Int(model.budgetMin)) min")
                                }
                            }
                            Button("Next: check the AirPods") { model.screen = .check }
                        }
                    }.padding(6)
                }
                if !model.message.isEmpty { Text(model.message).foregroundColor(.red) }
            }
        }
    }
}

// ---------------------------------------------------------------------------------------------------- check
struct CheckView: View {
    @EnvironmentObject var model: AppModel
    @EnvironmentObject var rec: Recorder

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Device check").font(.title).bold().onAppear { model.detectAirPods() }
            CheckLine(ok: rec.rateHz > 20, text: String(format: "Rate %.0f Hz (50, or 25 on some models)", rec.rateHz))
            CheckLine(ok: abs(rec.gravityNorm - 9.81) < 0.5, text: String(format: "|g| %.2f m/s² (about 9.81)", rec.gravityNorm))
            CheckLine(ok: rec.location != "-", text: "Streaming earbud: \(rec.location)")
            if let n = model.detected["name"] {
                Text("macOS sees: \(n)  (product \(model.detected["productID"] ?? "?"), firmware \(model.detected["firmware"] ?? "?")). Saved with the session; check it matches \"\(model.device)\".")
                    .font(.caption)
            } else if let e = model.detected["error"] {
                Text("Model detection: \(e)").font(.caption).foregroundColor(.secondary)
            }
            Text(rec.status).foregroundColor(rec.healthy ? .green : .orange)
            HStack(alignment: .top, spacing: 30) {
                VStack {
                    LiveHead(recorder: rec, reference: model.reference).frame(width: 240, height: 240)
                    Button("Set front (look straight ahead, then click)") { model.reference = rec.angles }
                }
                Text("Ask the participant to nod, tilt and turn: the head should follow.\n\nKeep BOTH AirPods in for the whole session. If one comes out, the stream moves to the other bud and the app will ask for a new calibration.")
                    .frame(width: 360, alignment: .leading)
            }
            Spacer()
            HStack {
                Button("Back") { model.screen = .start }
                Spacer()
                if !rec.healthy { Text("Not ready yet").foregroundColor(.orange) }
                Button("Continue anyway") { model.makePreview() }.disabled(rec.healthy)
                Button("Next: plan") { model.makePreview() }.disabled(!rec.healthy).keyboardShortcut(.defaultAction)
            }
        }
    }
}

struct CheckLine: View {
    var ok: Bool
    var text: String
    var body: some View {
        Label(text, systemImage: ok ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
            .foregroundColor(ok ? .green : .orange)
    }
}

// ---------------------------------------------------------------------------------------------------- review
struct ReviewView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Session plan").font(.title).bold()
            if let p = model.participant, let pv = model.preview {
                Text("\(p.firstName) (\(p.code)), session \(p.sessions.count + 1), \(model.device), \(Int(model.budgetMin)) min available")
                let t = model.plan.timing
                List {
                    Section("Always") {
                        Text("Calibration + practice  (\(model.minutes(Planner.estimate(pv.steps.filter { $0.module == "setup" }, t))))")
                    }
                    Section("Core (everyone, once per AirPods model)") {
                        if pv.coreBlocks.isEmpty { Text("already done on this model") }
                        ForEach(pv.coreBlocks, id: \.self) { id in
                            Text("\(model.plan.core.first { $0.id == id }?.title ?? id)  (\(model.minutes(Planner.estimate(pv.steps.filter { $0.block == id }, t))))")
                        }
                    }
                    Section("Optional modules, in this person's order") {
                        if pv.modules.isEmpty { Text("none fit in the time (or all done)") }
                        ForEach(pv.modules, id: \.self) { id in
                            let m = model.plan.modules.first { $0.id == id }
                            Text("\(id). \(m?.title ?? "") (tests \(m?.tests ?? ""))  (\(model.minutes(Planner.estimate(pv.steps.filter { $0.module == id }, t))))")
                        }
                        if pv.fillerRounds > 0 { Text("G. \(pv.fillerRounds) extra sitting round(s) to fill the time") }
                    }
                }.frame(minHeight: 300)
                Text("Estimated total: \(model.minutes(pv.estimateS)) (+ breaks). Modules are never cut in the middle.")
                ForEach(pv.warnings, id: \.self) { Text($0).foregroundColor(.orange) }
            }
            HStack {
                Button("Back") { model.screen = .check }
                Spacer()
                Button("Start session") { model.startSession() }.keyboardShortcut(.defaultAction)
            }
        }
    }
}

// ---------------------------------------------------------------------------------------------------- run
struct RunView: View {
    @EnvironmentObject var model: AppModel
    @EnvironmentObject var rec: Recorder
    @ObservedObject var runner: SessionRunner
    @State private var noteText = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                ProgressView(value: runner.progress).frame(maxWidth: .infinity)
                Text("about \(model.minutes(runner.remainingS)) left").font(.caption)
            }
            if !runner.banner.isEmpty {
                Text(runner.banner).foregroundColor(.white).padding(8).background(Color.orange).cornerRadius(6)
            }
            HStack(alignment: .center, spacing: 30) {
                VStack(alignment: .leading, spacing: 12) {
                    Text(runner.title).font(.system(size: 34, weight: .bold)).fixedSize(horizontal: false, vertical: true)
                    Text(runner.sub).font(.title3).fixedSize(horizontal: false, vertical: true)
                    if runner.countdown > 0 { Text(String(format: "%.1f s", runner.countdown)).font(.title2).monospacedDigit() }
                    if !runner.feedback.isEmpty {
                        Text(runner.feedback).font(.title2.bold())
                            .foregroundColor(runner.feedbackOK ? .green : .orange)
                    }
                }
                Spacer()
                TwoHeads(motion: runner.motion, recorder: rec, reference: model.reference)
            }
            Button("Set front (look straight ahead, then click)") { model.reference = rec.angles }.font(.caption)
            Spacer()
            switch runner.phase {
            case .waitingContinue:
                Button("Continue") { runner.pressContinue() }.keyboardShortcut(.defaultAction).controlSize(.large)
            case .waitingDone:
                Button("Done") { runner.pressContinue() }.keyboardShortcut(.defaultAction).controlSize(.large)
            default:
                EmptyView()
            }
            Divider()
            HStack {
                Text("\(rec.status) | \(Int(rec.rateHz)) Hz | earbud \(rec.location) | \(rec.segmentSamples) samples in this segment")
                    .font(.caption).foregroundColor(rec.healthy ? .secondary : .orange)
                Spacer()
            }
            GroupBox("Experimenter") {
                HStack {
                    Button(runner.phase == .paused ? "Resume" : "Pause after this step") { runner.togglePause() }
                    Button("Skip this step") { runner.skip() }
                    Button("Calibrate again") { runner.requestRecalibration() }
                    TextField("note", text: $noteText).frame(width: 220)
                    Button("Add note") { runner.note("note: " + noteText); noteText = "" }.disabled(noteText.isEmpty)
                    Spacer()
                    Button("End session") { runner.stop() }.foregroundColor(.red)
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------------------------------- done
struct DoneView: View {
    @EnvironmentObject var model: AppModel
    @State private var zipPath = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let m = model.lastMeta {
                Text(m.status == "complete" ? "Session complete" : "Session saved (incomplete)").font(.title).bold()
                Text("\(m.firstName), \(m.session) on \(m.device)")
                Text("Core blocks done: " + (m.coreBlocksDone.isEmpty ? "none" : m.coreBlocksDone.joined(separator: ", ")))
                Text("Modules done: " + (m.modulesDone.isEmpty ? "none" : m.modulesDone.joined(separator: ", ")))
                Text("Earbud switches: \(m.earbudSwitches), data gaps: \(m.gaps), segments: \(m.segments)")
                if m.status != "complete" {
                    Text("Unfinished parts will be planned again next time this person is chosen (a module is always redone whole).")
                        .foregroundColor(.secondary)
                }
            }
            HStack {
                if let r = model.runner {
                    Button("Show folder") { NSWorkspace.shared.activateFileViewerSelecting([r.folder]) }
                    Button("Export zip (AirDrop / WhatsApp / pen drive)") {
                        if let z = r.exportZip() {
                            zipPath = z.path
                            NSWorkspace.shared.activateFileViewerSelecting([z])
                        } else { zipPath = "zip failed" }
                    }
                }
            }
            if !zipPath.isEmpty { Text(zipPath).font(.caption).textSelection(.enabled) }
            Spacer()
            Button("Back to start") { model.backToStart() }.keyboardShortcut(.defaultAction)
        }
    }
}
