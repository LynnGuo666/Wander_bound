import SwiftUI
import MapKit

private struct CreatedHistory: Decodable { let id: String; let title: String }
private struct HistoryEvent: Decodable, Identifiable {
    let id: String
    let label: String
    let date: String
    let observedAt: String?
    let source: String
    let confidence: String
    let photoIds: [String]
    let note: String?
    let coordinate: Coordinates?
}
private struct HistoryDay: Decodable { let date: String; let events: [HistoryEvent] }
private struct PossibleCity: Decodable { let name: String; let reason: String? }
private struct JourneyCity: Decodable { let name: String; let role: String }
private struct JourneyLeg: Decodable { let date: String; let from: String; let to: String; let mode: String; let confidence: String }
private struct JourneyHypothesis: Decodable {
    let summary: String
    let status: String
    let cities: [JourneyCity]
    let legs: [JourneyLeg]
    let unknowns: [String]
}
private struct HistoryDraft: Decodable {
    let days: [HistoryDay]
    let status: String
    let notice: String?
    let possibleCity: PossibleCity?
    let journeyHypothesis: JourneyHypothesis?
}
private struct HistoryDetail: Decodable { let id: String; let title: String; let history: HistoryDraft? }
private struct HistoryChatResponse: Decodable { let reply: String; let history: HistoryDraft }

struct HistoryDiscoveryView: View {
    @EnvironmentObject private var account: AccountSession
    @EnvironmentObject private var store: PlannerStore
    @StateObject private var library = TripPhotoLibrary()
    @StateObject private var queue = PhotoUploadQueue()
    @State private var title = "过往旅行"
    @State private var activeId: String?
    @State private var progress = ""
    @State private var busy = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 15) {
                Text("从照片发现旅行").font(.title2.bold())
                Text("先在 iPhone 上扫描获准访问的照片时间与位置。选定一段旅行后，才会上传该段照片到私有 Spark。")
                    .font(.caption).foregroundStyle(.secondary)
                TextField("常居住地，例如长春", text: $store.memory.homeCity)
                    .textFieldStyle(.roundedBorder)
                Button(library.scanning ? "暂停扫描" : "扫描全部已授权相册") {
                    if library.scanning { library.cancelScan() }
                    else { Task { await library.scanAllAuthorized(homeCity: store.memory.homeCity) } }
                }.buttonStyle(.borderedProminent)
                if library.scanning { ProgressView(value: library.scanProgress) }
                Text(library.permissionNote).font(.caption)
                TextField("旅行名称", text: $title).textFieldStyle(.roundedBorder)
                ForEach(library.candidates) { candidate in
                    Surface {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("\(candidate.firstDay) — \(candidate.lastDay)").font(.headline)
                            Text("约 \(candidate.assetIds.count) 张照片，\(candidate.locationCount) 张带位置；需确认是否为同一趟旅行。")
                                .font(.caption).foregroundStyle(.secondary)
                            if candidate.id.hasPrefix("date-") {
                                Text("没有位置证据：仅按拍摄日期分组，不能判断是否真的旅行。")
                                    .font(.caption).foregroundStyle(.orange)
                            }
                            Button("以此生成可能行程") { Task { await create(candidate) } }
                                .disabled(busy || MediaTokenStore.load().isEmpty)
                            HStack {
                                Button("与下一段合并") { library.mergeWithNext(candidate) }
                                Button("按日期拆分") { library.split(candidate) }
                                Button("排除") { library.exclude(candidate) }
                            }.font(.caption).buttonStyle(.borderless)
                        }
                    }
                }
                if busy { ProgressView(); Text(progress).font(.caption) }
                if !queue.failed.isEmpty { Text("部分照片上传失败，可稍后在旅行相册重试。") .font(.caption).foregroundStyle(.red) }
                if let activeId { NavigationLink("查看并完善行程草稿", destination: HistoryDetailView(tripId: activeId)) }
            }.padding(18)
        }
        .navigationTitle("找回旅程")
    }

    private func create(_ candidate: TravelCandidate) async {
        busy = true
        defer { busy = false }
        let api = AppAPI(baseURL: store.serverURL)
        let client = MediaClient(serverURL: store.serverURL, token: MediaTokenStore.load())
        do {
            let payload = try JSONSerialization.data(withJSONObject: [
                "title": title.isEmpty ? "过往旅行" : title,
                "homeCity": store.memory.homeCity.trimmingCharacters(in: .whitespacesAndNewlines)
            ])
            let created = try JSONDecoder().decode(CreatedHistory.self,
                from: await api.data("/api/history/trips", method: "POST", body: payload))
            activeId = created.id
            let all = library.photos(for: candidate).sorted { ($0.asset.creationDate ?? .distantPast) < ($1.asset.creationDate ?? .distantPast) }
            for (index, photo) in all.enumerated() {
                progress = "准备照片 \(index + 1)/\(all.count)"
                do {
                    let data = try await library.uploadJPEG(for: photo)
                    try queue.enqueue(data, ownerId: account.user?.id ?? "", tripId: created.id, assetKey: photo.id, capturedDay: photo.capturedDay)
                } catch { progress = "跳过一张无法读取的照片：\(error.localizedDescription)" }
            }
            progress = "正在上传所选照片到私有 Spark…"
            await queue.uploadAll(client: client, ownerId: account.user?.id ?? "", tripId: created.id)
            let photos = try await client.photos(tripId: created.id)
            if !photos.isEmpty {
                progress = "正在私有模型中分析照片，随后生成草稿…"
                var job = try await client.createAnalysis(tripId: created.id, photoIds: photos.map(\.id), purpose: "history")
                while job.status == "queued" || job.status == "running" {
                    try await Task.sleep(for: .seconds(5))
                    job = try await client.analysisStatus(job.id)
                    progress = "已分析 \(job.completed)/\(job.total) 张"
                }
                _ = try await api.data("/api/history/trips/\(created.id)/reconstruct", method: "POST")
                progress = job.status == "succeeded" ? "草稿已生成，可对话补充。" : "已根据元数据生成草稿；视觉分析可稍后重试。"
                await store.refreshTrips()
            }
        } catch { progress = "生成未完成：\(error.localizedDescription)。已创建的旅行可在行程列表继续。" }
    }
}

struct HistoryDetailView: View {
    let tripId: String
    @EnvironmentObject private var store: PlannerStore
    @State private var detail: HistoryDetail?
    @State private var message = ""
    @State private var reply = ""
    @State private var error = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text(detail?.title ?? "过往旅行").font(.title2.bold())
                if let city = detail?.history?.possibleCity {
                    Text("可能去过：\(city.name) · AI 推断 · \(city.reason ?? "需要你确认")")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if let hypothesis = detail?.history?.journeyHypothesis {
                    Surface {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("可能的行程").font(.headline)
                            Text(hypothesis.summary)
                            if !hypothesis.cities.isEmpty {
                                Text(hypothesis.cities.map { "\($0.name)（\($0.role)）" }.joined(separator: " → "))
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            ForEach(Array(hypothesis.legs.enumerated()), id: \.offset) { _, leg in
                                Text("\(leg.date) · \(leg.from) → \(leg.to) · \(leg.mode) · \(leg.confidence)")
                                    .font(.caption)
                            }
                            if !hypothesis.unknowns.isEmpty {
                                Text("待确认：\(hypothesis.unknowns.joined(separator: "、"))")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                Text(detail?.history?.notice ?? "照片记录的是观测点，旅途中间的路线仍需补充。")
                    .font(.caption).foregroundStyle(.secondary)
                if let days = detail?.history?.days, days.contains(where: { $0.events.contains(where: { $0.coordinate != nil }) }) {
                    Map {
                        ForEach(days, id: \.date) { day in
                            ForEach(day.events) { event in
                                if let point = event.coordinate {
                                    Annotation(event.label, coordinate: CLLocationCoordinate2D(latitude: point.lat, longitude: point.lng)) {
                                        Image(systemName: "camera.fill").padding(7).background(.white, in: Circle())
                                    }
                                }
                            }
                            let points = day.events.compactMap(\.coordinate)
                            if points.count > 1 {
                                MapPolyline(coordinates: points.map { CLLocationCoordinate2D(latitude: $0.lat, longitude: $0.lng) })
                                    .stroke(Palette.muted, lineWidth: 2)
                            }
                        }
                    }
                    .frame(height: 240)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                    Text("地图连线仅表示照片拍摄顺序，并非实际路线。")
                        .font(.caption2).foregroundStyle(.secondary)
                }
                ForEach(detail?.history?.days ?? [], id: \.date) { day in
                    Surface {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(day.date).font(.headline)
                            ForEach(day.events) { event in
                                VStack(alignment: .leading) {
                                    Text(event.label)
                                    Text("\(event.observedAt ?? "时间未知") · \(event.source == "user_confirmed" ? "你已确认" : event.source == "photo_evidence" ? "照片线索" : "待分析")")
                                        .font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
                TextField("例如：这天先去酒店，西湖是第二天去的", text: $message, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                Button("发送补充") { Task { await chat() } }.disabled(message.isEmpty)
                if !reply.isEmpty { Text(reply).font(.caption) }
                HStack {
                    Button("撤销上次修订") { Task { await mutate("undo") } }
                    Button("确认这份行程") { Task { await mutate("confirm") } }
                }.buttonStyle(.bordered)
                if !error.isEmpty { Text(error).foregroundStyle(.red) }
            }.padding(18)
        }
        .navigationTitle("行程还原")
        .task { await refresh() }
    }

    private func refresh() async {
        do { detail = try await AppAPI(baseURL: store.serverURL).decode(HistoryDetail.self, path: "/api/history/trips/\(tripId)") }
        catch { self.error = error.localizedDescription }
    }
    private func chat() async {
        do {
            let payload = try JSONSerialization.data(withJSONObject: ["message": message])
            let data = try await AppAPI(baseURL: store.serverURL).data("/api/history/trips/\(tripId)/chat", method: "POST", body: payload)
            let result = try JSONDecoder().decode(HistoryChatResponse.self, from: data)
            reply = result.reply
            message = ""
            await refresh()
        } catch { self.error = error.localizedDescription }
    }
    private func mutate(_ action: String) async {
        do {
            _ = try await AppAPI(baseURL: store.serverURL).data("/api/history/trips/\(tripId)/\(action)", method: "POST")
            await refresh()
        } catch { self.error = error.localizedDescription }
    }
}
