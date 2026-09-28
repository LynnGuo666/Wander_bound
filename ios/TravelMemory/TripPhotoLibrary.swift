import Foundation
import Photos
import UIKit
import ImageIO
import UniformTypeIdentifiers

struct TripPhoto: Identifiable {
    let id: String
    let asset: PHAsset
    let capturedDay: String?
}

struct TravelCandidate: Identifiable, Codable {
    let id: String
    let firstDay: String
    let lastDay: String
    let assetIds: [String]
    let locationCount: Int
}

private struct PhotoIndexEntry: Codable {
    let id: String
    let day: String
    let lat: Double?
    let lng: Double?
    let modifiedAt: Date?
}

@MainActor
final class TripPhotoLibrary: ObservableObject {
    @Published private(set) var photos: [TripPhoto] = []
    @Published private(set) var permissionNote = "尚未读取相册"
    @Published private(set) var candidates: [TravelCandidate] = []
    @Published private(set) var scanProgress: Double = 0
    @Published private(set) var scanning = false
    private var cancelled = false

    func cancelScan() { cancelled = true }

    func exclude(_ candidate: TravelCandidate) {
        candidates.removeAll { $0.id == candidate.id }
    }

    func mergeWithNext(_ candidate: TravelCandidate) {
        guard let index = candidates.firstIndex(where: { $0.id == candidate.id }), index + 1 < candidates.count else { return }
        let next = candidates[index + 1]
        let merged = TravelCandidate(id: "\(candidate.firstDay)-\(next.lastDay)", firstDay: candidate.firstDay,
                                     lastDay: next.lastDay, assetIds: Array(Set(candidate.assetIds + next.assetIds)),
                                     locationCount: candidate.locationCount + next.locationCount)
        candidates.replaceSubrange(index...(index + 1), with: [merged])
    }

    func split(_ candidate: TravelCandidate) {
        let photos = photos(for: candidate)
        let dates = Array(Set(photos.compactMap(\.capturedDay))).sorted()
        guard dates.count > 1, let index = candidates.firstIndex(where: { $0.id == candidate.id }) else { return }
        let boundary = dates[dates.count / 2]
        let left = photos.filter { ($0.capturedDay ?? "") < boundary }
        let right = photos.filter { ($0.capturedDay ?? "") >= boundary }
        guard !left.isEmpty && !right.isEmpty else { return }
        let parts = [(left, candidate.firstDay, left.last?.capturedDay ?? candidate.firstDay),
                     (right, boundary, candidate.lastDay)].map { items, first, last in
            TravelCandidate(id: "\(first)-\(last)", firstDay: first, lastDay: last,
                            assetIds: items.map(\.id), locationCount: items.filter { $0.asset.location != nil }.count)
        }
        candidates.replaceSubrange(index...index, with: parts)
    }

    func scanAllAuthorized() async {
        let authorization = await withCheckedContinuation { continuation in
            PHPhotoLibrary.requestAuthorization(for: .readWrite) { continuation.resume(returning: $0) }
        }
        guard authorization == .authorized || authorization == .limited else {
            permissionNote = "需要允许读取照片，才能发现过往旅行。"
            return
        }
        cancelled = false
        scanning = true
        defer { scanning = false }
        let options = PHFetchOptions()
        options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: true)]
        let assets = PHAsset.fetchAssets(with: .image, options: options)
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        let cacheURL = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("travel-photo-index.json")
        let cached = ((try? Data(contentsOf: cacheURL)).flatMap { try? JSONDecoder().decode([PhotoIndexEntry].self, from: $0) }) ?? []
        var byId = Dictionary(uniqueKeysWithValues: cached.map { ($0.id, $0) })
        var entries: [PhotoIndexEntry] = []
        for index in 0..<assets.count {
            if cancelled {
                try? FileManager.default.createDirectory(at: cacheURL.deletingLastPathComponent(), withIntermediateDirectories: true)
                if let data = try? JSONEncoder().encode(entries) { try? data.write(to: cacheURL, options: .atomic) }
                permissionNote = "扫描已暂停，下次继续。"
                return
            }
            let asset = assets.object(at: index)
            guard !asset.mediaSubtypes.contains(.photoScreenshot), let date = asset.creationDate else { continue }
            let id = asset.localIdentifier
            let prior = byId.removeValue(forKey: id)
            let entry: PhotoIndexEntry
            if let prior, prior.modifiedAt == asset.modificationDate {
                entry = prior
            } else {
                entry = PhotoIndexEntry(id: id, day: formatter.string(from: date),
                    lat: asset.location?.coordinate.latitude, lng: asset.location?.coordinate.longitude,
                    modifiedAt: asset.modificationDate)
            }
            entries.append(entry)
            if index % 200 == 0 {
                scanProgress = Double(index) / Double(max(1, assets.count))
                if index % 1000 == 0 && index > 0 {
                    try? FileManager.default.createDirectory(at: cacheURL.deletingLastPathComponent(), withIntermediateDirectories: true)
                    if let data = try? JSONEncoder().encode(entries) { try? data.write(to: cacheURL, options: .atomic) }
                }
                await Task.yield()
            }
        }
        try? FileManager.default.createDirectory(at: cacheURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        if let data = try? JSONEncoder().encode(entries) { try? data.write(to: cacheURL, options: .atomic) }
        try? (cacheURL as NSURL).setResourceValue(URLFileProtection.completeUntilFirstUserAuthentication,
                                                   forKey: .fileProtectionKey)
        scanProgress = 1
        candidates = Self.discover(entries)
        permissionNote = authorization == .limited
            ? "已扫描获准访问的 \(entries.count) 张照片；可在系统设置中扩大范围。"
            : "已扫描 \(entries.count) 张照片，发现 \(candidates.count) 段可能的旅行。"
    }

    private static func discover(_ entries: [PhotoIndexEntry]) -> [TravelCandidate] {
        let located = entries.filter { $0.lat != nil && $0.lng != nil }
        let buckets = Dictionary(grouping: located) { "\(Int(($0.lat ?? 0) * 10))|\(Int(($0.lng ?? 0) * 10))" }
        let home = buckets.max { $0.value.count < $1.value.count }?.value.first
        let away = entries.filter { entry in
            guard let lat = entry.lat, let lng = entry.lng, let home else { return false }
            let dy = (lat - (home.lat ?? lat)) * 111
            let dx = (lng - (home.lng ?? lng)) * 90
            return (dx * dx + dy * dy).squareRoot() >= 30
        }
        let days = Dictionary(grouping: away, by: \.day)
        var groups: [[PhotoIndexEntry]] = []
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        for day in days.keys.sorted() {
            let current = days[day] ?? []
            if let last = groups.last?.last, let a = formatter.date(from: last.day), let b = formatter.date(from: day),
               b.timeIntervalSince(a) <= 2 * 86400 {
                groups[groups.count - 1].append(contentsOf: current)
            } else { groups.append(current) }
        }
        let discovered = groups.filter { $0.count >= 3 }.map { group in
            let start = group.first!.day, end = group.last!.day
            let ids = entries.filter { $0.day >= start && $0.day <= end }.map(\.id)
            return TravelCandidate(id: "\(start)-\(end)", firstDay: start, lastDay: end,
                                   assetIds: ids, locationCount: group.count)
        }
        if !discovered.isEmpty { return discovered }
        let dated = Dictionary(grouping: entries, by: \.day)
        return dated.keys.sorted().compactMap { day in
            let items = dated[day] ?? []
            return items.count >= 5 ? TravelCandidate(id: "date-\(day)", firstDay: day, lastDay: day,
                                                       assetIds: items.map(\.id), locationCount: items.filter { $0.lat != nil }.count) : nil
        }
    }

    func photos(for candidate: TravelCandidate) -> [TripPhoto] {
        let assets = PHAsset.fetchAssets(withLocalIdentifiers: candidate.assetIds, options: nil)
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        return (0..<assets.count).map { index in
            let asset = assets.object(at: index)
            return TripPhoto(id: asset.localIdentifier, asset: asset,
                             capturedDay: asset.creationDate.map(formatter.string(from:)))
        }
    }

    func scan(from start: Date, through end: Date) async {
        let authorization = await withCheckedContinuation { continuation in
            PHPhotoLibrary.requestAuthorization(for: .readWrite) { status in continuation.resume(returning: status) }
        }
        guard authorization == .authorized || authorization == .limited else {
            permissionNote = "请在系统设置中允许读取照片。"
            photos = []
            return
        }
        let calendar = Calendar.current
        let lower = calendar.startOfDay(for: start)
        let upper = calendar.date(byAdding: .day, value: 1, to: calendar.startOfDay(for: end)) ?? end
        let options = PHFetchOptions()
        options.predicate = NSPredicate(format: "creationDate >= %@ AND creationDate < %@", lower as NSDate, upper as NSDate)
        options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: true)]
        let result = PHAsset.fetchAssets(with: .image, options: options)
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        photos = (0..<result.count).compactMap { index in
            let asset = result.object(at: index)
            guard !asset.mediaSubtypes.contains(.photoScreenshot) else { return nil }
            return TripPhoto(id: asset.localIdentifier, asset: asset,
                             capturedDay: asset.creationDate.map(formatter.string(from:)))
        }
        permissionNote = authorization == .limited
            ? "仅扫描到系统允许访问的照片，共 \(photos.count) 张。可在系统设置中扩大范围。"
            : "本次日期范围找到 \(photos.count) 张照片；仅选择的照片会上传。"
    }

    func uploadJPEG(for photo: TripPhoto) async throws -> Data {
        let options = PHImageRequestOptions()
        options.isNetworkAccessAllowed = true
        options.deliveryMode = .highQualityFormat
        let (source, uti): (Data, String?) = try await withCheckedThrowingContinuation { continuation in
            PHImageManager.default().requestImageDataAndOrientation(for: photo.asset, options: options) { data, type, _, info in
                if let data { continuation.resume(returning: (data, type)) }
                else { continuation.resume(throwing: NSError(domain: "TravelPhoto", code: 1,
                    userInfo: [NSLocalizedDescriptionKey: (info?[PHImageErrorKey] as? Error)?.localizedDescription ?? "无法读取 iCloud 照片"])) }
            }
        }
        return try Self.jpegPreservingMetadata(source, type: uti)
    }

    static func jpegPreservingMetadata(_ source: Data, type uti: String?) throws -> Data {
        if let uti, UTType(uti)?.conforms(to: .jpeg) == true { return source }
        guard let sourceRef = CGImageSourceCreateWithData(source as CFData, nil),
              let destination = CFDataCreateMutable(nil, 0),
              let writer = CGImageDestinationCreateWithData(destination, UTType.jpeg.identifier as CFString, 1, nil) else {
            throw NSError(domain: "TravelPhoto", code: 2, userInfo: [NSLocalizedDescriptionKey: "无法读取照片元数据"])
        }
        let properties = (CGImageSourceCopyPropertiesAtIndex(sourceRef, 0, nil) as? [String: Any] ?? [:])
            .merging([kCGImageDestinationLossyCompressionQuality as String: 0.9]) { _, new in new }
        CGImageDestinationAddImageFromSource(writer, sourceRef, 0, properties as CFDictionary)
        guard CGImageDestinationFinalize(writer) else {
            throw NSError(domain: "TravelPhoto", code: 3, userInfo: [NSLocalizedDescriptionKey: "无法转换照片"])
        }
        return destination as Data
    }
}
