import SwiftUI
import AppKit

/// Startup is driven from the app delegate rather than a view's `.task`.
///
/// This is load-bearing: with `LSUIElement` the app has no Dock icon and the
/// Window scene is not instantiated until someone opens it, so anything hung
/// off the window's lifecycle would never run. The menu bar has to show live
/// state from launch, before any window exists.
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let model = AppModel()

    func applicationDidFinishLaunching(_ notification: Notification) {
        model.start()
    }

    func applicationWillTerminate(_ notification: Notification) {
        model.shutdown()
    }
}

@main
struct AutoKekaApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

    var body: some Scene {
        // The reason for going native: live status in the menu bar instead of
        // a window you have to go find.
        MenuBarExtra {
            MenuBarView(model: delegate.model)
        } label: {
            MenuBarLabel(model: delegate.model)
        }
        .menuBarExtraStyle(.window)

        Window("Auto-Keka", id: "main") {
            MainView(model: delegate.model)
                .frame(minWidth: 460, minHeight: 520)
        }
        .windowResizability(.contentMinSize)
    }
}

/// Split out so it observes the model — the icon and elapsed time have to
/// redraw as state changes, which a plain inline closure would not do.
private struct MenuBarLabel: View {
    @ObservedObject var model: AppModel

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: model.statusSymbol)
            if model.connection == .connected, model.state.clockedIn {
                Text(model.workedTitle)
            }
        }
    }
}
