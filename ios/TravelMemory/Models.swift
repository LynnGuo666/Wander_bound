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
    let duration: Int
    let description: String
    let start: String
    let travelMinutes: Int?
    let travelSource: String?
    let rating: Double?
    let ratingSource: String?
}

struct ItineraryDay: Codable, Identifiable {
    var id: Int { day }
    let day: Int
    let date: String
    let title: String
    let stops: [PlaceStop]
}

struct StayArea: Codable {
    let name: String
    let lat: Double
    let lng: Double
    let note: String
    let averageKm: Double?
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
