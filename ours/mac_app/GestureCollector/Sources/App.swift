// Gesture Collector (macOS 14+): the CS724 data-collection app, v2.0 (APP_V2_PLAN.md, build step 1).
// Build: bash build.sh

import SwiftUI

@main
struct GestureCollectorApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup("Gesture Collector") {
            RootView()
                .environmentObject(model)
                .environmentObject(model.roster)
                .environmentObject(model.recorder)
        }
    }
}
