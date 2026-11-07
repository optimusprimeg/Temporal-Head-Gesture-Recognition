// Gesture Collector: the CS724 data-collection app (macOS 14+ and iOS 16+, one shared code base), v3.
// Build: bash build.sh (Mac app), bash build_ios.sh (iPhone app, unsigned .ipa for Sideloadly/Xcode).

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
