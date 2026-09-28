import Foundation

enum AppAPIError: LocalizedError {
    case invalidURL
    case server(Int, String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: "服务地址无效"
        case .server(_, let message): message
        }
    }
}

struct AppAPI {
    let baseURL: String

    func url(_ path: String) throws -> URL {
        guard let base = URL(string: baseURL.trimmingCharacters(in: .whitespacesAndNewlines)),
              let scheme = base.scheme?.lowercased(),
              scheme == "https" || (scheme == "http" && ["127.0.0.1", "localhost", "spark-82.tailb7a50b.ts.net"].contains(base.host ?? "")),
              let url = URL(string: path, relativeTo: base)?.absoluteURL else { throw AppAPIError.invalidURL }
        return url
    }

    func request(_ path: String, method: String = "GET", token: String? = nil, body: Data? = nil) throws -> URLRequest {
        var request = URLRequest(url: try url(path))
        request.httpMethod = method
        request.timeoutInterval = 120
        let bearer = token ?? MediaTokenStore.load()
        if !bearer.isEmpty { request.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization") }
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        request.httpBody = body
        return request
    }

    func data(_ path: String, method: String = "GET", token: String? = nil, body: Data? = nil) async throws -> Data {
        let (data, response) = try await URLSession.shared.data(for: request(path, method: method, token: token, body: body))
        guard let response = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        guard (200...299).contains(response.statusCode) else {
            let value = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            let detail = value?["detail"] as? String ?? value?["error"] as? String ?? "请求失败（\(response.statusCode)）"
            throw AppAPIError.server(response.statusCode, detail)
        }
        return data
    }

    func decode<T: Decodable>(_ type: T.Type, path: String, token: String? = nil) async throws -> T {
        try JSONDecoder().decode(type, from: await data(path, token: token))
    }
}
