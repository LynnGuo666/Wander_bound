import AVKit
import Photos
import SwiftUI

private struct PhotoPreview: Identifiable {
    let id = UUID()
    let image: UIImage
}

private struct PhotoTile: View {
    let photo: TripPhoto
    let selected: Bool
    let toggle: () -> Void
    @State private var image: UIImage?

    var body: some View {
        Button(action: toggle) {
            ZStack(alignment: .topTrailing) {
                Group {
                    if let image { Image(uiImage: image).resizable().scaledToFill() }
                    else { Rectangle().fill(Palette.pale).overlay { ProgressView() } }
                }
                .frame(height: 110).clipped()
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(selected ? Palette.forest : .white)
                    .font(.title3).padding(7)
            }
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(photo.capturedDay ?? "未知日期")照片，\(selected ? "已选" : "未选")")
        .task(id: photo.id) {
            let options = PHImageRequestOptions()
            options.deliveryMode = .opportunistic
            PHImageManager.default().requestImage(for: photo.asset, targetSize: CGSize(width: 240, height: 240),
                                                  contentMode: .aspectFill, options: options) { result, _ in
                if let result { Task { @MainActor in image = result } }
            }
        }
    }
}

struct MediaView: View {
    @EnvironmentObject private var store: PlannerStore
    @StateObject private var library = TripPhotoLibrary()
    @State private var startDate = Date()
    @State private var endDate = Date()
    @State private var token = MediaTokenStore.load()
    @State private var selectedLocal: Set<String> = []
    @State private var uploaded: [ServerPhoto] = []
    @State private var selectedForVideo: Set<String> = []
    @State private var tripName = "我的旅程"
    @State private var memoryTitle = "旅行回忆"
    @State private var job: MemoryJob?
    @State private var player: AVPlayer?
    @State private var preview: PhotoPreview?
    @State private var busy = false
    @State private var status = ""

    private let columns = [GridItem(.flexible(), spacing: 6), GridItem(.flexible(), spacing: 6), GridItem(.flexible(), spacing: 6)]
    private var tripId: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        return MediaClient.tripId(destination: tripName.trimmingCharacters(in: .whitespacesAndNewlines),
                                  startDate: "\(formatter.string(from: startDate))..\(formatter.string(from: endDate))")
    }
    private var client: MediaClient { MediaClient(serverURL: store.serverURL, token: token) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                SectionTitle(number: "PRIVATE MEDIA", title: "把旅程留在自己的 Spark", detail: "按日期扫描设备相册。只有你选中的照片会上传到私有服务器；原始定位和 EXIF 不上传。")

                Surface {
                    VStack(alignment: .leading, spacing: 10) {
                        Label("媒体服务访问令牌", systemImage: "lock.shield").font(.headline)
                        SecureField("输入 MEDIA_API_TOKEN", text: $token)
                            .textContentType(.password).textFieldStyle(.roundedBorder)
                        Button("保存到本机钥匙串") { MediaTokenStore.save(token); status = "令牌已保存到钥匙串。" }
                            .font(.caption)
                        Text("请在“来源”页设置服务器地址。Spark 的 Tailscale 私网入口可用 HTTP；其他远程地址需使用 HTTPS。")
                            .font(.caption2).foregroundStyle(Palette.muted)
                    }
                }

                Surface {
                    VStack(alignment: .leading, spacing: 12) {
                        Label("选取旅程照片", systemImage: "photo.on.rectangle.angled").font(.headline)
                        TextField("旅程名称", text: $tripName).textFieldStyle(.roundedBorder)
                        DatePicker("从", selection: $startDate, displayedComponents: .date)
                        DatePicker("到", selection: $endDate, in: startDate..., displayedComponents: .date)
                        Text("旅程名称和日期用于找到对应的私有相册；修改后请重新刷新服务器照片。")
                            .font(.caption2).foregroundStyle(Palette.muted)
                        Button("扫描这段旅程") { Task { await library.scan(from: startDate, through: endDate) } }
                            .buttonStyle(.bordered)
                        Text(library.permissionNote).font(.caption).foregroundStyle(Palette.muted)
                        if !library.photos.isEmpty {
                            Button(selectedLocal.count == library.photos.count ? "取消全选" : "选择全部") {
                                selectedLocal = selectedLocal.count == library.photos.count ? [] : Set(library.photos.map(\.id))
                            }
                            .font(.caption)
                            LazyVGrid(columns: columns, spacing: 6) {
                                ForEach(library.photos) { photo in
                                    PhotoTile(photo: photo, selected: selectedLocal.contains(photo.id)) {
                                        if !selectedLocal.insert(photo.id).inserted { selectedLocal.remove(photo.id) }
                                    }
                                }
                            }
                            Button(busy ? "正在上传…" : "上传所选 \(selectedLocal.count) 张到 Spark") {
                                Task { await uploadSelected() }
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(busy || token.isEmpty || selectedLocal.isEmpty)
                        }
                    }
                }

                Surface {
                    VStack(alignment: .leading, spacing: 12) {
                        Label("私有照片与修图", systemImage: "camera.filters").font(.headline)
                        Button("刷新服务器照片") { Task { await refreshPhotos() } }.font(.caption)
                        if uploaded.isEmpty { Text("上传后可查看本地分析和生成大片色调。")
                                .font(.caption).foregroundStyle(Palette.muted) }
                        ForEach(uploaded) { photo in
                            VStack(alignment: .leading, spacing: 8) {
                                Toggle(isOn: Binding(get: { selectedForVideo.contains(photo.id) }, set: { selected in
                                    if selected { selectedForVideo.insert(photo.id) } else { selectedForVideo.remove(photo.id) }
                                })) { Text(photo.capturedDay ?? "未记录日期").font(.subheadline) }
                                HStack {
                                    Button("自然优化") { Task { await enhance(photo, preset: "natural") } }
                                    Button("大片色调") { Task { await enhance(photo, preset: "cinematic") } }
                                }
                                .font(.caption).disabled(busy)
                            }
                            Divider()
                        }
                    }
                }

                Surface {
                    VStack(alignment: .leading, spacing: 12) {
                        Label("MiniMax H3 旅程短片", systemImage: "film").font(.headline)
                        Text("所选照片只发送到本地 DGX Spark 的 MiniMax H3 工作流；每张生成一个镜头，再在本地合成。")
                            .font(.caption).foregroundStyle(Palette.muted)
                        TextField("短片标题", text: $memoryTitle).textFieldStyle(.roundedBorder)
                        Button("用所选 \(selectedForVideo.count) 张照片生成") { Task { await createMemory() } }
                            .buttonStyle(.borderedProminent)
                            .disabled(busy || selectedForVideo.isEmpty || selectedForVideo.count > 8 || token.isEmpty)
                        if selectedForVideo.count > 8 { Text("一次最多选择 8 张照片。")
                                .font(.caption).foregroundStyle(Palette.coral) }
                        if let job {
                            Text("任务：\(job.status) · \(job.backend)").font(.caption)
                            Button("刷新任务状态") { Task { await refreshJob() } }.font(.caption)
                        }
                        if let player { VideoPlayer(player: player).frame(height: 230) }
                    }
                }

                if !status.isEmpty { Text(status).font(.caption).foregroundStyle(Palette.forest) }
            }
            .padding(18)
        }
        .background(Palette.canvas)
        .navigationTitle("旅行相册")
        .sheet(item: $preview) { item in
            NavigationStack {
                Image(uiImage: item.image).resizable().scaledToFit().padding()
                    .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("完成") { preview = nil } } }
            }
        }
        .onAppear {
            let formatter = DateFormatter()
            formatter.dateFormat = "yyyy-MM-dd"
            formatter.locale = Locale(identifier: "en_US_POSIX")
            if let plan = store.plan {
                startDate = formatter.date(from: plan.startDate) ?? Date()
                endDate = formatter.date(from: plan.endDate) ?? startDate
                tripName = plan.destination
                memoryTitle = "\(plan.destination)旅行回忆"
            }
            if !token.isEmpty { Task { await refreshPhotos() } }
        }
        .task(id: job?.id) {
            while !Task.isCancelled && job?.status == "running" {
                try? await Task.sleep(for: .seconds(10))
                if !Task.isCancelled { await refreshJob() }
            }
        }
    }

    @MainActor private func uploadSelected() async {
        busy = true
        defer { busy = false }
        do {
            var count = 0
            for photo in library.photos where selectedLocal.contains(photo.id) {
                let bytes = try await library.uploadJPEG(for: photo)
                let saved = try await client.upload(bytes, tripId: tripId, capturedDay: photo.capturedDay)
                selectedForVideo.insert(saved.id)
                count += 1
            }
            await refreshPhotos()
            status = "已上传 \(count) 张去除元数据的照片。"
        } catch { status = "上传失败：\(error.localizedDescription)" }
    }

    @MainActor private func refreshPhotos() async {
        guard !token.isEmpty else { return }
        do { uploaded = try await client.photos(tripId: tripId) }
        catch { status = "读取服务器照片失败：\(error.localizedDescription)" }
    }

    @MainActor private func enhance(_ photo: ServerPhoto, preset: String) async {
        busy = true
        defer { busy = false }
        do {
            _ = try await client.enhance(photo.id, preset: preset)
            let bytes = try await client.image(photo.id, variant: preset)
            if let image = UIImage(data: bytes) { preview = PhotoPreview(image: image) }
            status = "已在私有服务器生成修图版本，原图仍保留。"
        } catch { status = "修图失败：\(error.localizedDescription)" }
    }

    @MainActor private func createMemory() async {
        busy = true
        defer { busy = false }
        do {
            let ordered = uploaded.map(\.id).filter { selectedForVideo.contains($0) }
            job = try await client.createMemory(tripId: tripId, photoIds: ordered, title: memoryTitle)
            status = "本地 MiniMax H3 已接收短片任务。"
        } catch { status = "短片任务未开始：\(error.localizedDescription)" }
    }

    @MainActor private func refreshJob() async {
        guard let id = job?.id else { return }
        do {
            job = try await client.memoryStatus(id)
            if job?.status == "succeeded" {
                player = AVPlayer(url: try await client.memoryVideo(id))
                status = "旅程短片已在本地生成。"
            } else if job?.status == "failed" {
                status = job?.error ?? "本地视频生成失败。"
            }
        } catch { status = "查询短片任务失败：\(error.localizedDescription)" }
    }
}
