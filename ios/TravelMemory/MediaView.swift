import AVKit
import Photos
import PhotosUI
import CryptoKit
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
    let tripId: String
    @EnvironmentObject private var account: AccountSession
    @EnvironmentObject private var store: PlannerStore
    @StateObject private var library = TripPhotoLibrary()
    @StateObject private var uploadQueue = PhotoUploadQueue()
    @State private var startDate = Date()
    @State private var endDate = Date()
    @State private var token = MediaTokenStore.load()
    @State private var selectedLocal: Set<String> = []
    @State private var pickedItems: [PhotosPickerItem] = []
    @State private var uploaded: [ServerPhoto] = []
    @State private var analysis: PhotoAnalysisJob?
    @State private var selectedForCuration: Set<String> = []
    @State private var selectedForVideo: Set<String> = []
    @State private var memoryTitle = "旅行回忆"
    @State private var redrawPrompt = "保留原照片中的人物和景点，将画面绘制成有质感的旅行明信片。不要添加文字。"
    @State private var editJob: ImageEditJob?
    @State private var editPhotoId: String?
    @State private var job: MemoryJob?
    @State private var player: AVPlayer?
    @State private var preview: PhotoPreview?
    @State private var busy = false
    @State private var status = ""

    private let columns = [GridItem(.flexible(), spacing: 6), GridItem(.flexible(), spacing: 6), GridItem(.flexible(), spacing: 6)]
    private var client: MediaClient { MediaClient(serverURL: store.serverURL, token: token) }

    var body: some View {
        Form {
            Section {
                Text("选择照片后上传到这段行程。原始 EXIF 可能包含精确位置，仅在私有服务器保存；展示和生成用图会去除 EXIF。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Section("照片上传") {
                if tripId.isEmpty { Text("请先在行程页创建并保存行程，再上传照片；照片会自动关联到该行程。")
                    .font(.caption).foregroundStyle(Palette.coral) }

                        PhotosPicker(selection: $pickedItems, maxSelectionCount: 100, matching: .images,
                                     preferredItemEncoding: .current) {
                            Label("从系统相册手选照片", systemImage: "photo.on.rectangle")
                        }
                        .buttonStyle(.bordered)
                        if !pickedItems.isEmpty {
                            Text("已手选 \(pickedItems.count) 张。确认后原始 EXIF（可能包含精确位置）会私存到 Spark；对外展示与生成使用去除 EXIF 的版本。")
                                .font(.caption).foregroundStyle(Palette.muted)
                            Button("确认上传手选照片") { Task { await uploadPicked() } }
                                .buttonStyle(.borderedProminent).tint(Palette.brandForest).disabled(busy || tripId.isEmpty)
                        }
                        DatePicker("从", selection: $startDate, displayedComponents: .date)
                        DatePicker("到", selection: $endDate, in: startDate..., displayedComponents: .date)
                        Text("按日期寻找相片；只有你选中的照片会上传到此行程。")
                            .font(.caption2).foregroundStyle(Palette.muted)
                        Button("扫描这段旅程") { Task { await library.scan(from: startDate, through: endDate) } }
                            .buttonStyle(.bordered)
                        Text(library.permissionNote).font(.caption).foregroundStyle(Palette.muted)
                        if uploadQueue.running || uploadQueue.totalBytes > 0 {
                            ProgressView(value: Double(uploadQueue.uploadedBytes), total: Double(max(1, uploadQueue.totalBytes)))
                            Text("已传输 \(uploadQueue.uploadedBytes) / \(uploadQueue.totalBytes) 字节 · 完成 \(uploadQueue.completed) 张")
                                .font(.caption).foregroundStyle(Palette.muted)
                        }
                        if !uploadQueue.pending.filter({ $0.tripId == tripId && $0.ownerId == account.user?.id }).isEmpty {
                            Button("重试未完成上传（\(uploadQueue.pending.filter { $0.tripId == tripId && $0.ownerId == account.user?.id }.count) 张）") {
                                Task { await uploadQueue.uploadAll(client: client, ownerId: account.user?.id ?? "", tripId: tripId); await refreshPhotos() }
                            }.disabled(uploadQueue.running)
                        }
                        ForEach(uploadQueue.failed, id: \.self) { Text($0).font(.caption).foregroundStyle(.red) }
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
                            .buttonStyle(.borderedProminent).tint(Palette.brandForest)
                            .disabled(busy || token.isEmpty || tripId.isEmpty || selectedLocal.isEmpty)
                        }
            }

            Section("分析与精选") {
                        Text("画质筛选、去重和视觉打标在私有 Spark 上完成。分析结果不会自动更改精选。")
                            .font(.caption).foregroundStyle(Palette.muted)
                        Button("分析已上传的 \(uploaded.count) 张照片") {
                            Task { await startAnalysis() }
                        }.disabled(uploaded.isEmpty || analysis?.status == "running" || analysis?.status == "queued")
                        if let analysis {
                            Text(analysis.stage).font(.subheadline)
                            ProgressView(value: Double(analysis.completed), total: Double(max(1, analysis.total)))
                            Text("已处理 \(analysis.completed) / \(analysis.total) 张；单张模型推理期间进度会等待。")
                                .font(.caption).foregroundStyle(Palette.muted)
                            if analysis.status == "failed" {
                                Text(analysis.error ?? "分析失败").foregroundStyle(.red)
                                Button("重试分析") { Task { await retryAnalysis() } }
                            }
                            if analysis.status == "succeeded" {
                                Text("推荐 \(analysis.recommended.count) 张，可自行调整后提交。").font(.caption)
                                ForEach(uploaded) { photo in
                                    Toggle(photo.capturedDay ?? photo.id, isOn: Binding(
                                        get: { selectedForCuration.contains(photo.id) },
                                        set: { selected in if selected { selectedForCuration.insert(photo.id) }
                                            else { selectedForCuration.remove(photo.id) } }))
                                }
                                Button("提交精选（\(selectedForCuration.count) 张）") {
                                    Task { await commitCuration() }
                                }.buttonStyle(.borderedProminent).tint(Palette.brandForest)
                            }
                        }
            }

            Section("已上传的照片") {
                        Button("刷新服务器照片") { Task { await refreshPhotos() } }.font(.caption)
                        DisclosureGroup("创意重绘设置") {
                            TextField("描述希望得到的效果", text: $redrawPrompt, axis: .vertical)
                                .lineLimit(2...4)
                            Text("生成新版本，原图保留。")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        if let editJob {
                            Text("创意重绘：\(editJob.status) · \(editJob.backend)").font(.caption)
                            Button("刷新重绘状态") { Task { await refreshEditJob() } }.font(.caption)
                            if editJob.status == "failed" {
                                Button("重试创意重绘") { Task { await retryEdit() } }.font(.caption)
                            }
                        }
                        if uploaded.isEmpty { Text("上传后可查看本地分析和生成大片色调。")
                                .font(.caption).foregroundStyle(Palette.muted) }
                        ForEach(uploaded) { photo in
                            HStack(spacing: 12) {
                                Toggle(isOn: Binding(get: { selectedForVideo.contains(photo.id) }, set: { selected in
                                    if selected { selectedForVideo.insert(photo.id) } else { selectedForVideo.remove(photo.id) }
                                })) { Text(photo.capturedDay ?? "未记录日期").font(.subheadline) }
                                Menu {
                                    Button("查看原图", systemImage: "photo") { Task { await showImage(photo.id) } }
                                    Button("自然优化", systemImage: "wand.and.stars") { Task { await enhance(photo, preset: "natural") } }
                                    Button("大片色调", systemImage: "camera.filters") { Task { await enhance(photo, preset: "cinematic") } }
                                    Button("创意重绘", systemImage: "paintbrush") { Task { await redraw(photo) } }
                                        .disabled(editJob?.status == "queued" || editJob?.status == "running" || redrawPrompt.isEmpty)
                                    ForEach(Array(photo.variants.filter { $0.hasPrefix("ai-") }.enumerated()), id: \.element) { index, variant in
                                        Button("查看创意版 \(index + 1)") { Task { await showImage(photo.id, variant: variant) } }
                                    }
                                } label: { Image(systemName: "ellipsis.circle").font(.title3) }
                                    .accessibilityLabel("\(photo.capturedDay ?? "照片")的编辑和预览操作")
                                    .disabled(busy)
                            }
                            if photo.id != uploaded.last?.id { Divider() }
                        }
            }

            Section("回忆短片") {
                        Text("所选照片只发送到本地 DGX Spark 的 MiniMax H3 工作流；每张生成一个镜头，再在本地合成。")
                            .font(.caption).foregroundStyle(Palette.muted)
                        TextField("短片标题", text: $memoryTitle).textFieldStyle(.roundedBorder)
                        Button("用所选 \(selectedForVideo.count) 张照片生成") { Task { await createMemory() } }
                            .buttonStyle(.borderedProminent).tint(Palette.brandForest)
                            .disabled(busy || selectedForVideo.isEmpty || selectedForVideo.count > 8 || token.isEmpty || tripId.isEmpty)
                        if selectedForVideo.count > 8 { Text("一次最多选择 8 张照片。")
                                .font(.caption).foregroundStyle(Palette.coral) }
                        if let job {
                            Text("任务：\(job.status) · \(job.backend)").font(.caption)
                            Button("刷新任务状态") { Task { await refreshJob() } }.font(.caption)
                            if job.status == "failed" {
                                Button("重试短片生成") { Task { await retryMemory() } }.font(.caption)
                            }
                        }
                        if let player { VideoPlayer(player: player).frame(height: 230) }
            }
            if !status.isEmpty { Text(status).font(.footnote).foregroundStyle(Palette.forest) }
        }
        .scrollContentBackground(.hidden)
        .background(Palette.canvas)
        .navigationTitle("旅行相册")
        .sheet(item: $preview) { item in
            NavigationStack {
                Image(uiImage: item.image).resizable().scaledToFit().padding()
                    .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("完成") { preview = nil } } }
            }
        }
        .task(id: tripId) {
            let formatter = DateFormatter()
            formatter.dateFormat = "yyyy-MM-dd"
            formatter.locale = Locale(identifier: "en_US_POSIX")
            if let trip = try? await AppAPI(baseURL: store.serverURL).decode(TripRecord.self, path: "/api/trips/\(tripId)"),
               let plan = trip.plan {
                startDate = formatter.date(from: plan.startDate) ?? Date()
                endDate = formatter.date(from: plan.endDate) ?? startDate
                memoryTitle = "\(plan.destination)旅行回忆"
            }
            if !token.isEmpty {
                await refreshPhotos()
                await restoreAnalysis()
                await uploadQueue.uploadAll(client: client, ownerId: account.user?.id ?? "", tripId: tripId)
                await refreshPhotos()
            }
        }
        .task(id: "\(job?.id ?? ""): \(job?.status ?? "")") {
            while !Task.isCancelled && (job?.status == "queued" || job?.status == "running") {
                try? await Task.sleep(for: .seconds(10))
                if !Task.isCancelled { await refreshJob() }
            }
        }
        .task(id: "\(editJob?.id ?? ""): \(editJob?.status ?? "")") {
            while !Task.isCancelled && (editJob?.status == "queued" || editJob?.status == "running") {
                try? await Task.sleep(for: .seconds(8))
                if !Task.isCancelled { await refreshEditJob() }
            }
        }
    }

    @MainActor private func startAnalysis() async {
        do {
            analysis = try await client.createAnalysis(tripId: tripId, photoIds: uploaded.map(\.id))
            await pollAnalysis()
        } catch { status = "分析创建失败：\(error.localizedDescription)" }
    }

    @MainActor private func restoreAnalysis() async {
        do {
            analysis = try await client.latestAnalysis(tripId: tripId)
            if analysis?.status == "running" || analysis?.status == "queued" { await pollAnalysis() }
            if analysis?.status == "succeeded" { selectedForCuration = Set(analysis?.recommended ?? []) }
        } catch { status = "分析状态读取失败：\(error.localizedDescription)" }
    }

    @MainActor private func pollAnalysis() async {
        while let current = analysis, current.status == "running" || current.status == "queued" {
            try? await Task.sleep(for: .seconds(3))
            guard !Task.isCancelled else { return }
            do { analysis = try await client.analysisStatus(current.id) }
            catch { status = "分析状态读取失败：\(error.localizedDescription)"; return }
        }
        if analysis?.status == "succeeded" { selectedForCuration = Set(analysis?.recommended ?? []) }
    }

    @MainActor private func retryAnalysis() async {
        guard let analysis else { return }
        do { self.analysis = try await client.retryAnalysis(analysis.id); await pollAnalysis() }
        catch { status = "重试失败：\(error.localizedDescription)" }
    }

    @MainActor private func commitCuration() async {
        guard let analysis else { return }
        do {
            try await client.commitSelection(tripId: tripId, photoIds: uploaded.map(\.id).filter { selectedForCuration.contains($0) }, batchId: analysis.id)
            status = "精选已保存，Web 与 iOS 会看到同一份清单。"
        } catch { status = "精选保存失败：\(error.localizedDescription)" }
    }

    @MainActor private func uploadPicked() async {
        busy = true
        defer { busy = false }
        for item in pickedItems {
            do {
                guard let source = try await item.loadTransferable(type: Data.self) else { throw URLError(.cannotDecodeContentData) }
                let type = item.supportedContentTypes.first?.identifier
                let bytes = try TripPhotoLibrary.jpegPreservingMetadata(source, type: type)
                let key = item.itemIdentifier ?? SHA256.hash(data: source).map { String(format: "%02x", $0) }.joined()
                try uploadQueue.enqueue(bytes, ownerId: account.user?.id ?? "", tripId: tripId, assetKey: key, capturedDay: nil)
            } catch { status = "准备照片失败：\(error.localizedDescription)" }
        }
        await uploadQueue.uploadAll(client: client, ownerId: account.user?.id ?? "", tripId: tripId)
        await refreshPhotos()
        pickedItems = []
        status = uploadQueue.failed.isEmpty ? "已上传 \(uploadQueue.completed) 张照片。" : "有 \(uploadQueue.failed.count) 张未完成，可重试。"
    }

    @MainActor private func uploadSelected() async {
        busy = true
        defer { busy = false }
        for photo in library.photos where selectedLocal.contains(photo.id) {
            do {
                let bytes = try await library.uploadJPEG(for: photo)
                try uploadQueue.enqueue(bytes, ownerId: account.user?.id ?? "", tripId: tripId, assetKey: photo.id, capturedDay: photo.capturedDay)
            } catch { status = "准备照片失败：\(error.localizedDescription)" }
        }
        await uploadQueue.uploadAll(client: client, ownerId: account.user?.id ?? "", tripId: tripId)
        await refreshPhotos()
        status = uploadQueue.failed.isEmpty ? "已上传 \(uploadQueue.completed) 张照片。" : "有 \(uploadQueue.failed.count) 张未完成，可重试。"
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

    @MainActor private func showImage(_ photoId: String, variant: String = "original") async {
        do {
            let bytes = try await client.image(photoId, variant: variant)
            if let image = UIImage(data: bytes) { preview = PhotoPreview(image: image) }
        } catch { status = "预览失败：\(error.localizedDescription)" }
    }

    @MainActor private func redraw(_ photo: ServerPhoto) async {
        busy = true
        defer { busy = false }
        do {
            editPhotoId = photo.id
            editJob = try await client.redraw(photo.id, prompt: redrawPrompt)
            status = "Qwen-Image-2.1 已接收创意重绘任务。"
        } catch { status = "创意重绘未开始：\(error.localizedDescription)" }
    }

    @MainActor private func refreshEditJob() async {
        guard let id = editJob?.id, let photoId = editPhotoId else { return }
        do {
            editJob = try await client.editStatus(id)
            if editJob?.status == "succeeded", let variant = editJob?.variant {
                let bytes = try await client.image(photoId, variant: variant)
                if let image = UIImage(data: bytes) { preview = PhotoPreview(image: image) }
                await refreshPhotos()
                status = "创意重绘已完成，可与原图对比；原图仍保留。"
            } else if editJob?.status == "failed" {
                status = editJob?.error ?? "创意重绘失败。"
            }
        } catch { status = "查询重绘任务失败：\(error.localizedDescription)" }
    }

    @MainActor private func retryEdit() async {
        guard let id = editJob?.id else { return }
        do { editJob = try await client.retryEdit(id); status = "创意重绘已重新排队。" }
        catch { status = "重试失败：\(error.localizedDescription)" }
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

    @MainActor private func retryMemory() async {
        guard let id = job?.id else { return }
        do { job = try await client.retryMemory(id); status = "短片任务已重新排队。" }
        catch { status = "重试失败：\(error.localizedDescription)" }
    }
}
