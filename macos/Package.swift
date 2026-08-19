// swift-tools-version:5.9
import PackageDescription

// Swift 5 language mode on purpose: the app is a thin UI over an HTTP API and
// gains nothing from strict-concurrency checking, which would otherwise force
// Sendable annotations through every SwiftUI view for no real safety win here.
let package = Package(
    name: "AutoKeka",
    platforms: [
        // MenuBarExtra — the whole point of going native — needs macOS 13.
        .macOS(.v13)
    ],
    targets: [
        .executableTarget(
            name: "AutoKeka",
            path: "Sources/AutoKeka"
        )
    ]
)
