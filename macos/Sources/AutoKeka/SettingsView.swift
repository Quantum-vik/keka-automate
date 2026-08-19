import SwiftUI

/// Native settings: Keka credentials, punch schedule, and launch-at-login.
///
/// Credentials are posted straight to the core (`save_creds`) and never held
/// or cached on the Swift side — the core owns that file and its 0600 mode.
struct SettingsView: View {
    @ObservedObject var model: AppModel

    @State private var url = ""
    @State private var email = ""
    @State private var password = ""
    @State private var scheduleIn = ""
    @State private var scheduleOut = ""
    @State private var launchAtLogin = LoginItem.isEnabled
    @State private var loginItemError: String?
    @State private var savedNote: String?

    var body: some View {
        Form {
            Section("Keka Account") {
                TextField("Portal URL", text: $url, prompt: Text("https://company.keka.com"))
                TextField("Email", text: $email)
                SecureField("Password", text: $password,
                            prompt: Text(password.isEmpty ? "unchanged" : ""))
                HStack {
                    Spacer()
                    Button("Save Credentials") { saveCreds() }
                        .disabled(url.isEmpty || email.isEmpty || model.busyAction != nil)
                }
                Text("Leave the password blank to keep the one already stored.")
                    .font(.caption).foregroundStyle(.secondary)
            }

            Section("Schedule") {
                HStack {
                    TextField("Clock in", text: $scheduleIn, prompt: Text("09:00"))
                    TextField("Clock out", text: $scheduleOut, prompt: Text("18:00"))
                }
                HStack {
                    Spacer()
                    Button("Apply Schedule") { applySchedule() }
                        .disabled(scheduleIn.isEmpty || scheduleOut.isEmpty || model.busyAction != nil)
                }
                Text("Punches run from launchd agents installed by the core — "
                     + "they fire whether or not this app is open.")
                    .font(.caption).foregroundStyle(.secondary)
            }

            Section("General") {
                Toggle("Open Auto-Keka at login", isOn: $launchAtLogin)
                    .onChange(of: launchAtLogin) { newValue in
                        loginItemError = LoginItem.setEnabled(newValue)
                        if loginItemError != nil { launchAtLogin = LoginItem.isEnabled }
                    }
                if LoginItem.needsUserApproval {
                    Text("Enable Auto-Keka in System Settings → General → Login Items.")
                        .font(.caption).foregroundStyle(.orange)
                }
                if let loginItemError {
                    Text(loginItemError).font(.caption).foregroundStyle(.red)
                }
            }

            if let savedNote {
                Text(savedNote).font(.caption).foregroundStyle(.secondary)
            }
            if let error = model.errorMessage {
                Text(error).font(.caption).foregroundStyle(.red)
            }
        }
        .formStyle(.grouped)
        .frame(width: 440)
        .onAppear(perform: seedFromState)
        // The core is the source of truth; re-seed if it changes underneath us,
        // but never clobber something half-typed.
        .onChange(of: model.state) { _ in seedFromState(force: false) }
    }

    private func seedFromState() { seedFromState(force: true) }

    private func seedFromState(force: Bool) {
        if force || url.isEmpty        { url = model.state.config.url ?? "" }
        if force || email.isEmpty      { email = model.state.config.email ?? "" }
        if force || scheduleIn.isEmpty { scheduleIn = model.state.scheduleIn }
        if force || scheduleOut.isEmpty { scheduleOut = model.state.scheduleOut }
    }

    private func saveCreds() {
        var payload: [String: Any] = ["url": url, "email": email]
        if !password.isEmpty { payload["password"] = password }
        model.saveCredentials(payload)
        password = ""                      // never keep it in view state
        savedNote = "Credentials sent to the core."
    }

    private func applySchedule() {
        model.applySchedule(["in": scheduleIn, "out": scheduleOut])
        savedNote = "Schedule applied — launchd agents reinstalled."
    }
}
