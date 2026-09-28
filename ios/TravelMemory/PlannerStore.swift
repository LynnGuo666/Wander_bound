import Foundation
import CoreLocation

@MainActor
final class PlannerStore: ObservableObject {
    @Published var memory: TripMemory {
        didSet { if let activeAccountId { save(memory, key: "travel-memory-v1:\(activeAccountId)") } }
    }
    @Published var plan: TravelPlan? {
        didSet { if let plan, let activeAccountId { save(plan, key: "travel-plan-v1:\(activeAccountId)") } }
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
    @Published var trips: [TripRecord] = []
    @Published var activeTripId: String?
    @Published var question: AgentQuestion?
    @Published var progressNote = ""
    private var streamTask: Task<Void, Never>?
    private var activeAccountId: String?

    init() {
        let savedMemory = TripMemory()
        memory = savedMemory
        plan = nil
        originCity = savedMemory.homeCity
        serverURL = UserDefaults.standard.string(forKey: "travel-api-url") ?? "http://spark-82.tailb7a50b.ts.net:7000"
        let calendar = Calendar.current
        let weekday = calendar.component(.weekday, from: Date())
        let daysUntilFriday = (6 - weekday + 7) % 7 == 0 ? 7 : (6 - weekday + 7) % 7
        startDate = calendar.date(byAdding: .day, value: daysUntilFriday, to: Date()) ?? Date()
    }

    func activateAccount(_ id: String?) {
        guard activeAccountId != id else { return }
        stop(); trips = []; activeTripId = nil; question = nil
        activeAccountId = id
        memory = id.flatMap { Self.load(TripMemory.self, key: "travel-memory-v1:\($0)") } ?? TripMemory()
        plan = id.flatMap { Self.load(TravelPlan.self, key: "travel-plan-v1:\($0)") }
        originCity = memory.homeCity
    }

    func clearAccountData() { activateAccount(nil) }

    func generate(location: CLLocationCoordinate2D?) {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        let requestBody = PlanRequest(
            query: query, destination: destination, originCity: originCity,
            days: days, startDate: formatter.string(from: startDate),
            location: location.map { Coordinates(lat: $0.latitude, lng: $0.longitude) },
            memory: memory
        )
        guard let body = try? JSONEncoder().encode(requestBody) else { return }
        beginStream(body)
    }

    func answer(optionId: String, customText: String = "") {
        guard let question, let activeTripId else { return }
        let payload: [String: Any] = ["sessionId": activeTripId, "answer": [
            "questionId": question.id, "optionId": optionId, "customText": customText]]
        if let body = try? JSONSerialization.data(withJSONObject: payload) { beginStream(body) }
    }

    func revise(_ instruction: String) {
        guard let activeTripId, !instruction.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        if let body = try? JSONSerialization.data(withJSONObject: ["tripId": activeTripId, "query": instruction]) {
            beginStream(body)
        }
    }

    func stop() { streamTask?.cancel(); isLoading = false; progressNote = "规划已停止" }

    func refreshTrips() async {
        do {
            trips = try await AppAPI(baseURL: serverURL).decode(TripList.self, path: "/api/trips").trips
        } catch { statusMessage = "行程读取失败：\(error.localizedDescription)" }
    }

    func openTrip(_ id: String) async {
        do {
            let record: TripRecord = try await AppAPI(baseURL: serverURL).decode(TripRecord.self, path: "/api/trips/\(id)")
            activeTripId = record.id
            plan = record.plan
            question = record.pendingQuestion
        } catch { statusMessage = "行程读取失败：\(error.localizedDescription)" }
    }

    private func beginStream(_ body: Data) {
        streamTask?.cancel()
        isLoading = true
        question = nil
        progressNote = "正在查找地点、交通与住宿…"
        streamTask = Task { await stream(body) }
    }

    private func stream(_ body: Data) async {
        defer { isLoading = false }
        do {
            var request = try AppAPI(baseURL: serverURL).request("/api/plan/stream", method: "POST", body: body)
            request.timeoutInterval = 300
            let (bytes, response) = try await URLSession.shared.bytes(for: request)
            guard let response = response as? HTTPURLResponse, (200...299).contains(response.statusCode) else {
                throw PlannerError.invalidResponse
            }
            var event = ""
            var data: [String] = []
            for try await line in bytes.lines {
                try Task.checkCancellation()
                if line.hasPrefix("event: ") { event = String(line.dropFirst(7)) }
                else if line.hasPrefix("data: ") { data.append(String(line.dropFirst(6))) }
                else if line.isEmpty {
                    if let payload = data.joined(separator: "\n").data(using: .utf8) {
                        receive(event: event, payload: payload)
                    }
                    event = ""; data = []
                }
            }
            await refreshTrips()
        } catch is CancellationError { return }
        catch { statusMessage = "规划失败：\(error.localizedDescription)" }
    }

    private func receive(event: String, payload: Data) {
        guard let object = (try? JSONSerialization.jsonObject(with: payload)) as? [String: Any] else { return }
        if event == "progress" {
            if let note = object["publicNote"] as? String, !note.isEmpty { progressNote = note }
            else if let name = object["type"] as? String { progressNote = name.replacingOccurrences(of: "_", with: " ") }
        } else if event == "result" {
            if let id = object["tripId"] as? String { activeTripId = id }
            if object["needsInput"] as? Bool == true {
                question = try? JSONDecoder().decode(AgentQuestion.self, from: JSONSerialization.data(withJSONObject: object["question"] ?? [:]))
                progressNote = "请选择后继续规划"
            } else if let error = object["error"] as? String {
                statusMessage = error
            } else if let result = try? JSONDecoder().decode(TravelPlan.self, from: payload) {
                plan = result
                originCity = result.originCity
                progressNote = "行程已生成"
            } else { statusMessage = "规划结果格式需要更新，请刷新行程详情" }
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
