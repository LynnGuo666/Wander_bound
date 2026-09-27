import SwiftUI

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
