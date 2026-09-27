import SwiftUI

struct RootView: View {
    var body: some View {
        TabView {
            NavigationStack { PlanView() }
                .tabItem { Label("规划", systemImage: "sparkles") }
            NavigationStack { MemoryView() }
                .tabItem { Label("记忆", systemImage: "heart.text.square") }
            NavigationStack { SourcesView() }
                .tabItem { Label("来源", systemImage: "square.stack.3d.up") }
        }
    }
}
