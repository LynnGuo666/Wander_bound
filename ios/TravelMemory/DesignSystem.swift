import SwiftUI

enum Palette {
    static let forest = Color(red: 0.13, green: 0.34, blue: 0.27)
    static let ink = Color(red: 0.11, green: 0.22, blue: 0.19)
    static let muted = Color(red: 0.43, green: 0.54, blue: 0.47)
    static let canvas = Color(red: 0.96, green: 0.97, blue: 0.94)
    static let pale = Color(red: 0.89, green: 0.94, blue: 0.88)
    static let coral = Color(red: 0.95, green: 0.43, blue: 0.31)
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
