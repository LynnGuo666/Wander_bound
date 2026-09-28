import AVKit
import SwiftUI

private struct WorkList: Decodable { let works: [JournalWork] }
private struct JournalWork: Decodable, Identifiable {
    let id: String
    let kind: String
    let status: String
    let title: String?
    let progressLabel: String?
    let error: String?
}
private struct StyleList: Decodable { let styles: [ScrapbookStyle] }
private struct ScrapbookStyle: Decodable, Identifiable {
    let id: String
    let name: String
}
private struct SelectionList: Decodable { let photoIds: [String] }

private struct PrivatePhoto: View {
    let id: String
    let client: MediaClient
    @State private var image: UIImage?

    var body: some View {
        Group {
            if let image { Image(uiImage: image).resizable().scaledToFill() }
            else { Rectangle().fill(Palette.pale).overlay(ProgressView()) }
        }
        .frame(height: 120)
        .clipped()
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .task(id: id) { if let data = try? await client.image(id) { image = UIImage(data: data) } }
    }
}

struct JournalView: View {
    @EnvironmentObject private var store: PlannerStore
    @State private var mode = "timeline"
    @State private var city = ""

    private var allTrips: [TripRecord] {
        store.trips.filter { $0.plan != nil || $0.status == "ended" }
            .sorted { ($0.plan?.startDate ?? $0.createdAt ?? "") > ($1.plan?.startDate ?? $1.createdAt ?? "") }
    }
    private var trips: [TripRecord] {
        switch mode {
        case "city": return allTrips.filter { $0.plan?.destination == city }
        case "today":
            let monthDay = String(Date().formatted(.iso8601.year().month().day()).suffix(5))
            return allTrips.filter { ($0.plan?.startDate ?? "").hasSuffix(monthDay) }
        default: return allTrips
        }
    }

    var body: some View {
        List {
            Section {
                Picker("翻阅方式", selection: $mode) {
                    Text("时间线").tag("timeline")
                    Text("往年今日").tag("today")
                    Text("同城").tag("city")
                }.pickerStyle(.segmented)
                if mode == "city" {
                    Picker("城市", selection: $city) {
                        ForEach(Array(Set(allTrips.compactMap { $0.plan?.destination })).sorted(), id: \.self) {
                            Text($0).tag($0)
                        }
                    }
                }
            }
            Section("旅途故事") {
                if trips.isEmpty {
                    ContentUnavailableView("还没有可以翻阅的旅途", systemImage: "book.closed",
                                           description: Text("行程和照片会在这里组成你的时间线。"))
                        .frame(maxWidth: .infinity)
                        .listRowBackground(Color.clear)
                }
                ForEach(trips) { trip in
                    NavigationLink {
                        JournalDetailView(tripId: trip.id)
                    } label: {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(trip.plan?.destination ?? trip.title).font(.headline)
                            Text(trip.plan.map { "\($0.startDate) — \($0.endDate)" } ?? "旅行故事")
                                .font(.subheadline).foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 5)
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(Palette.canvas)
        .navigationTitle("旅途")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    if let random = allTrips.randomElement() { selectedTrip = random.id }
                } label: { Label("随机一页", systemImage: "shuffle") }
                    .disabled(allTrips.isEmpty)
            }
        }
        .refreshable { await store.refreshTrips() }
        .task { await store.refreshTrips(); city = allTrips.first?.plan?.destination ?? "" }
        .navigationDestination(item: $selectedTrip) { JournalDetailView(tripId: $0) }
    }

    @State private var selectedTrip: String?
}

struct JournalDetailView: View {
    let tripId: String
    @EnvironmentObject private var store: PlannerStore
    @State private var trip: TripRecord?
    @State private var note = ""
    @State private var version = 0
    @State private var works: [JournalWork] = []
    @State private var styles: [ScrapbookStyle] = []
    @State private var selected: Set<String> = []
    @State private var chosenPhoto = ""
    @State private var chosenStyle = "watercolor"
    @State private var title = ""
    @State private var notice = ""
    @State private var player: AVPlayer?

    private var token: String { MediaTokenStore.load() }
    private var api: AppAPI { AppAPI(baseURL: store.serverURL) }
    private var client: MediaClient { MediaClient(serverURL: store.serverURL, token: token) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 17) {
                Text(trip?.plan?.destination ?? trip?.title ?? "旅途")
                    .font(.system(.largeTitle, design: .serif, weight: .semibold))
                Text(trip?.plan.map { "\($0.startDate) — \($0.endDate)" } ?? "")
                    .font(.caption).foregroundStyle(Palette.muted)
                if token.isEmpty { ContentUnavailableView("请重新登录", systemImage: "person.crop.circle.badge.exclamationmark", description: Text("登录后可查看照片、作品和同步日记。")) }
                else {
                    Surface {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("写给这段旅程").font(.system(.title2, design: .serif))
                            TextEditor(text: $note).frame(minHeight: 130)
                                .accessibilityLabel("旅行日记")
                            Button("保存日记") { Task { await saveNote() } }
                        }
                    }
                    NavigationLink { MediaView(tripId: tripId) } label: {
                        Label("选择照片、上传与分析", systemImage: "photo.on.rectangle.angled")
                    }.buttonStyle(.borderedProminent).tint(Palette.brandForest)
                    if let photos = trip?.photos, !photos.isEmpty {
                        Text("沿途的画面").font(.headline)
                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())]) {
                            ForEach(photos) { photo in
                                VStack(alignment: .leading) {
                                    PrivatePhoto(id: photo.id, client: client)
                                    Toggle(photo.capturedDay ?? "旅途片刻", isOn: Binding(
                                        get: { selected.contains(photo.id) },
                                        set: { if $0 { selected.insert(photo.id) } else { selected.remove(photo.id) } }))
                                        .font(.caption)
                                }
                            }
                        }
                        Button("保存精选照片") { Task { await saveSelection() } }
                            .buttonStyle(.bordered)
                        Surface {
                            VStack(alignment: .leading, spacing: 10) {
                                Text("制作手账").font(.headline)
                                Picker("照片", selection: $chosenPhoto) {
                                    ForEach(photos) { photo in Text(photo.capturedDay ?? photo.id).tag(photo.id) }
                                }
                                Picker("风格", selection: $chosenStyle) {
                                    ForEach(styles) { Text($0.name).tag($0.id) }
                                }
                                TextField("标题（可选）", text: $title)
                                Button("开始制作") { Task { await createScrapbook() } }
                                    .disabled(!selected.contains(chosenPhoto))
                            }
                        }
                    }
                    if !works.isEmpty {
                        Text("旅途作品").font(.headline)
                        ForEach(works) { work in
                            Surface {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text(work.title ?? (work.kind == "memory" ? "回忆短片" : "风格手账")).font(.headline)
                                    Text(work.status == "succeeded" ? "已完成" : work.progressLabel ?? work.status)
                                        .font(.caption).foregroundStyle(Palette.muted)
                                    if work.status == "succeeded", work.kind == "memory" {
                                        Button("播放短片") { Task { await play(work.id) } }
                                    } else if work.status == "succeeded" {
                                        PrivateWorkImage(id: work.id, client: client)
                                    }
                                    if let error = work.error { Text(error).font(.caption).foregroundStyle(.red) }
                                }
                            }
                        }
                    }
                    if let player { VideoPlayer(player: player).frame(height: 230) }
                }
                if !notice.isEmpty { Text(notice).font(.caption).foregroundStyle(Palette.forest) }
            }.padding(18)
        }
        .background(Palette.canvas)
        .navigationTitle("旅途手账")
        .task(id: tripId) { await load() }
    }

    private func load() async {
        guard !token.isEmpty else { return }
        do {
            trip = try await api.decode(TripRecord.self, path: "/api/trips/\(tripId)", token: token)
            let journal: JournalNote = try await api.decode(JournalNote.self, path: "/api/trips/\(tripId)/note", token: token)
            note = journal.text; version = journal.version
            let selection: SelectionList = try await api.decode(SelectionList.self, path: "/api/media/trips/\(tripId)/selected-photos", token: token)
            selected = Set(selection.photoIds)
            let catalog: StyleList = try await api.decode(StyleList.self, path: "/api/media/scrapbook-styles", token: token)
            styles = catalog.styles; chosenStyle = styles.first?.id ?? "watercolor"
            chosenPhoto = trip?.photos?.first?.id ?? ""
            await refreshWorks()
        } catch { notice = error.localizedDescription }
    }

    private func saveNote() async {
        do {
            let body = try JSONSerialization.data(withJSONObject: ["text": note, "version": version])
            let data = try await api.data("/api/trips/\(tripId)/note", method: "PUT", token: token, body: body)
            let saved = try JSONDecoder().decode(JournalNote.self, from: data)
            version = saved.version; notice = "日记已同步"
        } catch { notice = "日记未保存：\(error.localizedDescription)" }
    }

    private func saveSelection() async {
        do {
            let ids = (trip?.photos ?? []).map(\.id).filter { selected.contains($0) }
            let body = try JSONSerialization.data(withJSONObject: ["photoIds": ids, "batchId": UUID().uuidString, "source": "ios-journal"])
            _ = try await api.data("/api/media/trips/\(tripId)/selected-photos", method: "PUT", token: token, body: body)
            notice = "精选照片已保存"
        } catch { notice = error.localizedDescription }
    }

    private func createScrapbook() async {
        do {
            let body = try JSONSerialization.data(withJSONObject: ["tripId": tripId, "photoId": chosenPhoto, "styleId": chosenStyle, "title": title])
            _ = try await api.data("/api/media/scrapbooks", method: "POST", token: token, body: body)
            notice = "手账已开始制作"; await refreshWorks()
        } catch { notice = error.localizedDescription }
    }

    private func refreshWorks() async {
        if let list: WorkList = try? await api.decode(WorkList.self, path: "/api/media/trips/\(tripId)/works", token: token) {
            works = list.works
        }
    }

    private func play(_ id: String) async {
        do { player = AVPlayer(url: try await client.memoryVideo(id)); player?.play() }
        catch { notice = error.localizedDescription }
    }
}

private struct PrivateWorkImage: View {
    let id: String
    let client: MediaClient
    @State private var image: UIImage?
    var body: some View {
        Group {
            if let image { Image(uiImage: image).resizable().scaledToFit() }
            else { ProgressView() }
        }
        .frame(maxHeight: 240)
        .task(id: id) {
            let api = AppAPI(baseURL: client.serverURL)
            if let data = try? await api.data("/api/media/generation-jobs/\(id)/image", token: client.token) {
                image = UIImage(data: data)
            }
        }
    }
}
