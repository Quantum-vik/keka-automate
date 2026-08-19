import SwiftUI

/// The dropdown behind the menu-bar icon: current status, the two punch
/// actions, and today's schedule. Deliberately small — anything that needs
/// scrolling belongs in the main window.
struct MenuBarView: View {
    @ObservedObject var model: AppModel
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header

            if case .failed(let why) = model.connection {
                Label(why, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Divider()
            actions
            Divider()
            schedule

            if let error = model.errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Divider()
            footer
        }
        .padding(14)
        .frame(width: 280)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(model.state.clockedIn ? model.workedTitle : "Not clocked in")
                .font(.system(size: 26, weight: .semibold, design: .rounded))
                .monospacedDigit()
            Text(model.statusLine)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var actions: some View {
        VStack(spacing: 6) {
            Button {
                model.clockIn()
            } label: {
                Label("Clock In", systemImage: "arrow.right.to.line")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .disabled(model.state.clockedIn || model.busyAction != nil)

            Button {
                model.clockOut()
            } label: {
                Label("Clock Out", systemImage: "arrow.left.to.line")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .disabled(!model.state.clockedIn || model.busyAction != nil)

            Button {
                model.refreshSession()
            } label: {
                Label("Refresh Session", systemImage: "arrow.clockwise")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .disabled(model.busyAction != nil)
        }
        .buttonStyle(.plain)
    }

    private var schedule: some View {
        VStack(alignment: .leading, spacing: 4) {
            row("Scheduled", "\(model.state.scheduleIn) → \(model.state.scheduleOut)")
            row("Session", model.state.sessionAlive
                ? "valid · \(model.state.sessionDaysLeft)d device pass"
                : "expired")
            if !model.lastLog.isEmpty {
                Text(model.lastLog)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Spacer()
            Text(value).font(.caption).monospacedDigit()
        }
    }

    private var footer: some View {
        HStack {
            Button("Open Window") { openWindow(id: "main") }
            Spacer()
            Button("Quit") { NSApplication.shared.terminate(nil) }
        }
        .buttonStyle(.plain)
        .font(.caption)
        .foregroundStyle(.secondary)
    }
}
