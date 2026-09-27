import SwiftUI

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
