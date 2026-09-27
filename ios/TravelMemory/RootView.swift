import SwiftUI
import SwiftUIX
import MapKit

enum Palette {
    static let forest = Color(red: 0.13, green: 0.34, blue: 0.27)
    static let ink = Color(red: 0.11, green: 0.22, blue: 0.19)
    static let muted = Color(red: 0.43, green: 0.54, blue: 0.47)
    static let canvas = Color(red: 0.96, green: 0.97, blue: 0.94)
    static let pale = Color(red: 0.89, green: 0.94, blue: 0.88)
    static let coral = Color(red: 0.95, green: 0.43, blue: 0.31)
}

struct RootView: View {
    var body: some View {
        TabView {
            NavigationStack { PlanView() }
                .tabItem { Label("规划", systemImage: "sparkles") }
            NavigationStack { MemoryView() }
                .tabItem { Label("记忆", systemImage: "heart.text.square") }
            NavigationStack { SourcesView() }
                .tabItem { Label("来源", systemImage: "square.stack.3d.up") }
        }
    }
}

struct Surface<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        content
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
            .background(.white, in: RoundedRectangle(cornerRadius: 20))
    }
}

struct SectionTitle: View {
    let number: String
    let title: String
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(number).font(.caption2.bold()).tracking(2).foregroundStyle(Palette.forest)
            Text(title).font(.title3.bold()).foregroundStyle(Palette.ink)
            Text(detail).font(.caption).foregroundStyle(Palette.muted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct PlanView: View {
    @EnvironmentObject private var store: PlannerStore
    @StateObject private var location = LocationService()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 17) {
                hero
                requestCard
                if let message = store.statusMessage {
                    Label(message, systemImage: "info.circle")
                        .font(.caption)
                        .foregroundStyle(Palette.forest)
                        .padding(.horizontal, 4)
                        .accessibilityAddTraits(.updatesFrequently)
                }
                if let plan = store.plan {
                    PlanOverview(plan: plan)
                    TransportPanel(plan: plan)
                    StayPanel(plan: plan, budget: store.memory.hotelNightBudget)
                    RouteMapPanel(plan: plan)
                    SectionTitle(number: "03  ·  THE ITINERARY", title: "让每一天都有新发现", detail: plan.skippedPlaces.isEmpty ? "同一区域优先串联，减少路上折返。" : "已避开：\(plan.skippedPlaces.joined(separator: "、"))")
                        .padding(.top, 8)
                    ForEach(plan.itinerary) { day in DayPanel(day: day) }
                    if let offers = plan.attractionOffers, !offers.isEmpty {
                        Surface {
                            VStack(alignment: .leading, spacing: 10) {
                                Label("景区产品", systemImage: "ticket").font(.headline).foregroundStyle(Palette.ink)
                                ForEach(Array(offers.enumerated()), id: \.offset) { _, offer in
                                    HStack {
                                        VStack(alignment: .leading, spacing: 3) {
                                            Text("\(offer.name) · \(offer.productName.isEmpty ? "景区详情" : offer.productName)")
                                                .font(.subheadline.bold())
                                            Text(offer.startingPrice == true ? "\(offer.provider) · 起价对应 \(offer.priceDate ?? "未知日期")，出游日价格待核" : offer.provider)
                                                .font(.caption2).foregroundStyle(Palette.muted)
                                        }
                                        Spacer()
                                        if let price = offer.price {
                                            Text("\(price, format: .currency(code: offer.currency ?? "CNY"))\(offer.startingPrice == true ? "起" : "")")
                                                .font(.caption.bold()).foregroundStyle(Palette.forest)
                                        } else {
                                            Text("价格待查").font(.caption2).foregroundStyle(Palette.muted)
                                        }
                                        if let link = offer.bookingUrl, let url = URL(string: link) {
                                            Link(destination: url) { Image(systemName: "arrow.up.right") }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Button {
                        store.rememberCurrentTrip()
                    } label: {
                        Label("完成后记住这趟旅程", systemImage: "bookmark.check")
                            .frame(maxWidth: .infinity)
                            .padding(15)
                    }
                    .buttonStyle(.borderedProminent)
                    .accessibilityHint("将行程中的地点加入已到访记忆，未来规划会避开")
                } else {
                    ContentUnavailableView("从一次新探索开始", systemImage: "map", description: Text("输入目的地，添加出发城市，再生成行程。"))
                        .padding(.vertical, 30)
                }
            }
            .padding(.horizontal, 18)
            .padding(.top, 14)
            .padding(.bottom, 35)
        }
        .background(Palette.canvas)
        .navigationTitle("智能规划")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var hero: some View {
        ZStack(alignment: .leading) {
            RoundedRectangle(cornerRadius: 25)
                .fill(LinearGradient(colors: [Palette.pale, Color(red: 0.84, green: 0.91, blue: 0.82)], startPoint: .leading, endPoint: .trailing))
            Circle().fill(Color(red: 0.98, green: 0.84, blue: 0.62))
                .frame(width: 115, height: 115).offset(x: 255, y: -40)
            Image(systemName: "airplane")
                .font(.system(size: 31)).foregroundStyle(Palette.coral)
                .rotationEffect(.degrees(-20)).offset(x: 282, y: -23)
            VStack(alignment: .leading, spacing: 10) {
                Label("更懂你的旅行 Agent", systemImage: "sparkles")
                    .font(.caption.bold()).foregroundStyle(Palette.forest)
                    .padding(.horizontal, 10).padding(.vertical, 7)
                    .background(Color.white.opacity(0.53), in: Capsule())
                Text("下一站，\n去发现新的。")
                    .font(.system(size: 31, weight: .bold, design: .rounded))
                    .tracking(-1.5).foregroundStyle(Palette.ink)
                Text("结合位置、偏好和足迹，安排属于你的旅程。")
                    .font(.caption).foregroundStyle(Palette.muted)
            }
            .padding(23)
        }
        .frame(height: 213)
        .clipped()
    }

    private var requestCard: some View {
        Surface {
            VStack(alignment: .leading, spacing: 14) {
                Label("想去哪里走走？", systemImage: "sparkles")
                    .font(.subheadline.bold()).foregroundStyle(Palette.ink)
                TextEditor(text: $store.query)
                    .frame(minHeight: 76)
                    .scrollContentBackground(.hidden)
                    .font(.subheadline)
                    .accessibilityLabel("旅行需求")
                Divider()
                HStack(spacing: 10) {
                    field("目的地", text: $store.destination, icon: "mappin")
                    Picker("天数", selection: $store.days) {
                        ForEach(1...7, id: \.self) { Text("\($0) 天").tag($0) }
                    }
                    .font(.caption)
                    .frame(width: 88)
                }
                DatePicker("出发日期", selection: $store.startDate, in: Date()..., displayedComponents: .date)
                    .font(.caption)
                HStack {
                    Button { location.locate() } label: {
                        Label("获取当前位置", systemImage: "location.circle")
                    }
                    .buttonStyle(.bordered)
                    Spacer()
                    if location.coordinate != nil { Image(systemName: "checkmark.circle.fill").foregroundStyle(Palette.forest) }
                }
                Text(location.message).font(.caption2).foregroundStyle(Palette.muted)
                field("出发城市（定位不可用时填写）", text: $store.originCity, icon: "location")
                Button {
                    Task { await store.generate(location: location.coordinate) }
                } label: {
                    HStack(spacing: 9) {
                        if store.isLoading {
                            ActivityIndicator().animated(true).style(.large).frame(width: 20, height: 20)
                        } else {
                            Image(systemName: "sparkles")
                        }
                        Text(store.isLoading ? "正在规划…" : "生成行程")
                    }
                    .frame(maxWidth: .infinity)
                    .padding(11)
                }
                .buttonStyle(.borderedProminent)
                .disabled(store.isLoading)
            }
        }
    }

    private func field(_ title: String, text: Binding<String>, icon: String) -> some View {
        HStack(spacing: 7) {
            Image(systemName: icon).foregroundStyle(Palette.forest)
            CocoaTextField(title, text: text)
                .font(.caption)
                .textInputAutocapitalization(.never)
        }
        .padding(10)
        .background(Palette.canvas, in: RoundedRectangle(cornerRadius: 10))
    }
}

struct PlanOverview: View {
    let plan: TravelPlan

    var body: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 8) {
                Text("YOUR NEXT JOURNEY").font(.caption2.bold()).tracking(2).foregroundStyle(Palette.forest)
                Text("\(plan.destination) / \(plan.days) 天的全新探索")
                    .font(.title2.bold()).foregroundStyle(Palette.ink)
                Text(plan.intro).font(.caption).foregroundStyle(Palette.muted)
                HStack(spacing: 8) {
                    Tag(text: "\(plan.placeCount) 个地点", symbol: "mappin.and.ellipse")
                    Tag(text: plan.revisit ? "再次探索" : "初次探索", symbol: "arrow.triangle.2.circlepath")
                }
            }
            Spacer(minLength: 8)
            Text(String(format: "%02d", plan.days))
                .font(.system(size: 48, weight: .bold, design: .rounded))
                .foregroundStyle(Palette.forest.opacity(0.28))
        }
        .padding(.vertical, 8)
    }
}

struct Tag: View {
    let text: String
    let symbol: String

    var body: some View {
        Label(text, systemImage: symbol)
            .font(.caption2.bold())
            .foregroundStyle(Palette.forest)
            .padding(.horizontal, 9).padding(.vertical, 6)
            .background(Palette.pale, in: Capsule())
    }
}

struct TransportPanel: View {
    let plan: TravelPlan

    private var bestFlight: FlightOffer? { plan.flights.first(where: { !$0.redEye }) }
    private var bestTrain: TrainOffer? { plan.trains?.first(where: { !$0.redEye }) }

    var body: some View {
        Surface {
            VStack(alignment: .leading, spacing: 15) {
                SectionTitle(number: "01  ·  GETTING THERE", title: "怎么去，才符合你的节奏", detail: plan.originCity.isEmpty ? "请定位或填写出发城市。" : "从 \(plan.originCity) 出发 · 优先白天低价航班")
                if let flight = bestFlight {
                    VStack(alignment: .leading, spacing: 11) {
                        HStack {
                            Tag(text: "符合偏好", symbol: "airplane")
                            Spacer()
                            Text("实时查询 · \(flight.provider)").font(.caption2).foregroundStyle(Palette.muted)
                        }
                        HStack {
                            flightTime(flight.departureAt, code: flight.origin)
                            Image(systemName: "airplane").foregroundStyle(Palette.forest)
                            Rectangle().fill(Palette.forest.opacity(0.3)).frame(height: 1)
                            flightTime(flight.arrivalAt, code: flight.destination)
                            Spacer()
                            if let price = flight.totalPrice {
                                Text(price, format: .currency(code: flight.currency ?? "CNY"))
                                    .font(.headline).foregroundStyle(Palette.forest)
                            } else {
                                Text("价格待查").font(.caption).foregroundStyle(Palette.muted)
                            }
                        }
                        Text("\(flight.airline) \(flight.flightNumber) · \(flight.stops == 0 ? "直飞" : "\(flight.stops) 次中转") · \(flight.priceBasis ?? "预订前再次验价")")
                            .font(.caption2).foregroundStyle(Palette.muted)
                        if let link = flight.bookingUrl, let url = URL(string: link) {
                            Link("查看供应商", destination: url).font(.caption.bold())
                        }
                    }
                    .padding(12)
                    .background(Palette.pale.opacity(0.65), in: RoundedRectangle(cornerRadius: 13))
                } else {
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "airplane").font(.title3).foregroundStyle(Palette.forest)
                        VStack(alignment: .leading, spacing: 5) {
                            Text("白天航班 · 低价优先").font(.subheadline.bold())
                            Text("尚无实时报价。接入航班数据源后展示含税价格与时间，不生成示例价格。")
                                .font(.caption).foregroundStyle(Palette.muted)
                        }
                    }
                    .padding(13)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Palette.pale.opacity(0.65), in: RoundedRectangle(cornerRadius: 13))
                }
                Divider()
                if let train = bestTrain {
                    VStack(alignment: .leading, spacing: 5) {
                        Label("\(train.trainNumber) · \(String(train.departureAt.dropFirst(11).prefix(5))) → \(String(train.arrivalAt.dropFirst(11).prefix(5)))", systemImage: "tram")
                            .font(.caption.bold()).foregroundStyle(Palette.ink)
                        Text("\(train.origin) → \(train.destination) · \(train.provider)")
                            .font(.caption2).foregroundStyle(Palette.muted)
                        if let price = train.totalPrice {
                            Text(price, format: .currency(code: train.currency ?? "CNY"))
                                .font(.caption.bold()).foregroundStyle(Palette.forest)
                        } else {
                            Text("价格请到供应商查看").font(.caption2).foregroundStyle(Palette.muted)
                        }
                        if let link = train.bookingUrl, let url = URL(string: link) {
                            Link("查看车次", destination: url).font(.caption.bold())
                        }
                    }
                } else {
                    Label("高铁作为备选 · 本次无可核实班次", systemImage: "tram")
                        .font(.caption).foregroundStyle(Palette.muted)
                }
            }
        }
    }

    private func flightTime(_ iso: String, code: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(String(iso.dropFirst(11).prefix(5))).font(.headline)
            Text(code).font(.caption2).foregroundStyle(Palette.muted)
        }
    }
}

struct StayPanel: View {
    let plan: TravelPlan
    let budget: Int

    var body: some View {
        Surface {
            VStack(alignment: .leading, spacing: 13) {
                SectionTitle(number: "02  ·  WHERE TO STAY", title: "住在行程的中心", detail: "结合地点分布、品牌偏好与每晚预算。")
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: "bed.double.fill").foregroundStyle(Palette.forest).padding(9)
                        .background(Palette.pale, in: RoundedRectangle(cornerRadius: 10))
                    VStack(alignment: .leading, spacing: 4) {
                        Text("建议住宿区域").font(.caption2).foregroundStyle(Palette.muted)
                        Text(plan.stayArea?.name ?? "\(plan.destination)市区").font(.headline).foregroundStyle(Palette.forest)
                        Text(plan.stayArea?.note ?? "接入酒店数据后进一步核算通勤距离。")
                            .font(.caption).foregroundStyle(Palette.muted)
                    }
                    Spacer(minLength: 0)
                }
                .padding(12)
                .background(Palette.canvas, in: RoundedRectangle(cornerRadius: 12))
                HStack {
                    Tag(text: plan.hotelBrands.joined(separator: "、"), symbol: "heart")
                    Tag(text: "每晚 ¥\(budget)", symbol: "creditcard")
                }
                if plan.hotels.isEmpty {
                    Text("酒店实时库存未连接，当前没有可比较的房价。")
                        .font(.caption2).foregroundStyle(Palette.muted)
                } else {
                    ForEach(plan.hotels.prefix(3)) { hotel in
                        HStack(spacing: 8) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(hotel.name).font(.subheadline.bold())
                                Text("\(hotel.provider) · \(hotel.address)").font(.caption2).foregroundStyle(Palette.muted)
                            }
                            Spacer()
                            if let price = hotel.displayPrice {
                                Text(price, format: .currency(code: hotel.currency)).font(.caption.bold()).foregroundStyle(Palette.forest)
                            }
                            if let urlString = hotel.bookingUrl, let url = URL(string: urlString) {
                                Link(destination: url) { Image(systemName: "arrow.up.right") }
                            }
                        }
                        Divider()
                    }
                    Text("展示价可能不是最终总价，打开供应商页面前请核对入住与退改条件。")
                        .font(.caption2).foregroundStyle(Palette.muted)
                }
            }
        }
    }
}

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

struct DayPanel: View {
    let day: ItineraryDay

    var body: some View {
        Surface {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text("DAY \(String(format: "%02d", day.day))")
                        .font(.caption2.bold()).foregroundStyle(.white)
                        .padding(.horizontal, 9).padding(.vertical, 7)
                        .background(Palette.forest, in: RoundedRectangle(cornerRadius: 7))
                    VStack(alignment: .leading) {
                        Text(day.title).font(.subheadline.bold()).foregroundStyle(Palette.ink)
                        Text(day.date).font(.caption2).foregroundStyle(Palette.muted)
                    }
                }
                if day.stops.isEmpty {
                    Text(day.title == "抵达与入住" ? "抵达时间较晚，留给进城和入住。" : "尚无可核实的新地点。接入地点源后重新规划。")
                        .font(.caption).foregroundStyle(Palette.muted)
                }
                ForEach(day.stops) { stop in
                    HStack(alignment: .top, spacing: 10) {
                        Text(stop.start).font(.caption2.bold()).foregroundStyle(Palette.muted).frame(width: 41, alignment: .leading)
                        Circle().fill(Palette.forest).frame(width: 8, height: 8).padding(.top, 4)
                        VStack(alignment: .leading, spacing: 5) {
                            HStack {
                                Text(stop.name).font(.subheadline.bold()).foregroundStyle(Palette.ink)
                                Tag(text: stop.category, symbol: "circle.fill")
                            }
                            Text(stop.description).font(.caption).foregroundStyle(Palette.muted)
                            HStack(spacing: 8) {
                                Text("游玩约 \(stop.duration) 分钟")
                                if let minutes = stop.travelMinutes, minutes > 0 {
                                    Text("路程约 \(minutes) 分钟 · \(stop.travelSource ?? "估算")")
                                }
                                if let rating = stop.rating {
                                    Text("评分 \(rating.formatted()) · \(stop.ratingSource ?? "供应商")")
                                } else {
                                    Text("暂无可信评分")
                                }
                            }
                            .font(.caption2).foregroundStyle(Palette.muted)
                        }
                        Spacer(minLength: 0)
                    }
                    if stop.id != day.stops.last?.id { Divider().padding(.leading, 57) }
                }
            }
        }
    }
}
