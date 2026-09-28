import Foundation

struct PendingPhotoUpload: Codable, Identifiable {
    let id: String
    let ownerId: String?
    let tripId: String
    let capturedDay: String?
    let fileName: String
    let byteCount: Int
}

@MainActor final class PhotoUploadQueue: ObservableObject {
    @Published private(set) var pending: [PendingPhotoUpload] = []
    @Published private(set) var uploadedBytes: Int64 = 0
    @Published private(set) var totalBytes: Int64 = 0
    @Published private(set) var completed = 0
    @Published private(set) var failed: [String] = []
    @Published private(set) var running = false

    private let root: URL
    private let manifest: URL

    init() {
        root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("PhotoUploadQueue", isDirectory: true)
        manifest = root.appendingPathComponent("pending.json")
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        pending = (try? JSONDecoder().decode([PendingPhotoUpload].self, from: Data(contentsOf: manifest))) ?? []
    }

    func enqueue(_ bytes: Data, ownerId: String, tripId: String, assetKey: String, capturedDay: String?) throws {
        guard !pending.contains(where: { $0.id == assetKey && $0.tripId == tripId && $0.ownerId == ownerId }) else { return }
        let name = UUID().uuidString + ".jpg"
        let file = root.appendingPathComponent(name)
        try bytes.write(to: file, options: .atomic)
        try (file as NSURL).setResourceValue(URLFileProtection.completeUntilFirstUserAuthentication,
                                              forKey: .fileProtectionKey)
        pending.append(PendingPhotoUpload(id: assetKey, ownerId: ownerId, tripId: tripId, capturedDay: capturedDay,
                                          fileName: name, byteCount: bytes.count))
        try persist()
    }

    func uploadAll(client: MediaClient, ownerId: String, tripId: String) async {
        guard !running else { return }
        running = true; completed = 0; failed = []
        let batch = pending.filter { $0.tripId == tripId && $0.ownerId == ownerId }
        totalBytes = Int64(batch.reduce(0) { $0 + $1.byteCount })
        uploadedBytes = 0
        for entry in batch {
            let prior = uploadedBytes
            do {
                _ = try await client.uploadFile(root.appendingPathComponent(entry.fileName), tripId: entry.tripId,
                                                assetKey: entry.id, capturedDay: entry.capturedDay) { sent in
                    Task { @MainActor in self.uploadedBytes = prior + sent }
                }
                uploadedBytes = prior + Int64(entry.byteCount)
                completed += 1
                pending.removeAll { $0.id == entry.id && $0.tripId == entry.tripId && $0.ownerId == ownerId }
                try persist()
                try? FileManager.default.removeItem(at: root.appendingPathComponent(entry.fileName))
            } catch {
                failed.append("\(entry.id): \(error.localizedDescription)")
            }
        }
        running = false
    }

    private func persist() throws {
        let data = try JSONEncoder().encode(pending)
        try data.write(to: manifest, options: .atomic)
        try (manifest as NSURL).setResourceValue(URLFileProtection.completeUntilFirstUserAuthentication,
                                                  forKey: .fileProtectionKey)
    }
}
