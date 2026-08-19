import Foundation
import SwiftUI

/// Single source of truth for the UI. Owns the sidecar, the client, and the
/// event-stream reconnect loop.
@MainActor
final class AppModel: ObservableObject {
    @Published private(set) var state = KekaState.placeholder
    @Published private(set) var connection: Connection = .connecting
    @Published private(set) var lastLog: String = ""
    @Published var otpRequired = false
    @Published var otpIsRetry = false
    @Published var busyAction: String?
    @Published var errorMessage: String?

    /// Ticks once a second purely so the live timer redraws; the authoritative
    /// clock-in time comes from the core, never from here.
    @Published private(set) var now = Date()

    enum Connection: Equatable {
        case connecting, connected, failed(String)
    }

    private let sidecar = SidecarManager()
    private var client: KekaClient?
    private var listenTask: Task<Void, Never>?
    private var tickTask: Task<Void, Never>?

    // MARK: - Lifecycle

    private var started = false

    func start() {
        guard !started else { return }   // delegate owns startup; never double-run
        started = true
        tickTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                await MainActor.run { self?.now = Date() }
            }
        }
        connect()
    }

    func shutdown() {
        listenTask?.cancel()
        tickTask?.cancel()
        sidecar.stop()
    }

    private func connect() {
        connection = .connecting
        listenTask?.cancel()
        listenTask = Task { [weak self] in
            guard let self else { return }
            do {
                let info = try await self.sidecar.start()
                let client = KekaClient(info: info)
                self.client = client
                let snapshot = try await client.fetchState()
                self.state = snapshot
                self.connection = .connected
                await self.listen(client)
            } catch {
                self.connection = .failed(error.localizedDescription)
                // Back off, then retry — the core may still be booting.
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                if !Task.isCancelled { self.connect() }
            }
        }
    }

    /// Consumes the SSE stream. If it drops (core restarted, machine slept),
    /// fall back to `connect()` which re-runs discovery — the port and token
    /// change whenever the core restarts, so reusing the old client is wrong.
    private func listen(_ client: KekaClient) async {
        do {
            for try await event in await client.events() {
                switch event {
                case .state(let s):
                    state = s
                case .otpRequired(let retry):
                    otpRequired = true
                    otpIsRetry = retry
                case .otpDone:
                    otpRequired = false
                case .log(let msg):
                    lastLog = msg
                }
            }
            // Clean end of stream still means we lost the core.
            if !Task.isCancelled { connect() }
        } catch {
            if !Task.isCancelled {
                connection = .failed(error.localizedDescription)
                connect()
            }
        }
    }

    // MARK: - Actions

    func clockIn()         { run("clock_in") }
    func clockOut()        { run("clock_out") }
    func refreshSession()  { run("refresh_session") }

    func submitOTP(_ code: String) {
        run("submit_otp", body: ["code": code])
    }

    private func run(_ action: String, body: [String: Any]? = nil) {
        guard let client, busyAction == nil else { return }
        busyAction = action
        errorMessage = nil
        Task { [weak self] in
            defer { Task { @MainActor in self?.busyAction = nil } }
            do {
                let result = try await client.post(action, body: body)
                if let ok = result.ok, !ok {
                    await MainActor.run { self?.errorMessage = result.message ?? "Action failed." }
                }
                // The core pushes a fresh state over SSE after every action, so
                // there is deliberately no refetch here.
            } catch {
                await MainActor.run { self?.errorMessage = error.localizedDescription }
            }
        }
    }

    // MARK: - Presentation helpers

    /// `7h 42m` — the menu-bar title, kept short enough not to crowd the bar.
    var workedTitle: String {
        guard let seconds = state.workedSeconds(now: now) else { return "--:--" }
        let h = Int(seconds) / 3600
        let m = (Int(seconds) % 3600) / 60
        return h > 0 ? "\(h)h \(m)m" : "\(m)m"
    }

    var statusSymbol: String {
        switch connection {
        case .connected:  return state.clockedIn ? "clock.fill" : "clock"
        case .connecting: return "clock.badge.questionmark"
        case .failed:     return "clock.badge.exclamationmark"
        }
    }

    var statusLine: String {
        switch connection {
        case .failed(let why): return why
        case .connecting:      return "Connecting to the core…"
        case .connected:
            if state.clockedIn {
                return "Clocked in since \(Self.time(state.clockInDate))"
            } else if state.clockOutDate != nil {
                return "Clocked out at \(Self.time(state.clockOutDate))"
            }
            return "Not clocked in today"
        }
    }

    private static func time(_ date: Date?) -> String {
        guard let date else { return "--:--" }
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        return f.string(from: date)
    }
}
