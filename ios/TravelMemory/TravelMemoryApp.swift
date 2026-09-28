import SwiftUI

@main
struct TravelMemoryApp: App {
    @StateObject private var store = PlannerStore()
    @StateObject private var account = AccountSession()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .environmentObject(account)
                .tint(Palette.forest)
        }
    }
}
