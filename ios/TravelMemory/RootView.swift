import SwiftUI

struct RootView: View {
    @EnvironmentObject private var account: AccountSession
    @EnvironmentObject private var store: PlannerStore
    @State private var selection: MainDestination? = .trips

    var body: some View {
        Group {
            if account.checking { ProgressView("正在连接行驿…") }
            else if account.user == nil { AccountGate() }
            else if UIDevice.current.userInterfaceIdiom == .pad { tablet }
            else { main }
        }
        .task { if account.checking { await account.restore(serverURL: store.serverURL); store.activateAccount(account.user?.id) } }
        .onChange(of: account.user?.id) { _, id in store.activateAccount(id) }
    }

    private var tablet: some View {
        NavigationSplitView {
            List(selection: $selection) {
                Label("行程", systemImage: "map").tag(MainDestination.trips)
                Label("旅途", systemImage: "book.closed").tag(MainDestination.journal)
                Label("我的", systemImage: "person.crop.circle").tag(MainDestination.profile)
                Label("设置", systemImage: "gearshape").tag(MainDestination.settings)
            }.navigationTitle("行驿")
        } detail: {
            NavigationStack {
                switch selection ?? .trips {
                case .trips: JourneyView()
                case .journal: JournalView()
                case .profile: MemoryView()
                case .settings: AccountSettingsView()
                }
            }
        }
    }

    private var main: some View {
        TabView {
            NavigationStack { JourneyView() }.tabItem { Label("行程", systemImage: "map") }
            NavigationStack { JournalView() }.tabItem { Label("旅途", systemImage: "book.closed") }
            NavigationStack { MemoryView() }.tabItem { Label("我的", systemImage: "person.crop.circle") }
            NavigationStack { AccountSettingsView() }.tabItem { Label("设置", systemImage: "gearshape") }
        }
    }
}

private enum MainDestination: Hashable {
    case trips, journal, profile, settings
}
