import Foundation
import CoreLocation

@MainActor
final class PlannerStore: ObservableObject {
    @Published var memory: TripMemory {
        didSet { save(memory, key: "travel-memory-v1") }
    }
    @Published var plan: TravelPlan? {
        didSet { if let plan { save(plan, key: "travel-plan-v1") } }
    }
    @Published var query = "我想去深圳玩 3 天，机票尽量便宜，但不要红眼航班。"
    @Published var destination = "深圳"
    @Published var originCity = ""
    @Published var days = 3
    @Published var startDate: Date
    @Published var serverURL: String {
        didSet { UserDefaults.standard.set(serverURL, forKey: "travel-api-url") }
    }
    @Published var isLoading = false
    @Published var statusMessage: String?

    init() {
        let savedMemory = Self.load(TripMemory.self, key: "travel-memory-v1") ?? TripMemory()
        memory = savedMemory
        plan = Self.load(TravelPlan.self, key: "travel-plan-v1")
        originCity = savedMemory.homeCity
        serverURL = UserDefaults.standard.string(forKey: "travel-api-url") ?? "http://127.0.0.1:4174"
        let calendar = Calendar.current
        let weekday = calendar.component(.weekday, from: Date())
        let daysUntilFriday = (6 - weekday + 7) % 7 == 0 ? 7 : (6 - weekday + 7) % 7
        startDate = calendar.date(byAdding: .day, value: daysUntilFriday, to: Date()) ?? Date()
    }

    func generate(location: CLLocationCoordinate2D?) async {
        guard let endpoint = URL(string: serverURL.trimmingCharacters(in: .whitespacesAndNewlines) + "/api/plan") else {
            statusMessage = "请在数据来源中填写有效的规划服务地址。"
            return
        }
        isLoading = true
        defer { isLoading = false }
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        let requestBody = PlanRequest(
            query: query, destination: destination, originCity: originCity,
            days: days, startDate: formatter.string(from: startDate),
            location: location.map { Coordinates(lat: $0.latitude, lng: $0.longitude) },
            memory: memory
        )
        do {
            var request = URLRequest(url: endpoint)
            request.httpMethod = "POST"
            request.timeoutInterval = 115
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(requestBody)
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let response = response as? HTTPURLResponse else { throw PlannerError.invalidResponse }
            if !(200...299).contains(response.statusCode) {
                let message = try? JSONDecoder().decode(APIError.self, from: data).error
                throw PlannerError.server(message ?? "规划服务返回 \(response.statusCode)")
            }
            let result = try JSONDecoder().decode(TravelPlan.self, from: data)
            plan = result
            originCity = result.originCity
            let sourceMessage: String
            switch result.agentRun?.status {
            case "completed": sourceMessage = "Step 5 Preview 已完成规划"
            case "degraded": sourceMessage = "模型暂不可用，已用规则生成行程"
            default: sourceMessage = "Step 5 Preview 未配置，已用规则生成行程"
            }
            statusMessage = result.locationDetected == true ? "已识别出发城市：\(result.originCity)。\(sourceMessage)" : sourceMessage
        } catch {
            statusMessage = "连接失败：\(error.localizedDescription)"
        }
    }

    func rememberCurrentTrip() {
        guard let plan else { return }
        var changed = memory
        if !changed.visitedCities.contains(plan.destination) { changed.visitedCities.append(plan.destination) }
        for stop in plan.allStops where !changed.visitedPlaces.contains(where: { $0.id == stop.id }) {
            changed.visitedPlaces.append(VisitedPlace(id: stop.id, name: stop.name, city: plan.destination))
        }
        memory = changed
        statusMessage = "已记住 \(plan.destination) 的 \(plan.placeCount) 个地点，下次会避开。"
    }

    func addVisitedCity(_ city: String) {
        let trimmed = city.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: "市", with: "")
        guard !trimmed.isEmpty else { return }
        var changed = memory
        if !changed.visitedCities.contains(trimmed) { changed.visitedCities.append(trimmed) }
        memory = changed
    }

    func addVisitedPlace(_ name: String) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        var changed = memory
        changed.visitedPlaces.append(VisitedPlace(id: "manual-\(UUID().uuidString)", name: trimmed, city: destination))
        memory = changed
    }

    private func save<T: Encodable>(_ value: T, key: String) {
        guard let data = try? JSONEncoder().encode(value) else { return }
        UserDefaults.standard.set(data, forKey: key)
    }

    private static func load<T: Decodable>(_ type: T.Type, key: String) -> T? {
        guard let data = UserDefaults.standard.data(forKey: key) else { return nil }
        return try? JSONDecoder().decode(type, from: data)
    }
}

private enum PlannerError: LocalizedError {
    case invalidResponse
    case server(String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse: "没有收到有效响应"
        case .server(let message): message
        }
    }
}
