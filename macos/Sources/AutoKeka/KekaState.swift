import Foundation

/// Mirrors the JSON returned by `GET /api/state` on the Python core.
///
/// The Python side sends epoch **milliseconds** for timestamps and uses `0`
/// (not null) to mean "never happened", so both are normalised here rather
/// than leaking that convention into the views.
struct KekaState: Codable, Equatable {
    var licensed: Bool
    var licenseName: String
    var clockedIn: Bool
    var clockInAt: Double
    var clockOutAt: Double
    var scheduleIn: String
    var scheduleOut: String
    var sessionDaysLeft: Int
    var sessionAlive: Bool
    var tokenExpiresAt: Double
    var week: [WeekDay]
    var activity: [ActivityEntry]
    var depsReady: Bool
    var onboarded: Bool
    var config: Config

    struct WeekDay: Codable, Equatable, Identifiable {
        var day: String
        var date: String
        var `in`: String
        var out: String
        var today: Bool
        var dim: Bool
        var id: String { "\(day)-\(date)" }
    }

    struct ActivityEntry: Codable, Equatable, Identifiable {
        var time: String
        var msg: String
        var kind: String
        var date: String?
        var id: String { "\(date ?? "")-\(time)-\(msg)" }
    }

    struct Config: Codable, Equatable {
        var url: String?
        var email: String?
    }

    // MARK: - Derived

    var clockInDate: Date? { Self.date(fromMillis: clockInAt) }
    var clockOutDate: Date? { Self.date(fromMillis: clockOutAt) }

    /// Seconds worked today. Counts up live while clocked in, otherwise the
    /// closed in→out span. Nil when today has no clock-in yet.
    func workedSeconds(now: Date = Date()) -> TimeInterval? {
        guard let start = clockInDate else { return nil }
        if clockedIn { return max(0, now.timeIntervalSince(start)) }
        guard let end = clockOutDate, end > start else { return nil }
        return end.timeIntervalSince(start)
    }

    private static func date(fromMillis ms: Double) -> Date? {
        // Python sends 0 for "no punch recorded", which must not become 1970.
        guard ms > 0 else { return nil }
        return Date(timeIntervalSince1970: ms / 1000)
    }

    static let placeholder = KekaState(
        licensed: false, licenseName: "", clockedIn: false,
        clockInAt: 0, clockOutAt: 0, scheduleIn: "--:--", scheduleOut: "--:--",
        sessionDaysLeft: 0, sessionAlive: false, tokenExpiresAt: 0,
        week: [], activity: [], depsReady: false, onboarded: false,
        config: Config(url: nil, email: nil)
    )
}

/// Handshake the core writes to `~/Library/Application Support/Auto-Keka/sidecar.json`.
struct SidecarInfo: Codable {
    var port: Int
    var token: String
    var pid: Int32
}

/// Result envelope shared by every `POST /api/<action>` on the Python side.
struct ActionResult: Codable {
    var ok: Bool?
    var message: String?
}
