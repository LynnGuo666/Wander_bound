import Foundation
import Photos
import UIKit

struct TripPhoto: Identifiable {
    let id: String
    let asset: PHAsset
    let capturedDay: String?
}

@MainActor
final class TripPhotoLibrary: ObservableObject {
    @Published private(set) var photos: [TripPhoto] = []
    @Published private(set) var permissionNote = "尚未读取相册"

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
        let source: Data = try await withCheckedThrowingContinuation { continuation in
            PHImageManager.default().requestImageDataAndOrientation(for: photo.asset, options: options) { data, _, _, info in
                if let data { continuation.resume(returning: data) }
                else { continuation.resume(throwing: NSError(domain: "TravelPhoto", code: 1,
                    userInfo: [NSLocalizedDescriptionKey: (info?[PHImageErrorKey] as? Error)?.localizedDescription ?? "无法读取照片"])) }
            }
        }
        guard let image = UIImage(data: source) else { throw NSError(domain: "TravelPhoto", code: 2,
            userInfo: [NSLocalizedDescriptionKey: "无法解码照片"]) }
        let scale = min(1, 2560 / max(image.size.width, image.size.height))
        let size = CGSize(width: max(1, image.size.width * scale), height: max(1, image.size.height * scale))
        return UIGraphicsImageRenderer(size: size).jpegData(withCompressionQuality: 0.86) { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
    }
}
