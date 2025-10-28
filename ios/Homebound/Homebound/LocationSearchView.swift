import SwiftUI
import MapKit
import CoreLocation
import Combine

// MARK: - Location Search View
struct LocationSearchView: View {
    @Binding var selectedLocation: String
    @Binding var selectedCoordinates: CLLocationCoordinate2D?
    @Binding var isPresented: Bool

    @StateObject private var searchCompleter = LocationSearchCompleter()
    @State private var searchText = ""
    @State private var showingNearby = true
    @State private var nearbyPlaces: [MKMapItem] = []
    @State private var isLoadingNearby = true

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Search Bar
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundStyle(.secondary)

                    TextField("Search places...", text: $searchText)
                        .textFieldStyle(.plain)
                        .autocapitalization(.none)
                        .disableAutocorrection(true)
                        .onChange(of: searchText) { _, newValue in
                            searchCompleter.searchQuery = newValue
                            showingNearby = newValue.isEmpty
                        }

                    if !searchText.isEmpty {
                        Button(action: {
                            searchText = ""
                            showingNearby = true
                        }) {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .padding()
                .background(Color(.secondarySystemBackground))
                .cornerRadius(12)
                .padding()

                // Results List
                List {
                    if showingNearby {
                        // Current Location Option
                        Section {
                            Button(action: {
                                selectedLocation = "Current Location"
                                selectedCoordinates = searchCompleter.currentLocation
                                isPresented = false
                            }) {
                                HStack {
                                    ZStack {
                                        Circle()
                                            .fill(Color(hex: "#6C63FF") ?? .purple)
                                            .frame(width: 40, height: 40)

                                        Image(systemName: "location.fill")
                                            .foregroundStyle(.white)
                                            .font(.system(size: 18))
                                    }

                                    VStack(alignment: .leading, spacing: 4) {
                                        Text("Current Location")
                                            .font(.subheadline)
                                            .fontWeight(.medium)
                                            .foregroundStyle(.primary)

                                        Text("Use your current location")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }

                                    Spacer()
                                }
                            }
                        }

                        // Nearby Places
                        if isLoadingNearby {
                            Section("Nearby Places") {
                                HStack {
                                    Spacer()
                                    ProgressView()
                                        .padding()
                                    Spacer()
                                }
                            }
                        } else if !nearbyPlaces.isEmpty {
                            Section("Nearby Places") {
                                ForEach(nearbyPlaces, id: \.self) { place in
                                    LocationRow(
                                        mapItem: place,
                                        onSelect: {
                                            selectedLocation = place.name ?? "Unknown Location"
                                            selectedCoordinates = place.location.coordinate
                                            isPresented = false
                                        }
                                    )
                                }
                            }
                        }
                    } else {
                        // Search Results
                        if searchCompleter.searchResults.isEmpty && !searchText.isEmpty {
                            HStack {
                                Spacer()
                                VStack(spacing: 12) {
                                    Image(systemName: "magnifyingglass")
                                        .font(.largeTitle)
                                        .foregroundStyle(.secondary)

                                    Text("No results found")
                                        .font(.headline)
                                        .foregroundStyle(.secondary)

                                    Text("Try searching for a different place")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                .padding(.vertical, 40)
                                Spacer()
                            }
                            .listRowBackground(Color.clear)
                        } else {
                            ForEach(searchCompleter.searchResults, id: \.self) { result in
                                SearchResultRow(
                                    result: result,
                                    onSelect: {
                                        Task {
                                            await selectSearchResult(result)
                                        }
                                    }
                                )
                            }
                        }
                    }
                }
                .listStyle(.insetGrouped)
            }
            .navigationTitle("Select Location")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        isPresented = false
                    }
                }
            }
        }
        .task {
            await loadNearbyPlaces()
        }
    }

    private func selectSearchResult(_ result: MKLocalSearchCompletion) async {
        // Convert search completion to map item
        let searchRequest = MKLocalSearch.Request(completion: result)
        let search = MKLocalSearch(request: searchRequest)

        do {
            let response = try await search.start()
            if let mapItem = response.mapItems.first {
                await MainActor.run {
                    selectedLocation = result.title + (result.subtitle.isEmpty ? "" : ", \(result.subtitle)")
                    selectedCoordinates = mapItem.location.coordinate
                    isPresented = false
                }
            }
        } catch {
            print("Error converting search result: \(error)")
            await MainActor.run {
                selectedLocation = result.title
                isPresented = false
            }
        }
    }

    private func loadNearbyPlaces() async {
        guard let location = searchCompleter.currentLocation else {
            await MainActor.run {
                isLoadingNearby = false
            }
            return
        }

        let request = MKLocalSearch.Request()
        request.naturalLanguageQuery = "Points of Interest"
        request.region = MKCoordinateRegion(
            center: location,
            span: MKCoordinateSpan(latitudeDelta: 0.05, longitudeDelta: 0.05)
        )

        let search = MKLocalSearch(request: request)

        do {
            let response = try await search.start()
            await MainActor.run {
                nearbyPlaces = Array(response.mapItems.prefix(10))
                isLoadingNearby = false
            }
        } catch {
            print("Error loading nearby places: \(error)")
            await MainActor.run {
                isLoadingNearby = false
            }
        }
    }
}

// MARK: - Location Row
struct LocationRow: View {
    let mapItem: MKMapItem
    let onSelect: () -> Void
    @StateObject private var locationManager = LocationHelper()

    private var categoryIcon: String {
        guard let category = mapItem.pointOfInterestCategory else {
            return "mappin.circle.fill"
        }

        switch category {
        case .airport: return "airplane"
        case .amusementPark: return "star.circle.fill"
        case .aquarium: return "drop.circle.fill"
        case .atm: return "creditcard.fill"
        case .bakery: return "birthday.cake.fill"
        case .bank: return "building.columns.fill"
        case .beach: return "umbrella.fill"
        case .brewery: return "mug.fill"
        case .cafe: return "cup.and.saucer.fill"
        case .campground: return "tent.fill"
        case .carRental: return "car.fill"
        case .evCharger: return "bolt.car.fill"
        case .fireStation: return "flame.fill"
        case .fitnessCenter: return "figure.run"
        case .foodMarket: return "cart.fill"
        case .gasStation: return "fuelpump.fill"
        case .hospital: return "cross.fill"
        case .hotel: return "bed.double.fill"
        case .laundry: return "washer.fill"
        case .library: return "books.vertical.fill"
        case .marina: return "sailboat.fill"
        case .movieTheater: return "tv.fill"
        case .museum: return "building.columns.fill"
        case .nationalPark: return "tree.fill"
        case .nightlife: return "moon.stars.fill"
        case .park: return "leaf.fill"
        case .parking: return "p.square.fill"
        case .pharmacy: return "pills.fill"
        case .police: return "shield.fill"
        case .postOffice: return "envelope.fill"
        case .publicTransport: return "bus.fill"
        case .restaurant: return "fork.knife"
        case .restroom: return "figure.dress.line.vertical.figure"
        case .school: return "graduationcap.fill"
        case .stadium: return "sportscourt.fill"
        case .store: return "bag.fill"
        case .theater: return "theatermasks.fill"
        case .university: return "building.2.fill"
        case .winery: return "wineglass.fill"
        case .zoo: return "pawprint.fill"
        default: return "mappin.circle.fill"
        }
    }

    private var categoryColor: Color {
        guard let category = mapItem.pointOfInterestCategory else {
            return Color(hex: "#6C63FF") ?? .purple
        }

        switch category {
        case .restaurant, .cafe, .bakery, .foodMarket:
            return .orange
        case .park, .nationalPark, .beach, .campground:
            return .green
        case .hotel, .gasStation, .parking:
            return .blue
        case .hospital, .pharmacy, .police, .fireStation:
            return .red
        case .museum, .theater, .movieTheater:
            return Color(hex: "#6C63FF") ?? .purple
        default:
            return .gray
        }
    }

    var body: some View {
        Button(action: onSelect) {
            HStack {
                ZStack {
                    Circle()
                        .fill(categoryColor.opacity(0.2))
                        .frame(width: 40, height: 40)

                    Image(systemName: categoryIcon)
                        .foregroundStyle(categoryColor)
                        .font(.system(size: 18))
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(mapItem.name ?? "Unknown Place")
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundStyle(.primary)

                    if let address = formatAddress(mapItem) {
                        Text(address)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }

                Spacer()

                if let currentLocation = locationManager.currentLocation {
                    let distance = mapItem.location.distance(from: CLLocation(latitude: currentLocation.latitude, longitude: currentLocation.longitude))
                    Text(formatDistance(distance))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func formatAddress(_ mapItem: MKMapItem) -> String? {
        // For now, just return the subtitle if available
        // In a real app, we might use reverse geocoding or access the address differently
        return nil
    }

    private func formatDistance(_ distance: CLLocationDistance) -> String {
        let formatter = MKDistanceFormatter()
        formatter.unitStyle = .abbreviated
        return formatter.string(fromDistance: distance)
    }
}

// MARK: - Search Result Row
struct SearchResultRow: View {
    let result: MKLocalSearchCompletion
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            HStack {
                ZStack {
                    Circle()
                        .fill(Color(hex: "#6C63FF")?.opacity(0.2) ?? Color.purple.opacity(0.2))
                        .frame(width: 40, height: 40)

                    Image(systemName: "mappin.circle.fill")
                        .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
                        .font(.system(size: 18))
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(result.title)
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundStyle(.primary)

                    if !result.subtitle.isEmpty {
                        Text(result.subtitle)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }

                Spacer()
            }
        }
    }
}

// MARK: - Location Helper (for LocationRow)
class LocationHelper: NSObject, ObservableObject {
    @Published var currentLocation: CLLocationCoordinate2D?
    private let locationManager = CLLocationManager()

    override init() {
        super.init()
        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracyBest
        locationManager.requestWhenInUseAuthorization()
        locationManager.startUpdatingLocation()
    }
}

extension LocationHelper: CLLocationManagerDelegate {
    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }
        currentLocation = location.coordinate
    }
}

// MARK: - Location Search Completer
class LocationSearchCompleter: NSObject, ObservableObject {
    @Published var searchResults: [MKLocalSearchCompletion] = []
    @Published var currentLocation: CLLocationCoordinate2D?

    var searchQuery = "" {
        didSet {
            if searchQuery.isEmpty {
                searchResults = []
            } else {
                searchCompleter.queryFragment = searchQuery
            }
        }
    }

    private let searchCompleter = MKLocalSearchCompleter()
    private let locationManager = CLLocationManager()

    override init() {
        super.init()
        searchCompleter.delegate = self
        searchCompleter.resultTypes = [.address, .pointOfInterest]

        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracyBest
        locationManager.requestWhenInUseAuthorization()
        locationManager.startUpdatingLocation()
    }
}

// MARK: - MKLocalSearchCompleter Delegate
extension LocationSearchCompleter: MKLocalSearchCompleterDelegate {
    func completerDidUpdateResults(_ completer: MKLocalSearchCompleter) {
        DispatchQueue.main.async {
            self.searchResults = completer.results
        }
    }

    func completer(_ completer: MKLocalSearchCompleter, didFailWithError error: Error) {
        print("Search completer error: \(error)")
    }
}

// MARK: - CLLocationManager Delegate
extension LocationSearchCompleter: CLLocationManagerDelegate {
    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }
        currentLocation = location.coordinate
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        print("Location manager error: \(error)")
    }
}

#Preview {
    LocationSearchView(
        selectedLocation: .constant(""),
        selectedCoordinates: .constant(nil),
        isPresented: .constant(true)
    )
}