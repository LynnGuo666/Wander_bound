import SwiftUI

enum Palette {
    static let brandForest = Color(red: 0.14, green: 0.34, blue: 0.29)
    static let forest = Color(uiColor: UIColor { trait in
        trait.userInterfaceStyle == .dark ? UIColor(red: 0.55, green: 0.82, blue: 0.68, alpha: 1)
        : UIColor(red: 0.14, green: 0.34, blue: 0.29, alpha: 1)
    })
    static let ink = Color.primary
    static let muted = Color.secondary
    static let canvas = Color(uiColor: UIColor { trait in
        trait.userInterfaceStyle == .dark ? UIColor(red: 0.08, green: 0.13, blue: 0.11, alpha: 1)
        : UIColor(red: 0.96, green: 0.95, blue: 0.91, alpha: 1)
    })
    static let pale = Color(uiColor: .secondarySystemBackground)
    static let coral = Color(uiColor: UIColor { trait in
        trait.userInterfaceStyle == .dark ? UIColor(red: 0.91, green: 0.64, blue: 0.49, alpha: 1)
        : UIColor(red: 0.62, green: 0.36, blue: 0.24, alpha: 1)
    })
}

struct Surface<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        content
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
            .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 20))
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
