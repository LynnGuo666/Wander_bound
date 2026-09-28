import Foundation

struct VisitedPlace: Codable, Identifiable, Hashable {
    var id: String
    var name: String
    var city: String
}

struct TripMemory: Codable {
    var homeCity: String = ""
    var transportPreference: String = "flight"
    var pricePriority: Bool = true
    var avoidRedEye: Bool = true
    var hotelBrands: [String] = ["汉庭", "希尔顿"]
    var hotelNightBudget: Int = 550
    var visitedCities: [String] = []
    var visitedPlaces: [VisitedPlace] = []
    var interests: [String] = ["海岸", "艺术", "历史街区"]
}

struct Coordinates: Codable {
    let lat: Double
    let lng: Double
}

struct PlaceStop: Codable, Identifiable {
    let id: String
    let name: String
    let lat: Double
    let lng: Double
    let area: String?
    let category: String
    // 服务端不再编造游玩时长与时刻；两者为 null 表示“已核实但未排时刻”。
    let duration: Int?
    let description: String
    let start: String?
    let travelMinutes: Int?
    let travelSource: String?
    let rating: Double?
    let ratingSource: String?
    let mapCoordinate: Coordinates?
    let durationSource: String?
    let recommendedDurationMinutes: Int?
}

struct TimelineEvent: Codable {
    let kind: String
    let label: String
    let startAt: String?
    let endAt: String?
    let minutes: Int?
    let durationSource: String?
    let routeStatus: String?
}

struct DayFeasibility: Codable {
    let status: String
    let issues: [String]
}

struct TimeCost: Codable {
    let travelMinutes: Int
    let visitMinutes: Int
    let bufferMinutes: Int
    let unknownLegs: Int
}

struct GroundJourney: Codable, Identifiable {
    var id: String { "\(day)-\(purpose ?? "route")-\(from ?? "")-\(to ?? "")" }
    let day: Int
    let purpose: String?
    let from: String?
    let to: String?
    let minutes: Int?
    let mode: String?
    let mapFromCoordinate: Coordinates?
    let mapToCoordinate: Coordinates?
    let mapGeometry: [Coordinates]?
}

struct TerminalPoint: Codable {
    let name: String
    let mapCoordinate: Coordinates?
}

struct ItineraryDay: Codable, Identifiable {
    var id: Int { day }
    let day: Int
    let date: String
    let title: String
    let stops: [PlaceStop]
    let timeline: [TimelineEvent]?
    let feasibility: DayFeasibility?
    let timeCost: TimeCost?
}

struct StayArea: Codable {
    let name: String
    let lat: Double?
    let lng: Double?
    let note: String?
    let averageKm: Double?
    let mapCoordinate: Coordinates?
}

struct FlightOffer: Codable, Identifiable {
    let id: String
    let provider: String
    let airline: String
    let flightNumber: String
    let departureAt: String
    let arrivalAt: String
    let origin: String
    let destination: String
    let stops: Int
    let totalPrice: Double?
    let currency: String?
    let redEye: Bool
    let expiresAt: String?
    let bookingUrl: String?
    let priceBasis: String?
}

struct TrainOffer: Codable, Identifiable {
    let id: String
    let provider: String
    let trainNumber: String
    let departureAt: String
    let arrivalAt: String
    let origin: String
    let destination: String
    let totalPrice: Double?
    let currency: String?
    let redEye: Bool
    let bookingUrl: String?
    let priceBasis: String?
}

struct AttractionOffer: Codable {
    let provider: String
    let name: String
    let productName: String
    let price: Double?
    let currency: String?
    let priceDate: String?
    let startingPrice: Bool?
    let bookingUrl: String?
}

struct HotelOffer: Codable, Identifiable {
    let id: String
    let provider: String
    let name: String
    let address: String
    let displayPrice: Double?
    let priceBasis: String
    let totalPrice: Double?
    let currency: String
    let rating: Double?
    let bookingUrl: String?
}

struct ProviderInfo: Codable {
    let configured: Bool
    let label: String
    let result: String?
}

struct AgentRun: Codable {
    let status: String
    let model: String
}

struct TravelPlan: Codable {
    let tripId: String?
    let destination: String
    let originCity: String
    let startDate: String
    let endDate: String
    let days: Int
    let intro: String
    let revisit: Bool
    let skippedPlaces: [String]
    let itinerary: [ItineraryDay]
    let stayArea: StayArea?
    let flights: [FlightOffer]
    let trains: [TrainOffer]?
    let attractionOffers: [AttractionOffer]?
    let hotels: [HotelOffer]
    let providerStatus: [String: ProviderInfo]
    let transportPreference: String
    let hotelBrands: [String]
    let generatedAt: String
    let locationDetected: Bool?
    let agentRun: AgentRun?
    let groundJourneys: [GroundJourney]?
    let startLocation: Coordinates?
    let terminals: [String: TerminalPoint?]?

    var placeCount: Int { itinerary.reduce(0) { $0 + $1.stops.count } }
    var allStops: [PlaceStop] { itinerary.flatMap(\.stops) }
}

struct PlanRequest: Encodable {
    let query: String
    let destination: String
    let originCity: String
    let days: Int
    let startDate: String
    let location: Coordinates?
    let memory: TripMemory
}

struct APIError: Decodable {
    let error: String
}

struct AgentQuestion: Decodable, Identifiable {
    struct Option: Decodable, Identifiable {
        let id: String
        let label: String
        let description: String?
    }
    let id: String
    let question: String
    let options: [Option]
}

struct TripRecord: Decodable, Identifiable {
    let id: String
    let title: String
    let status: String
    let createdAt: String?
    let plan: TravelPlan?
    let pendingQuestion: AgentQuestion?
    let photos: [ServerPhoto]?
    let kind: String?

    enum CodingKeys: String, CodingKey { case id, title, status, createdAt, plan, pendingQuestion, photos, kind }
    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: CodingKeys.self)
        id = try box.decode(String.self, forKey: .id)
        title = (try? box.decode(String.self, forKey: .title)) ?? "规划中的旅程"
        status = (try? box.decode(String.self, forKey: .status)) ?? "not_started"
        createdAt = try? box.decode(String.self, forKey: .createdAt)
        plan = try? box.decode(TravelPlan.self, forKey: .plan)
        pendingQuestion = try? box.decode(AgentQuestion.self, forKey: .pendingQuestion)
        photos = try? box.decode([ServerPhoto].self, forKey: .photos)
        kind = try? box.decode(String.self, forKey: .kind)
    }
}

struct TripList: Decodable { let trips: [TripRecord] }

struct JournalNote: Codable {
    let tripId: String
    var text: String
    var version: Int
    let updatedAt: String?
}
