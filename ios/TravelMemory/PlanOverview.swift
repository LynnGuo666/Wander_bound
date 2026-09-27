import SwiftUI

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
