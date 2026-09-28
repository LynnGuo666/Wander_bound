import SwiftUI

struct PlanView: View {
    @EnvironmentObject private var store: PlannerStore
    @StateObject private var location = LocationService()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 17) {
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
                    .buttonStyle(.borderedProminent).tint(Palette.brandForest)
                    .accessibilityHint("将行程中的地点加入已到访记忆，未来规划会避开")
                }
            }
            .padding(.horizontal, 18)
            .padding(.top, 14)
            .padding(.bottom, 35)
        }
        .background(Palette.canvas)
        .navigationTitle("规划新行程")
        .navigationBarTitleDisplayMode(.inline)
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
                    .frame(width: 100)
                }
                DatePicker("出发日期", selection: $store.startDate, in: Date()..., displayedComponents: .date)
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
                    store.generate(location: location.coordinate)
                } label: {
                    HStack(spacing: 9) {
                        if store.isLoading {
                            ProgressView().frame(width: 20, height: 20)
                        } else {
                            Image(systemName: "sparkles")
                        }
                        Text(store.isLoading ? "正在规划…" : "生成行程")
                    }
                    .frame(maxWidth: .infinity)
                    .padding(11)
                }
                .buttonStyle(.borderedProminent).tint(Palette.brandForest)
                .disabled(store.isLoading)
                if store.isLoading {
                    HStack {
                        ProgressView()
                        Text(store.progressNote).font(.caption)
                        Spacer()
                        Button("停止") { store.stop() }
                    }
                }
            }
        }
    }

    private func field(_ title: String, text: Binding<String>, icon: String) -> some View {
        HStack(spacing: 7) {
            Image(systemName: icon).foregroundStyle(Palette.forest)
            TextField(title, text: text)
                .font(.body)
                .textInputAutocapitalization(.never)
        }
        .padding(10)
        .background(Palette.canvas, in: RoundedRectangle(cornerRadius: 10))
    }
}
