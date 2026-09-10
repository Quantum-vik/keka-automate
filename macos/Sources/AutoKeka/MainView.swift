import SwiftUI

/// The full window: hero timer, this week's punches, and recent activity.
struct MainView: View {
    @ObservedObject var model: AppModel
    @State private var otpCode = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                hero
                if model.otpRequired { otpPrompt }
                week
                activity
            }
            .padding(20)
        }
        .background(.background)
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Circle()
                    .fill(model.state.clockedIn ? Color.green : Color.secondary)
                    .frame(width: 9, height: 9)
                Text(model.statusLine)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Spacer()
                if model.busyAction != nil { ProgressView().controlSize(.small) }
            }

            Text(model.workedTitle)
                .font(.system(size: 52, weight: .semibold, design: .rounded))
                .monospacedDigit()

            HStack(spacing: 10) {
                Button("Clock In", action: model.clockIn)
                    .disabled(model.state.clockedIn || model.busyAction != nil)
                Button("Clock Out", action: model.clockOut)
                    .disabled(!model.state.clockedIn || model.busyAction != nil)
                Button("Refresh Session", action: model.refreshSession)
                    .disabled(model.busyAction != nil)
            }
            .controlSize(.large)

            if let error = model.errorMessage {
                Text(error).font(.caption).foregroundStyle(.red)
            }
        }
    }

    /// Shown when the core signals that Keka wants an emailed OTP. Mirrors the
    /// web UI's prompt so both front-ends can satisfy the same login flow.
    private var otpPrompt: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(model.otpIsRetry ? "That code didn't work — try again"
                                   : "Enter the code Keka emailed you",
                  systemImage: "envelope.badge")
                .font(.subheadline)
            HStack {
                TextField("6-digit code", text: $otpCode)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 140)
                Button("Submit") {
                    model.submitOTP(otpCode)
                    otpCode = ""
                }
                .disabled(otpCode.isEmpty)
            }
        }
        .padding(14)
        .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
    }

    private var week: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("This Week").font(.headline)
            HStack(spacing: 8) {
                ForEach(model.state.week) { day in
                    VStack(spacing: 4) {
                        Text(day.day).font(.caption2).foregroundStyle(.secondary)
                        Text(day.in).font(.caption).monospacedDigit()
                        Text(day.out).font(.caption).monospacedDigit()
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(day.today ? Color.accentColor.opacity(0.12) : Color.clear,
                                in: RoundedRectangle(cornerRadius: 8))
                    .opacity(day.dim ? 0.45 : 1)
                }
            }
        }
    }

    private var activity: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Activity").font(.headline)
            if model.state.activity.isEmpty {
                Text("Nothing yet today.").font(.caption).foregroundStyle(.secondary)
            } else {
                ForEach(model.state.activity.prefix(12)) { entry in
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        Text(entry.time)
                            .font(.caption).monospacedDigit()
                            .foregroundStyle(.secondary)
                            .frame(width: 44, alignment: .leading)
                        Text(entry.msg).font(.caption)
                        Spacer()
                    }
                }
            }
        }
    }
}
