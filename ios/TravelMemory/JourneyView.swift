import SwiftUI

struct JourneyView: View {
    @EnvironmentObject private var store: PlannerStore
    @State private var showingComposer = false
    @State private var showingHistoryDiscovery = false

    var body: some View {
        List {
            Section {
                if store.trips.isEmpty {
                    VStack(spacing: 16) {
                        Image("TravelCover")
                            .resizable()
                            .scaledToFill()
                            .frame(height: 170)
                            .clipped()
                            .clipShape(RoundedRectangle(cornerRadius: 14))
                            .accessibilityLabel("山海与小镇的旅行插画")
                        ContentUnavailableView("还没有行程", systemImage: "map",
                                               description: Text("点右上角的加号，规划第一趟旅行。"))
                    }
                    .frame(maxWidth: .infinity)
                    .listRowBackground(Color.clear)
                }
                ForEach(store.trips) { trip in
                    NavigationLink {
                        if trip.kind == "history" { HistoryDetailView(tripId: trip.id) }
                        else { TripDetailView(tripId: trip.id) }
                    } label: {
                        HStack(spacing: 14) {
                            Image(systemName: "map.fill")
                                .font(.title3)
                                .foregroundStyle(.white)
                                .frame(width: 48, height: 48)
                                .background(Palette.brandForest, in: RoundedRectangle(cornerRadius: 12))
                                .accessibilityHidden(true)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(trip.plan?.destination ?? trip.title)
                                    .font(.headline)
                                Text(trip.plan.map { "\($0.startDate) — \($0.endDate)" } ?? "正在规划")
                                    .font(.subheadline).foregroundStyle(.secondary)
                            }
                            Spacer(minLength: 8)
                            Text(trip.status == "ended" ? "已结束" : trip.status == "in_progress" ? "旅途中" : "待出发")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 6)
                    }
                }
            } header: {
                Text("我的行程")
            } footer: {
                Text("行程与旅途故事会同步到当前账号。")
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(Palette.canvas)
        .navigationTitle("行程")
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Button { showingHistoryDiscovery = true } label: {
                    Label("从照片找回旅行", systemImage: "photo.on.rectangle.angled")
                }
            }
            ToolbarItem(placement: .topBarTrailing) {
                Button { showingComposer = true } label: {
                    Label("规划新行程", systemImage: "plus")
                }
            }
        }
        .refreshable { await store.refreshTrips() }
        .task { await store.refreshTrips() }
        .navigationDestination(isPresented: $showingComposer) { PlanView() }
        .navigationDestination(isPresented: $showingHistoryDiscovery) { HistoryDiscoveryView() }
    }
}

struct TripDetailView: View {
    let tripId: String
    @EnvironmentObject private var store: PlannerStore
    @State private var trip: TripRecord?
    @State private var revision = ""
    @State private var error = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let trip {
                    Text(trip.plan?.destination ?? trip.title)
                        .font(.system(.largeTitle, design: .serif, weight: .semibold))
                    if let plan = trip.plan {
                        Text("\(plan.startDate) — \(plan.endDate) · \(plan.days) 天")
                            .foregroundStyle(Palette.muted)
                        PlanOverview(plan: plan)
                        TransportPanel(plan: plan)
                        StayPanel(plan: plan, budget: store.memory.hotelNightBudget)
                        RouteMapPanel(plan: plan)
                        ForEach(plan.itinerary) { DayPanel(day: $0) }
                    } else {
                        ContentUnavailableView("行程还在形成中", systemImage: "sparkles")
                    }
                    NavigationLink {
                        MediaView(tripId: trip.id)
                    } label: { Label("旅行相册与照片分析", systemImage: "photo.stack") }
                        .buttonStyle(.borderedProminent).tint(Palette.brandForest)
                    Surface {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("想换一种走法？").font(.headline)
                            TextField("例如：第三天轻松一点", text: $revision, axis: .vertical)
                                .lineLimit(2...4)
                            Button("发送修改") {
                                store.activeTripId = trip.id
                                store.revise(revision)
                                revision = ""
                            }.disabled(revision.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || store.isLoading)
                            if store.isLoading { ProgressView(); Text(store.progressNote).font(.caption) }
                        }
                    }
                } else { ProgressView("正在读取行程…") }
                if !error.isEmpty { Text(error).foregroundStyle(.red) }
            }.padding(18)
        }
        .background(Palette.canvas)
        .navigationTitle("行程详情")
        .task(id: tripId) { await load() }
        .onChange(of: store.isLoading) { _, loading in if !loading { Task { await load() } } }
    }

    private func load() async {
        do {
            trip = try await AppAPI(baseURL: store.serverURL).decode(TripRecord.self, path: "/api/trips/\(tripId)", token: MediaTokenStore.load())
            await store.openTrip(tripId)
        } catch { self.error = error.localizedDescription }
    }
}
