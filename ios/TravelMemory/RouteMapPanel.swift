import SwiftUI
import MapKit

struct RouteMapPanel: View {
    let plan: TravelPlan
    @State private var selectedDay = 0

    private var shownDays: [ItineraryDay] {
        selectedDay == 0 ? plan.itinerary : plan.itinerary.filter { $0.day == selectedDay }
    }

    private var stops: [PlaceStop] { shownDays.flatMap(\.stops) }

    private var region: MKCoordinateRegion {
        let points = stops
        guard !points.isEmpty else { return MKCoordinateRegion(center: CLLocationCoordinate2D(latitude: 22.5431, longitude: 114.0579), span: MKCoordinateSpan(latitudeDelta: 0.25, longitudeDelta: 0.25)) }
        let minLat = points.map(\.lat).min() ?? 22.54
        let maxLat = points.map(\.lat).max() ?? 22.54
        let minLng = points.map(\.lng).min() ?? 114.05
        let maxLng = points.map(\.lng).max() ?? 114.05
        return MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: (minLat + maxLat) / 2, longitude: (minLng + maxLng) / 2),
            span: MKCoordinateSpan(latitudeDelta: max(0.06, (maxLat - minLat) * 1.5), longitudeDelta: max(0.06, (maxLng - minLng) * 1.5))
        )
    }

    var body: some View {
        Surface {
            VStack(alignment: .leading, spacing: 11) {
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("路线地图").font(.caption).foregroundStyle(Palette.muted)
                        Text("\(plan.destination) · \(plan.placeCount) 站").font(.subheadline.bold()).foregroundStyle(Palette.ink)
                    }
                    Spacer()
                    Image(systemName: "map.fill").foregroundStyle(Palette.forest)
                }
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 7) {
                        dayButton("全部", day: 0)
                        ForEach(plan.itinerary) { day in dayButton("D\(day.day)", day: day.day) }
                    }
                }
                Map(initialPosition: .region(region)) {
                    ForEach(shownDays) { day in
                        ForEach(day.stops) { stop in
                            Annotation(stop.name, coordinate: CLLocationCoordinate2D(latitude: stop.lat, longitude: stop.lng)) {
                                Text("\(day.day)")
                                    .font(.caption2.bold()).foregroundStyle(.white)
                                    .frame(width: 26, height: 26)
                                    .background(day.day == 1 ? Palette.coral : Palette.forest, in: Circle())
                                    .overlay(Circle().stroke(.white, lineWidth: 2))
                            }
                        }
                        if day.stops.count > 1 {
                            MapPolyline(coordinates: day.stops.map { CLLocationCoordinate2D(latitude: $0.lat, longitude: $0.lng) })
                                .stroke(day.day == 1 ? Palette.coral : Palette.forest, lineWidth: 3)
                        }
                    }
                }
                .id(selectedDay)
                .frame(height: 250)
                .clipShape(RoundedRectangle(cornerRadius: 13))
                Text("地图连线表示地点顺序；交通时间以行程中每段的来源为准。")
                    .font(.caption2).foregroundStyle(Palette.muted)
            }
        }
    }

    private func dayButton(_ title: String, day: Int) -> some View {
        Button(title) { selectedDay = day }
            .font(.caption.bold())
            .padding(.horizontal, 12).padding(.vertical, 7)
            .background(selectedDay == day ? Palette.forest : Palette.canvas, in: Capsule())
            .foregroundStyle(selectedDay == day ? .white : Palette.muted)
    }
}
