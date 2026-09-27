import SwiftUI

struct MemoryView: View {
    @EnvironmentObject private var store: PlannerStore
    @State private var newCity = ""
    @State private var newPlace = ""
    @State private var brands = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("YOUR TRAVEL MEMORY")
                        .font(.caption2.bold()).tracking(2).foregroundStyle(Palette.forest)
                    Text("让下一次，更像你。")
                        .font(.largeTitle.bold()).foregroundStyle(Palette.ink)
                    Text("偏好与足迹保存在此设备。规划时会避开已到访地点。")
                        .font(.caption).foregroundStyle(Palette.muted)
                }
                .padding(.vertical, 12)

                Surface {
                    VStack(alignment: .leading, spacing: 14) {
                        Label("出行偏好", systemImage: "airplane").font(.headline).foregroundStyle(Palette.ink)
                        TextField("常用出发城市", text: $store.memory.homeCity)
                            .textFieldStyle(.roundedBorder)
                        Picker("优先交通", selection: $store.memory.transportPreference) {
                            Text("飞机").tag("flight")
                            Text("高铁").tag("train")
                        }
                        Toggle("价格优先", isOn: $store.memory.pricePriority)
                        Toggle("避开红眼与隔夜航班", isOn: $store.memory.avoidRedEye)
                    }
                }

                Surface {
                    VStack(alignment: .leading, spacing: 14) {
                        Label("住宿喜好", systemImage: "bed.double").font(.headline).foregroundStyle(Palette.ink)
                        TextField("喜欢的品牌，以顿号分隔", text: $brands)
                            .textFieldStyle(.roundedBorder)
                            .onChange(of: brands) { _, value in
                                store.memory.hotelBrands = value.split(whereSeparator: { "、,，".contains($0) }).map(String.init).filter { !$0.isEmpty }
                            }
                        Stepper("每晚预算 ¥\(store.memory.hotelNightBudget)", value: $store.memory.hotelNightBudget, in: 0...10000, step: 50)
                        Label("仅在生成行程时向规划服务传入这些偏好。", systemImage: "lock.shield")
                            .font(.caption2).foregroundStyle(Palette.muted)
                    }
                }

                Surface {
                    VStack(alignment: .leading, spacing: 13) {
                        Label("去过的城市", systemImage: "map").font(.headline).foregroundStyle(Palette.ink)
                        if store.memory.visitedCities.isEmpty {
                            Text("还没有记录").font(.caption).foregroundStyle(Palette.muted)
                        }
                        ForEach(store.memory.visitedCities, id: \.self) { city in
                            HStack {
                                Tag(text: city, symbol: "mappin")
                                Spacer()
                                Button(role: .destructive) {
                                    store.memory.visitedCities.removeAll { $0 == city }
                                } label: { Image(systemName: "xmark.circle") }
                                .accessibilityLabel("移除 \(city)")
                            }
                        }
                        HStack {
                            TextField("添加城市", text: $newCity).textFieldStyle(.roundedBorder)
                            Button("添加") { store.addVisitedCity(newCity); newCity = "" }
                        }
                    }
                }

                Surface {
                    VStack(alignment: .leading, spacing: 13) {
                        Label("去过的地点", systemImage: "mappin.and.ellipse").font(.headline).foregroundStyle(Palette.ink)
                        if store.memory.visitedPlaces.isEmpty {
                            Text("完成一次行程后，可自动记录它的地点。")
                                .font(.caption).foregroundStyle(Palette.muted)
                        }
                        ForEach(store.memory.visitedPlaces) { place in
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(place.name).font(.subheadline)
                                    Text(place.city).font(.caption2).foregroundStyle(Palette.muted)
                                }
                                Spacer()
                                Button(role: .destructive) {
                                    store.memory.visitedPlaces.removeAll { $0.id == place.id }
                                } label: { Image(systemName: "xmark.circle") }
                                .accessibilityLabel("移除 \(place.name)")
                            }
                            Divider()
                        }
                        HStack {
                            TextField("添加已去过的地点", text: $newPlace).textFieldStyle(.roundedBorder)
                            Button("添加") { store.addVisitedPlace(newPlace); newPlace = "" }
                        }
                    }
                }
            }
            .padding(18)
        }
        .background(Palette.canvas)
        .navigationTitle("旅行记忆")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { brands = store.memory.hotelBrands.joined(separator: "、") }
    }
}
