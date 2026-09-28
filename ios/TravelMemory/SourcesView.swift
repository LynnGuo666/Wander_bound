import SwiftUI

struct SourcesView: View {
    @EnvironmentObject private var store: PlannerStore

    private let names: [(String, String)] = [
        ("amap", "高德地点与路线"),
        ("dida", "道旅酒店"),
        ("duffel", "Duffel 航班"),
        ("tuniu", "途牛 MCP CLI"),
        ("flyai", "飞猪 FlyAI Skill/CLI"),
        ("trip", "携程景区合作方接口"),
        ("reviews", "大众点评/美团评论 MCP"),
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("DATA & TRUST")
                        .font(.caption2.bold()).tracking(2).foregroundStyle(Palette.forest)
                    Text("每一条建议，\n都有出处。")
                        .font(.largeTitle.bold()).foregroundStyle(Palette.ink)
                    Text("没有真实价格的来源不会进入比价列表。")
                        .font(.caption).foregroundStyle(Palette.muted)
                }
                .padding(.vertical, 12)

                Surface {
                    VStack(alignment: .leading, spacing: 12) {
                        Label("规划服务", systemImage: "network").font(.headline).foregroundStyle(Palette.ink)
                        TextField("服务地址", text: $store.serverURL)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .keyboardType(.URL)
                            .textFieldStyle(.roundedBorder)
                        Text("模拟器可用 http://127.0.0.1:4176；真机请填写可访问的 Python FastAPI 地址。")
                            .font(.caption2).foregroundStyle(Palette.muted)
                    }
                }

                Surface {
                    VStack(spacing: 0) {
                        ForEach(names, id: \.0) { key, fallbackName in
                            let info = store.plan?.providerStatus[key]
                            HStack(spacing: 11) {
                                Image(systemName: info?.configured == true ? "checkmark.circle.fill" : "circle.dotted")
                                    .foregroundStyle(info?.configured == true ? Palette.forest : Palette.muted)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(info?.label ?? fallbackName).font(.subheadline.bold()).foregroundStyle(Palette.ink)
                                    Text(info?.result ?? "尚未接入真实数据")
                                        .font(.caption2).foregroundStyle(Palette.muted)
                                }
                                Spacer()
                                Text(info?.configured == true ? "已接入" : "待接入")
                                    .font(.caption2.bold()).foregroundStyle(info?.configured == true ? Palette.forest : Palette.muted)
                            }
                            .padding(.vertical, 11)
                            if key != names.last?.0 { Divider() }
                        }
                    }
                }

                Surface {
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "slider.horizontal.3").foregroundStyle(Palette.forest)
                        VStack(alignment: .leading, spacing: 5) {
                            Text("比价口径").font(.subheadline.bold()).foregroundStyle(Palette.ink)
                            Text("仅比较相同日期、人数、房型、早餐和退改条件下的含税总价。供应商缺价格时只展示来源，不填估算价。")
                                .font(.caption).foregroundStyle(Palette.muted)
                        }
                    }
                }
            }
            .padding(18)
        }
        .background(Palette.canvas)
        .navigationTitle("数据来源")
        .navigationBarTitleDisplayMode(.inline)
    }
}
