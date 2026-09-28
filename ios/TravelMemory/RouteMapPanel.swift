import SwiftUI
import MapKit

struct RouteMapPanel: View {
    let plan: TravelPlan
    @State private var selectedDay = 1

    private var shownDays: [ItineraryDay] {
        selectedDay == 0 ? plan.itinerary : plan.itinerary.filter { $0.day == selectedDay }
    }

    private var stops: [PlaceStop] { shownDays.flatMap(\.stops) }
    private var journeys: [GroundJourney] {
        (plan.groundJourneys ?? []).filter { selectedDay == 0 || $0.day == selectedDay }
    }
    private func coordinate(_ point: Coordinates) -> CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: point.lat, longitude: point.lng)
    }

    private var region: MKCoordinateRegion {
        let points = stops.map { $0.mapCoordinate ?? Coordinates(lat: $0.lat, lng: $0.lng) }
            + journeys.flatMap { [$0.mapFromCoordinate, $0.mapToCoordinate].compactMap { $0 } }
            + [plan.startLocation, plan.stayArea?.mapCoordinate].compactMap { $0 }
            + (plan.terminals?.values.compactMap { $0?.mapCoordinate } ?? [])
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
                            Annotation(stop.name, coordinate: coordinate(stop.mapCoordinate ?? Coordinates(lat: stop.lat, lng: stop.lng))) {
                                Text("\(day.day)")
                                    .font(.caption2.bold()).foregroundStyle(.white)
                                    .frame(width: 26, height: 26)
                                    .background(day.day == 1 ? Palette.coral : Palette.forest, in: Circle())
                                    .overlay(Circle().stroke(.white, lineWidth: 2))
                            }
                        }
                    }
                    ForEach(journeys) { route in
                        let geometry = route.mapGeometry ?? []
                        let points = geometry.count > 1 ? geometry : [route.mapFromCoordinate, route.mapToCoordinate].compactMap { $0 }
                        if points.count > 1 {
                            MapPolyline(coordinates: points.map(coordinate))
                                .stroke(geometry.count > 1 ? Palette.forest : Palette.muted, lineWidth: 3)
                        }
                    }
                    if let hotel = plan.stayArea?.mapCoordinate {
                        Annotation(plan.stayArea?.name ?? "住宿区域", coordinate: coordinate(hotel)) {
                            Image(systemName: "bed.double.fill").padding(7).background(.white, in: Circle())
                        }
                    }
                    if let start = plan.startLocation {
                        Annotation("出发地点", coordinate: coordinate(start)) {
                            Image(systemName: "figure.walk").padding(7).background(.white, in: Circle())
                        }
                    }
                    ForEach((plan.terminals ?? [:]).keys.sorted(), id: \.self) { key in
                        if let terminal = plan.terminals?[key] ?? nil, let point = terminal.mapCoordinate {
                            Annotation(terminal.name, coordinate: coordinate(point)) {
                                Image(systemName: "airplane").padding(7).background(.white, in: Circle())
                            }
                        }
                    }
                }
                .id(selectedDay)
                .frame(height: 250)
                .clipShape(RoundedRectangle(cornerRadius: 13))
                Text("路线实线来自高德；无路线几何时仅显示两点示意线。导航由 Apple 地图即时计算。")
                    .font(.caption2).foregroundStyle(Palette.muted)
                ForEach(journeys) { route in
                    HStack {
                        VStack(alignment: .leading) {
                            Text("\(route.from ?? "出发地") → \(route.to ?? "目的地")").font(.caption.bold())
                            Text(route.minutes.map { "高德预计 \($0) 分钟" } ?? "高德路线时间未知")
                                .font(.caption2).foregroundStyle(Palette.muted)
                        }
                        Spacer()
                        if let destination = route.mapToCoordinate {
                            Button("导航") { navigate(route, destination: destination) }
                                .font(.caption).buttonStyle(.bordered)
                        }
                    }
                }
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

    private func navigate(_ route: GroundJourney, destination: Coordinates) {
        let target = MKMapItem(placemark: MKPlacemark(coordinate: coordinate(destination)))
        target.name = route.to
        let mode = route.mode == "walk" ? MKLaunchOptionsDirectionsModeWalking : MKLaunchOptionsDirectionsModeTransit
        let origin = route.mapFromCoordinate.map { MKMapItem(placemark: MKPlacemark(coordinate: coordinate($0))) }
        MKMapItem.openMaps(with: (origin.map { [$0] } ?? []) + [target],
                           launchOptions: [MKLaunchOptionsDirectionsModeKey: mode])
    }
}
