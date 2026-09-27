import SwiftUI

@main
struct TravelMemoryApp: App {
    @StateObject private var store = PlannerStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .tint(Palette.forest)
        }
    }
}
