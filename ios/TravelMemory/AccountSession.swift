import SwiftUI

struct AccountUser: Codable {
    let id: String
    let username: String
    let role: String
}

private struct AuthResponse: Decodable {
    let token: String
    let user: AccountUser
}
private struct MeResponse: Decodable { let user: AccountUser }
private struct InviteResponse: Decodable { let invite: String }

@MainActor final class AccountSession: ObservableObject {
    @Published var user: AccountUser?
    @Published var busy = false
    @Published var error = ""
    @Published var checking = true

    func restore(serverURL: String) async {
        defer { checking = false }
        guard !MediaTokenStore.load().isEmpty else { return }
        do { user = try await AppAPI(baseURL: serverURL).decode(MeResponse.self, path: "/api/auth/me").user }
        catch { MediaTokenStore.save("") }
    }

    func authenticate(serverURL: String, username: String, password: String, invite: String?) async {
        busy = true; error = ""
        defer { busy = false }
        do {
            let payload: [String: String] = invite.map { ["username": username, "password": password, "invite": $0] }
                ?? ["username": username, "password": password]
            let body = try JSONSerialization.data(withJSONObject: payload)
            let path = invite == nil ? "/api/auth/login" : "/api/auth/register"
            let data = try await AppAPI(baseURL: serverURL).data(path, method: "POST", token: "", body: body)
            let response = try JSONDecoder().decode(AuthResponse.self, from: data)
            MediaTokenStore.save(response.token)
            user = response.user
        } catch { self.error = error.localizedDescription }
    }

    func logout(serverURL: String) async {
        var request = try? AppAPI(baseURL: serverURL).request("/api/auth/logout", method: "POST")
        request?.timeoutInterval = 5
        MediaTokenStore.save(""); user = nil
        if let request { _ = try? await URLSession.shared.data(for: request) }
    }

    func createInvite(serverURL: String) async throws -> String {
        let data = try await AppAPI(baseURL: serverURL).data("/api/auth/invites", method: "POST")
        return try JSONDecoder().decode(InviteResponse.self, from: data).invite
    }
}

struct AccountGate: View {
    @EnvironmentObject private var account: AccountSession
    @EnvironmentObject private var store: PlannerStore
    @State private var username = ""
    @State private var password = ""
    @State private var invite = ""
    @State private var registering = false
    @State private var showingConnection = false
    @FocusState private var focus: Field?

    private enum Field: Hashable { case username, password, invite }

    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: 0) {
                    brand
                    VStack(alignment: .leading, spacing: 16) {
                        Text(registering ? "创建账号" : "欢迎回来")
                            .font(.title3.weight(.semibold))
                            .frame(maxWidth: .infinity, alignment: .leading)
                        VStack(spacing: 0) {
                            TextField("用户名", text: $username)
                                .textContentType(.username)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                                .focused($focus, equals: .username)
                                .submitLabel(.next)
                                .onSubmit { focus = .password }
                                .padding(16)
                            Divider().padding(.leading, 16)
                            SecureField("密码", text: $password)
                                .textContentType(registering ? .newPassword : .password)
                                .focused($focus, equals: .password)
                                .submitLabel(registering ? .next : .go)
                                .onSubmit { if registering { focus = .invite } else { submit() } }
                                .padding(16)
                            if registering {
                                Divider().padding(.leading, 16)
                                SecureField("邀请码", text: $invite)
                                    .focused($focus, equals: .invite)
                                    .submitLabel(.go)
                                    .onSubmit(submit)
                                    .padding(16)
                            }
                        }
                        .background(Color(uiColor: .secondarySystemGroupedBackground),
                                    in: RoundedRectangle(cornerRadius: 16))
                        if !account.error.isEmpty {
                            Text(account.error).font(.footnote).foregroundStyle(.red)
                                .accessibilityAddTraits(.updatesFrequently)
                        }
                        Button(action: submit) {
                            if account.busy { ProgressView().tint(.white).frame(maxWidth: .infinity) }
                            else { Text(registering ? "创建账号" : "登录").frame(maxWidth: .infinity) }
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(Palette.brandForest)
                        .controlSize(.large)
                        .disabled(account.busy || username.isEmpty || password.isEmpty || (registering && invite.isEmpty))
                        Button(registering ? "已有账号？登录" : "持有邀请码？创建账号") {
                            registering.toggle(); account.error = ""; focus = nil
                        }
                        .font(.subheadline.weight(.medium))
                        .frame(maxWidth: .infinity)
                        .padding(.top, 4)
                    }
                    .padding(.top, 42)
                    DisclosureGroup("连接设置", isExpanded: $showingConnection) {
                        TextField("服务地址", text: $store.serverURL)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .keyboardType(.URL)
                            .textFieldStyle(.roundedBorder)
                            .padding(.top, 12)
                        Text("连接同一 Tailscale 私网后使用 Spark 服务。")
                            .font(.caption).foregroundStyle(Palette.muted)
                    }
                    .font(.footnote)
                    .foregroundStyle(Palette.muted)
                    .padding(.top, 46)
                }
                .frame(maxWidth: 420)
                .padding(.horizontal, 24)
                .frame(maxWidth: .infinity, minHeight: geometry.size.height)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(Palette.canvas)
        }
    }

    private var brand: some View {
        VStack(spacing: 12) {
            Image("BrandMark")
                .resizable()
                .frame(width: 56, height: 56)
                .clipShape(RoundedRectangle(cornerRadius: 13))
                .accessibilityHidden(true)
            Text("行驿")
                .font(.system(size: 34, weight: .semibold, design: .serif))
                .foregroundStyle(Palette.ink)
            Text("把每一次出发，留成故事。")
                .font(.subheadline)
                .foregroundStyle(Palette.muted)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
    }

    private func submit() {
        focus = nil
        Task {
            await account.authenticate(serverURL: store.serverURL, username: username,
                                       password: password, invite: registering ? invite : nil)
        }
    }
}
