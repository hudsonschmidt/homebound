import SwiftUI
import Combine

enum TripStatus: String { case planned, inProgress, overdue, done }

struct DemoTrip: Identifiable, Equatable {
    let id: UUID
    var title: String
    var activity: String
    var start: Date
    var eta: Date
    var graceMinutes: Int = 30
    var location: String?
    var status: TripStatus
    var etaPlusGrace: Date { eta.addingTimeInterval(TimeInterval(graceMinutes * 60)) }
}

final class HomeViewModel: ObservableObject {
    @Published var currentTrip: DemoTrip?
    @Published var recent: [DemoTrip] = []
    @Published var now: Date = .now
    private var tick: AnyCancellable?

    init() {
        let start = Calendar.current.date(byAdding: .hour, value: -2, to: .now)!
        let eta   = Calendar.current.date(byAdding: .hour, value:  2, to: .now)!
        self.currentTrip = DemoTrip(id: .init(), title: "Skyline Loop", activity: "Hike",
                                start: start, eta: eta, location: "TNF trailhead",
                                status: .inProgress)
        self.recent = [
            DemoTrip(id: .init(), title: "Crystal Cove Dive", activity: "Dive",
                 start: .now.addingTimeInterval(-86400),
                 eta:   .now.addingTimeInterval(-82800), status: .done),
            DemoTrip(id: .init(), title: "Bishop Bouldering", activity: "Climb",
                 start: .now, eta: .now.addingTimeInterval(14400), status: .planned)
        ]
        startTicker()
    }

    func startTicker() {
        tick = Timer.publish(every: 1, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] in self?.now = $0 }
    }

    func timeRemaining(for demoTrip: DemoTrip) -> TimeInterval {
        max(0, demoTrip.etaPlusGrace.timeIntervalSince(now))
    }

    var isOverdue: Bool {
        guard let t = currentTrip else { return false }
        return now >= t.etaPlusGrace && t.status != .done
    }

    func delayETA(minutes: Int) {
        guard var t = currentTrip else { return }
        t.eta = t.eta.addingTimeInterval(TimeInterval(minutes * 60))
        currentTrip = t
    }

    func checkOut() {
        guard var t = currentTrip else { return }
        t.status = .done
        currentTrip = t
    }
}

struct LandingView: View {
    @StateObject private var vm = HomeViewModel()
    @State private var showShare = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    Header()

                    if vm.currentTrip == nil {
                        EmptyHero(onPlan: { /* start plan flow */ })
                    }

                    if let trip = vm.currentTrip {
                        CurrentTripCard(demoTrip: trip)
                            .environmentObject(vm)
                    }

                    QuickActions(
                        onPlan: { /* start plan */ },
                        onShare: { showShare = true },
                        onAddContact: { /* add */ },
                        onCard: { /* safety card */ }
                    )

                    RecentList(trips: vm.recent)
                }
                .padding()
            }
            .overlay(alignment: .top) {
                if vm.isOverdue {
                    OverdueBanner(
                        onNotify: { /* notify contacts */ },
                        onCall: { /* call 911 */ },
                        onCard: { /* open safety card */ }
                    )
                }
            }
            .navigationTitle("Home")
            .sheet(isPresented: $showShare) { Text("Share…") }
        }
    }
}

// MARK: - Components

private struct Header: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Plan in seconds. Get found fast.")
                .font(.title.bold())
            Text("One-tap check-in/out. Automatic overdue alerts. No live tracking.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct EmptyHero: View {
    var onPlan: () -> Void
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 16)
                .fill(Color(.secondarySystemBackground))
            VStack(spacing: 12) {
                Image(systemName: "map")
                    .font(.system(size: 44, weight: .semibold))
                Text("Create your first trip plan").font(.headline)
                Button("Plan a Trip", action: onPlan)
                    .buttonStyle(.borderedProminent)
            }
            .padding(24)
        }
        .frame(maxWidth: .infinity, minHeight: 160)
    }
}

private struct CurrentTripCard: View {
    @EnvironmentObject var vm: HomeViewModel
    let demoTrip: DemoTrip

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                SwiftUI.Label(demoTrip.title, systemImage: "map")
                    .font(.headline)
                Spacer()
                StatusChip(status: vm.isOverdue ? .overdue : demoTrip.status)
            }

            HStack(spacing: 8) {
                Meta(title: "Start", date: demoTrip.start)
                Divider().frame(height: 18)
                Meta(title: "ETA", date: demoTrip.eta)
                Divider().frame(height: 18)
                CountdownView(remaining: vm.timeRemaining(for: demoTrip),
                              isOverdue: vm.isOverdue)
            }
            .font(.subheadline)
            .foregroundStyle(.secondary)

            if let loc = demoTrip.location {
                SwiftUI.Label(loc, systemImage: "mappin.and.ellipse")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            HStack {
                Button(action: { /* share link */ }) {
                    SwiftUI.Label("Share", systemImage: "link")
                }

                Spacer()

                if demoTrip.status == .inProgress {
                    Button(action: { vm.checkOut() }) {
                        SwiftUI.Label("I’m Safe", systemImage: "checkmark.seal")
                    }
                }

                Menu(content: {
                    Button("+15 min") { vm.delayETA(minutes: 15) }
                    Button("+30 min") { vm.delayETA(minutes: 30) }
                    Button("+60 min") { vm.delayETA(minutes: 60) }
                }, label: {
                    SwiftUI.Label("Delay ETA", systemImage: "clock")
                })
            }
            // keep default button style for widest compatibility
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 16).fill(Color(.systemBackground)))
        .overlay(RoundedRectangle(cornerRadius: 16).strokeBorder(.black.opacity(0.05)))
    }
}

private struct Meta: View {
    var title: String
    var date: Date
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.caption2).foregroundStyle(.secondary)
            Text(date, style: .time).font(.subheadline)
        }
    }
}

private struct CountdownView: View {
    var remaining: TimeInterval
    var isOverdue: Bool
    private var formatted: String {
        let mins = max(0, Int(remaining / 60))
        let hrs = mins / 60
        let rem = mins % 60
        return String(format: "%02dh %02dm left", hrs, rem)
    }
    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: isOverdue ? "clock.badge.exclamationmark" : "clock")
            Text(isOverdue ? "Overdue" : formatted)
        }
    }
}

private struct StatusChip: View {
    let status: TripStatus
    var body: some View {
        let text: String = {
            switch status {
            case .planned: return "Planned"
            case .inProgress: return "In Progress"
            case .overdue: return "Overdue"
            case .done: return "Done"
            }
        }()
        Text(text)
            .font(.caption)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(.thinMaterial)
            .clipShape(Capsule())
    }
}

private struct QuickActions: View {
    var onPlan: () -> Void
    var onShare: () -> Void
    var onAddContact: () -> Void
    var onCard: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Quick Actions").font(.headline)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: 4), spacing: 12) {
                Tile("Plan", "map", onPlan)
                Tile("Share", "link", onShare)
                Tile("Contact", "person.badge.plus", onAddContact)
                Tile("Card", "doc.richtext", onCard)
            }
        }
    }
}

private struct Tile: View {
    let title: String
    let systemImage: String
    let action: () -> Void
    init(_ t: String, _ s: String, _ a: @escaping () -> Void) { title = t; systemImage = s; action = a }

    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                Image(systemName: systemImage).font(.system(size: 22, weight: .semibold))
                Text(title).font(.footnote)
            }
            .frame(maxWidth: .infinity, minHeight: 72)
            .background(RoundedRectangle(cornerRadius: 14).fill(Color(.secondarySystemBackground)))
        }
        .buttonStyle(.plain)
    }
}

private struct RecentList: View {
    let trips: [DemoTrip]
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Recent Plans").font(.headline)
            ForEach(trips) { t in
                HStack {
                    VStack(alignment: .leading) {
                        Text(t.title).font(.subheadline)
                        Text(t.status.rawValue.capitalized)
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Image(systemName: "chevron.right").foregroundStyle(.tertiary)
                }
                .padding(12)
                .background(RoundedRectangle(cornerRadius: 12).fill(Color(.secondarySystemBackground)))
            }
        }
    }
}

private struct OverdueBanner: View {
    var onNotify: () -> Void
    var onCall: () -> Void
    var onCard: () -> Void
    var body: some View {
        HStack {
            Image(systemName: "exclamationmark.triangle.fill")
            Text("Overdue — consider notifying contacts.")
                .font(.subheadline).bold()
            Spacer()
            Menu("Actions", content: {
                Button("Notify now", action: onNotify)
                Button("Show safety card", action: onCard)
                Button("Call 911", action: onCall)
            })
        }
        .padding(12)
        .background(.ultraThinMaterial)
        .background(Color.red.opacity(0.85))
        .foregroundStyle(.white)
    }
}
