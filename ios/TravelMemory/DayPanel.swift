import SwiftUI

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
                if let feasibility = day.feasibility {
                    Text(feasibility.status == "conflict" ? "时间冲突" : feasibility.status == "unknown" ? "部分交通时间待核实" : "预计可行")
                        .font(.caption.bold()).foregroundStyle(feasibility.status == "conflict" ? Palette.coral : Palette.forest)
                    ForEach(feasibility.issues, id: \.self) { issue in
                        Text(issue).font(.caption2).foregroundStyle(Palette.coral)
                    }
                }
                if let cost = day.timeCost {
                    Text("时间成本：交通 \(cost.travelMinutes) 分钟 · 游玩 \(cost.visitMinutes) 分钟 · 准备与用餐 \(cost.bufferMinutes) 分钟\(cost.unknownLegs > 0 ? " · \(cost.unknownLegs) 段未知" : "")")
                        .font(.caption2).foregroundStyle(Palette.muted)
                }
                if let timeline = day.timeline, !timeline.isEmpty {
                    ForEach(Array(timeline.enumerated()), id: \.offset) { _, item in
                        HStack(alignment: .top, spacing: 10) {
                            Text(item.startAt.map { String($0.dropFirst(11).prefix(5)) } ?? "待定")
                                .font(.caption.monospacedDigit()).frame(width: 40, alignment: .leading)
                            VStack(alignment: .leading) {
                                Text(item.label).font(.subheadline)
                                Text(item.durationSource == "ai_recommended" ? "AI 建议时长" : item.durationSource == "planning_default" ? "规划占位时长" :
                                     item.routeStatus == "unknown" ? "高德路线时间未知" : item.minutes.map { "\($0) 分钟" } ?? "")
                                    .font(.caption2).foregroundStyle(Palette.muted)
                            }
                        }
                    }
                } else {
                if day.stops.isEmpty {
                    Text(day.title == "抵达与入住" ? "抵达时间较晚，留给进城和入住。" : "尚无可核实的新地点。接入地点源后重新规划。")
                        .font(.caption).foregroundStyle(Palette.muted)
                }
                ForEach(day.stops) { stop in
                    HStack(alignment: .top, spacing: 10) {
                        Text(stop.start ?? "待核实").font(.caption2.bold()).foregroundStyle(Palette.muted).frame(width: 41, alignment: .leading)
                        Circle().fill(Palette.forest).frame(width: 8, height: 8).padding(.top, 4)
                        VStack(alignment: .leading, spacing: 5) {
                            HStack {
                                Text(stop.name).font(.subheadline.bold()).foregroundStyle(Palette.ink)
                                Tag(text: stop.category, symbol: "circle.fill")
                            }
                            Text(stop.description).font(.caption).foregroundStyle(Palette.muted)
                            HStack(spacing: 8) {
                                if let duration = stop.duration {
                                    Text("游玩约 \(duration) 分钟")
                                } else {
                                    Text("游玩时长未核实")
                                }
                                if let minutes = stop.travelMinutes, minutes > 0 {
                                    Text("路程约 \(minutes) 分钟 · \(stop.travelSource ?? "高德")")
                                } else {
                                    Text("路程时间未核实")
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
}
