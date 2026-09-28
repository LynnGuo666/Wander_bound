import SwiftUI

struct AccountSettingsView: View {
    @EnvironmentObject private var account: AccountSession
    @EnvironmentObject private var store: PlannerStore
    @State private var invite = ""
    @State private var error = ""

    var body: some View {
        Form {
            Section("我的账号") {
                LabeledContent("用户名", value: account.user?.username ?? "")
                LabeledContent("身份", value: account.user?.role == "admin" ? "管理员" : "成员")
                Button("退出登录") { Task { await account.logout(serverURL: store.serverURL); store.clearAccountData() } }
            }
            if account.user?.role == "admin" {
                Section("邀请成员") {
                    Button("生成一次性邀请码") {
                        Task { do { invite = try await account.createInvite(serverURL: store.serverURL) }
                            catch { self.error = error.localizedDescription } }
                    }
                    if !invite.isEmpty { Text(invite).textSelection(.enabled).font(.footnote.monospaced()) }
                    if !error.isEmpty { Text(error).foregroundStyle(.red) }
                }
                Section("高级设置") { NavigationLink("供应商与数据源") { AdvancedSettingsView() } }
            }
            Section("服务") {
                TextField("API 地址", text: $store.serverURL).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                NavigationLink("数据来源状态") { SourcesView() }
            }
        }.navigationTitle("设置")
    }
}

private struct SettingsPayload: Decodable {
    let priorities: [String: [String]]
    let credentials: [String: CredentialStatus]
}
private struct CredentialStatus: Decodable { let configured: Bool }

struct AdvancedSettingsView: View {
    @EnvironmentObject private var store: PlannerStore
    @State private var settings: SettingsPayload?
    @State private var keys: [String: String] = [:]
    @State private var priorities: [String: [String]] = [:]
    @State private var message = ""
    private let providers = ["stepfun", "amap", "dida", "duffel", "tuniu", "flyai"]
    var body: some View {
        Form {
            if settings == nil { ProgressView("正在读取配置…") }
            Section("供应商密钥") {
                ForEach(providers, id: \.self) { id in
                    SecureField("\(id) · \(settings?.credentials[id]?.configured == true ? "已配置" : "未配置")", text: Binding(
                        get: { keys[id] ?? "" }, set: { keys[id] = $0 }))
                }
            }
            ForEach(["flights", "trains", "attractions"], id: \.self) { group in
                Section(group == "flights" ? "航班优先级" : group == "trains" ? "火车优先级" : "景点优先级") {
                    ForEach(Array((priorities[group] ?? []).enumerated()), id: \.element) { index, name in
                        HStack { Text(name); Spacer()
                            Button { move(group, index, -1) } label: { Image(systemName: "arrow.up") }.disabled(index == 0)
                            Button { move(group, index, 1) } label: { Image(systemName: "arrow.down") }.disabled(index == (priorities[group]?.count ?? 0) - 1)
                        }
                    }
                }
            }
            Section {
                Button("保存设置") { Task { await save() } }.disabled(settings == nil)
                if !message.isEmpty { Text(message).font(.footnote) }
            }
        }.navigationTitle("高级设置").task { await load() }
    }
    private func move(_ group: String, _ index: Int, _ offset: Int) {
        guard var items = priorities[group], items.indices.contains(index + offset) else { return }
        items.swapAt(index, index + offset); priorities[group] = items
    }
    private func load() async {
        do { let value: SettingsPayload = try await AppAPI(baseURL: store.serverURL).decode(SettingsPayload.self, path: "/api/settings")
            settings = value; priorities = value.priorities }
        catch { message = error.localizedDescription }
    }
    private func save() async {
        do {
            let body = try JSONSerialization.data(withJSONObject: ["credentials": keys.filter { !$0.value.isEmpty }, "priorities": priorities])
            _ = try await AppAPI(baseURL: store.serverURL).data("/api/settings", method: "PUT", body: body)
            keys = [:]; message = "已保存"; await load()
        } catch { message = error.localizedDescription }
    }
}
