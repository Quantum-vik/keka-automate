import Foundation
import ServiceManagement

/// Launch-at-login via `SMAppService` (macOS 13+).
///
/// Note this registers the *native client*, which is a separate concern from
/// the `com.keka.punchin` / `com.keka.punchout` launchd agents the Python core
/// installs. Those run the punches on schedule whether or not any UI is open,
/// and this must never interfere with them — clocking in cannot depend on
/// someone having a menu-bar app running.
enum LoginItem {
    static var isEnabled: Bool {
        SMAppService.mainApp.status == .enabled
    }

    /// Returns nil on success, or a human-readable reason on failure.
    @discardableResult
    static func setEnabled(_ enabled: Bool) -> String? {
        do {
            if enabled {
                try SMAppService.mainApp.register()
            } else {
                try SMAppService.mainApp.unregister()
            }
            return nil
        } catch {
            return error.localizedDescription
        }
    }

    /// `requiresApproval` means macOS registered it but the user has it toggled
    /// off in System Settings → General → Login Items, so we should say so
    /// rather than silently showing an "on" switch that does nothing.
    static var needsUserApproval: Bool {
        SMAppService.mainApp.status == .requiresApproval
    }
}
