import Foundation
import UserNotifications

/// Native notifications for the things that happen while the app is not in
/// front of you — which, for a menu-bar utility driven by a schedule, is
/// essentially everything that matters.
@MainActor
final class NotificationManager {
    private var authorized = false

    func requestAuthorization() async {
        do {
            authorized = try await UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .sound])
        } catch {
            // Denied or unavailable (unsigned bundle, notifications off) — the
            // app must keep working regardless, so this is not fatal.
            authorized = false
        }
    }

    func post(title: String, body: String, sound: Bool = false) {
        guard authorized else { return }
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        if sound { content.sound = .default }
        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil          // deliver immediately
        )
        UNUserNotificationCenter.current().add(request)
    }
}

/// Decides which state changes are worth interrupting someone for.
///
/// Deliberately narrow: a punch is a once-or-twice-a-day event and an OTP
/// prompt blocks the automation entirely, so those earn a notification.
/// Reconnects and routine state refreshes do not — the menu-bar icon already
/// carries that, and notifying on them would train the user to ignore us.
struct PunchTransition {
    private var lastClockedIn: Bool?
    private var lastOtpRequired = false

    enum Event {
        case clockedIn(at: String)
        case clockedOut(at: String)
        case otpNeeded(retry: Bool)
    }

    mutating func evaluate(state: KekaState, otpRequired: Bool) -> [Event] {
        var events: [Event] = []

        if let previous = lastClockedIn, previous != state.clockedIn {
            if state.clockedIn {
                events.append(.clockedIn(at: Self.time(state.clockInDate)))
            } else {
                events.append(.clockedOut(at: Self.time(state.clockOutDate)))
            }
        }
        lastClockedIn = state.clockedIn

        // Edge-triggered: only when the prompt first appears, not on every
        // state push while it stays up.
        if otpRequired && !lastOtpRequired {
            events.append(.otpNeeded(retry: false))
        }
        lastOtpRequired = otpRequired

        return events
    }

    private static func time(_ date: Date?) -> String {
        guard let date else { return "just now" }
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        return f.string(from: date)
    }
}
