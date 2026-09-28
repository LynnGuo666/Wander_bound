import SwiftUI

struct MemoryView: View {
    @EnvironmentObject private var store: PlannerStore
    @State private var newCity = ""
    @State private var newPlace = ""
    @State private var brands = ""

    var body: some View {
        Form {
            Section {
                TextField("常用出发城市", text: $store.memory.homeCity)
                    .textContentType(.addressCity)
                Picker("优先交通", selection: $store.memory.transportPreference) {
                    Text("飞机").tag("flight")
                    Text("高铁").tag("train")
                }
                Toggle("价格优先", isOn: $store.memory.pricePriority)
                Toggle("避开红眼航班", isOn: $store.memory.avoidRedEye)
            } header: { Text("出行偏好") }
            footer: { Text("这些偏好会用于你发起的下一次行程规划。") }

            Section("住宿") {
                TextField("喜欢的酒店品牌", text: $brands)
                    .onChange(of: brands) { _, value in
                        store.memory.hotelBrands = value.split(whereSeparator: { "、,，".contains($0) })
                            .map(String.init).filter { !$0.isEmpty }
                    }
                Stepper(value: $store.memory.hotelNightBudget, in: 0...10000, step: 50) {
                    LabeledContent("每晚预算", value: store.memory.hotelNightBudget,
                                   format: .currency(code: "CNY"))
                }
            }

            Section {
                ForEach(store.memory.visitedCities, id: \.self) { city in
                    Label(city, systemImage: "mappin")
                }
                .onDelete { indexes in store.memory.visitedCities.remove(atOffsets: indexes) }
                HStack {
                    TextField("添加城市", text: $newCity)
                    Button("添加") { store.addVisitedCity(newCity); newCity = "" }
                        .disabled(newCity.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            } header: { Text("去过的城市") }
            footer: { Text("向左轻扫条目可移除。") }

            Section("去过的地点") {
                ForEach(store.memory.visitedPlaces) { place in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(place.name)
                        Text(place.city).font(.caption).foregroundStyle(.secondary)
                    }
                }
                .onDelete { indexes in store.memory.visitedPlaces.remove(atOffsets: indexes) }
                HStack {
                    TextField("添加地点", text: $newPlace)
                    Button("添加") { store.addVisitedPlace(newPlace); newPlace = "" }
                        .disabled(newPlace.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
        .scrollContentBackground(.hidden)
        .background(Palette.canvas)
        .navigationTitle("我的")
        .onAppear { brands = store.memory.hotelBrands.joined(separator: "、") }
    }
}
