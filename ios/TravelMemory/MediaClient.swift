import CryptoKit
import Foundation
import Security

struct ServerPhoto: Decodable, Identifiable {
    let id: String
    let tripId: String
    let capturedDay: String?
    let variants: [String]
}

struct MemoryJob: Decodable {
    let id: String
    let status: String
    let backend: String
    let error: String?
}

struct ImageEditJob: Decodable {
    let id: String
    let status: String
    let backend: String
    let seed: Int?
    let variant: String?
    let error: String?
}

private struct MediaError: Decodable {
    let error: String
}

private struct PhotoList: Decodable {
    let photos: [ServerPhoto]
}

enum MediaTokenStore {
    private static let service = "ai.deepsleeptt.travelmemory.media"

    static func load() -> String {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                    kSecAttrService as String: service,
                                    kSecReturnData as String: true,
                                    kSecMatchLimit as String: kSecMatchLimitOne]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return "" }
        return String(data: data, encoding: .utf8) ?? ""
    }

    static func save(_ token: String) {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service]
        SecItemDelete(query as CFDictionary)
        guard !token.isEmpty else { return }
        var attributes = query
        attributes[kSecValueData as String] = Data(token.utf8)
        attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemAdd(attributes as CFDictionary, nil)
    }
}

struct MediaClient {
    let serverURL: String
    let token: String

    static func tripId(destination: String, startDate: String) -> String {
        let digest = SHA256.hash(data: Data("\(destination)|\(startDate)".utf8))
        return "trip-" + digest.prefix(12).map { String(format: "%02x", $0) }.joined()
    }

    private func send(_ path: String, method: String = "GET", body: Data? = nil,
                      contentType: String? = nil, headers: [String: String] = [:]) async throws -> Data {
        guard let base = URL(string: serverURL.trimmingCharacters(in: .whitespacesAndNewlines)),
              base.scheme == "https" || (base.scheme == "http" &&
                  (base.host == "127.0.0.1" || base.host == "localhost" || base.host == "spark-82.tailb7a50b.ts.net")),
              let url = URL(string: path, relativeTo: base)?.absoluteURL else {
            throw NSError(domain: "Media", code: 1, userInfo: [NSLocalizedDescriptionKey: "媒体服务需要 HTTPS、本机地址或本队 Spark 的 Tailscale 私网地址"])
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 120
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if let contentType { request.setValue(contentType, forHTTPHeaderField: "Content-Type") }
        for (key, value) in headers { request.setValue(value, forHTTPHeaderField: key) }
        request.httpBody = body
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        guard (200...299).contains(response.statusCode) else {
            let reason = (try? JSONDecoder().decode(MediaError.self, from: data).error) ?? "媒体服务返回 \(response.statusCode)"
            throw NSError(domain: "Media", code: response.statusCode, userInfo: [NSLocalizedDescriptionKey: reason])
        }
        return data
    }

    func upload(_ bytes: Data, tripId: String, capturedDay: String?) async throws -> ServerPhoto {
        var headers = ["X-Trip-Id": tripId]
        if let capturedDay { headers["X-Captured-Day"] = capturedDay }
        return try JSONDecoder().decode(ServerPhoto.self, from: await send("/api/media/photos", method: "POST", body: bytes,
            contentType: "image/jpeg", headers: headers))
    }

    func enhance(_ id: String, preset: String) async throws -> ServerPhoto {
        let body = try JSONSerialization.data(withJSONObject: ["preset": preset])
        return try JSONDecoder().decode(ServerPhoto.self, from: await send("/api/media/photos/\(id)/enhance", method: "POST",
            body: body, contentType: "application/json"))
    }

    func redraw(_ id: String, prompt: String) async throws -> ImageEditJob {
        let body = try JSONSerialization.data(withJSONObject: ["prompt": prompt])
        return try JSONDecoder().decode(ImageEditJob.self, from: await send("/api/media/photos/\(id)/redraw", method: "POST",
            body: body, contentType: "application/json"))
    }

    func editStatus(_ id: String) async throws -> ImageEditJob {
        try JSONDecoder().decode(ImageEditJob.self, from: await send("/api/media/edits/\(id)"))
    }

    func retryEdit(_ id: String) async throws -> ImageEditJob {
        _ = try await send("/api/media/edits/\(id)/retry", method: "POST")
        return try await editStatus(id)
    }

    func image(_ id: String, variant: String = "original") async throws -> Data {
        try await send("/api/media/photos/\(id)?variant=\(variant)")
    }

    func photos(tripId: String) async throws -> [ServerPhoto] {
        let encoded = tripId.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? tripId
        return try JSONDecoder().decode(PhotoList.self, from: await send("/api/media/photos?tripId=\(encoded)")).photos
    }

    func createMemory(tripId: String, photoIds: [String], title: String) async throws -> MemoryJob {
        let body = try JSONSerialization.data(withJSONObject: ["tripId": tripId, "photoIds": photoIds, "title": title])
        return try JSONDecoder().decode(MemoryJob.self, from: await send("/api/media/memories", method: "POST",
            body: body, contentType: "application/json"))
    }

    func memoryStatus(_ id: String) async throws -> MemoryJob {
        try JSONDecoder().decode(MemoryJob.self, from: await send("/api/media/memories/\(id)"))
    }

    func retryMemory(_ id: String) async throws -> MemoryJob {
        _ = try await send("/api/media/memories/\(id)/retry", method: "POST")
        return try await memoryStatus(id)
    }

    func memoryVideo(_ id: String) async throws -> URL {
        let bytes = try await send("/api/media/memories/\(id)/video")
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("travel-memory-\(id).mp4")
        try bytes.write(to: url, options: .atomic)
        return url
    }
}
