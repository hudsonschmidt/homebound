import SwiftUI

/// Wrapper to handle both new trip and template-based trip creation
enum CreateTripMode: Identifiable {
    case solo
    case group
    case fromTemplate(SavedTripTemplate)

    var id: String {
        switch self {
        case .solo: return "solo"
        case .group: return "group"
        case .fromTemplate(let template): return "template-\(template.id)"
        }
    }

    var template: SavedTripTemplate? {
        switch self {
        case .solo, .group: return nil
        case .fromTemplate(let template): return template
        }
    }

    var isGroupTrip: Bool {
        switch self {
        case .group: return true
        case .solo, .fromTemplate: return false
        }
    }
}

/// Pre-step view shown before CreatePlanView
/// Allows users to choose between creating a new trip or using a saved template
struct TripStartView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    @State private var createTripMode: CreateTripMode? = nil
    @State private var templateToDelete: SavedTripTemplate? = nil
    @State private var showDeleteConfirmation = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    // Header
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Start a Trip")
                            .font(.largeTitle)
                            .fontWeight(.bold)
                        Text("Choose the type of trip you're planning")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.top, 20)

                    // Trip Type Selection
                    HStack(spacing: 12) {
                        // Solo Trip Button
                        Button(action: {
                            createTripMode = .solo
                        }) {
                            TripTypeCard(
                                icon: "figure.walk",
                                title: "Solo Trip",
                                subtitle: "Just me",
                                gradient: [Color.hbBrand, Color.hbTeal]
                            )
                        }
                        .buttonStyle(PlainButtonStyle())

                        // Group Trip Button
                        Button(action: {
                            createTripMode = .group
                        }) {
                            TripTypeCard(
                                icon: "person.3.fill",
                                title: "Group Trip",
                                subtitle: "With friends",
                                gradient: [Color.hbAccent, Color.orange]
                            )
                        }
                        .buttonStyle(PlainButtonStyle())
                    }

                    // Saved Templates Section
                    if !session.savedTemplates.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            // Divider with text
                            HStack {
                                Rectangle()
                                    .fill(Color(.separator))
                                    .frame(height: 1)
                                Text("or start from")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Rectangle()
                                    .fill(Color(.separator))
                                    .frame(height: 1)
                            }
                            .padding(.top, 8)

                            ForEach(session.savedTemplates) { template in
                                Button(action: {
                                    createTripMode = .fromTemplate(template)
                                }) {
                                    TemplateCard(template: template, onDelete: {
                                        templateToDelete = template
                                        showDeleteConfirmation = true
                                    })
                                }
                                .buttonStyle(PlainButtonStyle())
                            }
                        }
                    }
                }
                .padding(.horizontal)
                .padding(.bottom, 100)
            }
            .scrollIndicators(.hidden)
            .navigationTitle("New Adventure")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                }
            }
            .sheet(item: $createTripMode) { mode in
                CreatePlanView(prefillTemplate: mode.template, isGroupTrip: mode.isGroupTrip)
                    .environmentObject(session)
            }
            .alert("Delete Template?", isPresented: $showDeleteConfirmation) {
                Button("Cancel", role: .cancel) {
                    templateToDelete = nil
                }
                Button("Delete", role: .destructive) {
                    if let template = templateToDelete {
                        session.deleteTemplate(template)
                    }
                    templateToDelete = nil
                }
            } message: {
                if let template = templateToDelete {
                    Text("Are you sure you want to delete \"\(template.name)\"? This cannot be undone.")
                }
            }
            .task {
                session.loadTemplates()
            }
            // Dismiss when a trip is created from CreatePlanView
            .onReceive(NotificationCenter.default.publisher(for: .tripCreated)) { _ in
                dismiss()
            }
        }
    }
}

// MARK: - Trip Type Card
struct TripTypeCard: View {
    let icon: String
    let title: String
    let subtitle: String
    let gradient: [Color]

    var body: some View {
        VStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(LinearGradient(
                        colors: gradient,
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ))
                    .frame(width: 60, height: 60)

                Image(systemName: icon)
                    .font(.title2)
                    .foregroundStyle(.white)
            }

            VStack(spacing: 4) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(.primary)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 20)
        .background(Color(.secondarySystemGroupedBackground))
        .cornerRadius(12)
    }
}

// MARK: - Template Card
struct TemplateCard: View {
    let template: SavedTripTemplate
    var onDelete: (() -> Void)? = nil
    @EnvironmentObject var session: Session

    var activity: Activity? {
        session.activities.first { $0.id == template.activityId }
    }

    var body: some View {
        HStack(spacing: 16) {
            ZStack {
                Circle()
                    .fill(Color(hex: activity?.colors.primary ?? "#666666") ?? .gray)
                    .frame(width: 50, height: 50)

                Text(activity?.icon ?? "figure.walk")
                    .font(.title3)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(template.name)
                    .font(.headline)
                    .foregroundStyle(.primary)

                if let location = template.locationText, !location.isEmpty {
                    HStack(spacing: 4) {
                        Image(systemName: "location.fill")
                            .font(.caption2)
                        Text(location)
                            .font(.caption)
                    }
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                }

                // Show contact count if contacts are saved
                let contactCount = [template.contact1Id, template.contact2Id, template.contact3Id].compactMap { $0 }.count
                if contactCount > 0 {
                    HStack(spacing: 4) {
                        Image(systemName: "person.2.fill")
                            .font(.caption2)
                        Text("\(contactCount) contact\(contactCount == 1 ? "" : "s")")
                            .font(.caption)
                    }
                    .foregroundStyle(.secondary)
                }
            }

            Spacer()

            // Delete button
            if let onDelete = onDelete {
                Button(action: onDelete) {
                    Image(systemName: "trash")
                        .font(.subheadline)
                        .foregroundStyle(.red.opacity(0.7))
                        .padding(8)
                }
                .buttonStyle(PlainButtonStyle())
            }

            Image(systemName: "chevron.right")
                .foregroundStyle(.secondary)
        }
        .padding()
        .background(Color(.secondarySystemGroupedBackground))
        .cornerRadius(12)
    }
}

#Preview {
    TripStartView()
        .environmentObject(Session())
}
