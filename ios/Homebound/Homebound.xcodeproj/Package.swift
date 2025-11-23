// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "HomeboundPackages",
    defaultLocalization: "en",
    platforms: [
        .iOS(.v15)
    ],
    products: [
        // A convenience umbrella library that re-exports GRDB for the app
        .library(name: "HomeboundDB", targets: ["HomeboundDB"])
    ],
    dependencies: [
        .package(url: "https://github.com/groue/GRDB.swift", from: "6.0.0")
    ],
    targets: [
        .target(
            name: "HomeboundDB",
            dependencies: [
                .product(name: "GRDB", package: "GRDB.swift")
            ]
        )
    ]
)
