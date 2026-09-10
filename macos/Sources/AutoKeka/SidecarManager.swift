import Foundation

/// Owns the Python core process.
///
/// Two paths, in order of preference:
///  1. **Attach** — a core is already running (the cross-platform app, or a
///     previous launch of this one). Its handshake file is live, so we just
///     use it and leave the process alone.
///  2. **Spawn** — start our own `--serve` core and adopt it. Only a core we
///     started ourselves is terminated on quit.
final class SidecarManager {
    private(set) var info: SidecarInfo?
    private var ownedProcess: Process?

    static var handshakeURL: URL {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory,
                                                  in: .userDomainMask)[0]
        return appSupport.appendingPathComponent("Auto-Keka/sidecar.json")
    }

    // MARK: - Lifecycle

    func start() async throws -> SidecarInfo {
        if let existing = try? await attach() {
            self.info = existing
            return existing
        }
        let spawned = try await spawn()
        self.info = spawned
        return spawned
    }

    func stop() {
        // Never kill a core we merely attached to — the cross-platform app may
        // be relying on it, and its punch schedule certainly is.
        guard let proc = ownedProcess, proc.isRunning else { return }
        proc.terminate()
        ownedProcess = nil
    }

    // MARK: - Attach

    private func attach() async throws -> SidecarInfo {
        let data = try Data(contentsOf: Self.handshakeURL)
        let info = try JSONDecoder().decode(SidecarInfo.self, from: data)
        guard isAlive(pid: info.pid) else { throw SidecarError.stale }
        // A live PID is not proof the API answers — the file can outlive a
        // crash and the PID be recycled. Probe before trusting it.
        guard try await probe(info) else { throw SidecarError.stale }
        return info
    }

    private func isAlive(pid: Int32) -> Bool {
        // Signal 0 tests for existence without delivering anything.
        kill(pid, 0) == 0 || errno == EPERM
    }

    private func probe(_ info: SidecarInfo) async throws -> Bool {
        var c = URLComponents()
        c.scheme = "http"; c.host = "127.0.0.1"; c.port = info.port
        c.path = "/api/state"
        c.queryItems = [URLQueryItem(name: "t", value: info.token)]
        var req = URLRequest(url: c.url!)
        req.timeoutInterval = 2
        guard let (_, response) = try? await URLSession.shared.data(for: req),
              let http = response as? HTTPURLResponse else { return false }
        return http.statusCode == 200
    }

    // MARK: - Spawn

    private func spawn() async throws -> SidecarInfo {
        let proc = Process()
        let (executable, arguments) = try Self.resolveCore()
        proc.executableURL = executable
        proc.arguments = arguments

        let pipe = Pipe()
        proc.standardOutput = pipe
        try proc.run()
        ownedProcess = proc

        // The core prints its handshake JSON as the first stdout line. Reading
        // that is faster and less racy than polling for the file to appear.
        let handle = pipe.fileHandleForReading
        let deadline = Date().addingTimeInterval(20)
        var buffer = Data()
        while Date() < deadline {
            let chunk = handle.availableData
            if chunk.isEmpty { try await Task.sleep(nanoseconds: 100_000_000); continue }
            buffer.append(chunk)
            guard let text = String(data: buffer, encoding: .utf8) else { continue }
            for line in text.split(separator: "\n") {
                if let data = line.data(using: .utf8),
                   let info = try? JSONDecoder().decode(SidecarInfo.self, from: data) {
                    return info
                }
            }
        }
        proc.terminate()
        ownedProcess = nil
        throw SidecarError.handshakeTimeout
    }

    /// Bundled core first; falls back to the repo checkout so the app is
    /// runnable during development without a full packaging step.
    private static func resolveCore() throws -> (URL, [String]) {
        let bundled = Bundle.main.bundleURL
            .appendingPathComponent("Contents/MacOS/auto-keka-core")
        // --exit-with-parent is not optional in practice: applicationWillTerminate
        // does not run on SIGKILL, force-quit, or a crash, so without the core
        // watching us it would be orphaned holding a port and token.
        if FileManager.default.isExecutableFile(atPath: bundled.path) {
            return (bundled, ["--serve", "--exit-with-parent"])
        }
        // Dev fallback: env var first (running from a terminal), then the path
        // build-app.sh stamps into Info.plist (launched from Finder, where no
        // environment is inherited).
        let repoCandidates = [
            ProcessInfo.processInfo.environment["AUTOKEKA_REPO"],
            Bundle.main.object(forInfoDictionaryKey: "AutoKekaRepo") as? String,
        ].compactMap { $0 }

        for repo in repoCandidates {
            let python = URL(fileURLWithPath: repo).appendingPathComponent(".venv/bin/python")
            let script = URL(fileURLWithPath: repo).appendingPathComponent("keka_ui.py")
            if FileManager.default.isExecutableFile(atPath: python.path) {
                return (python, [script.path, "--serve", "--exit-with-parent"])
            }
        }
        throw SidecarError.coreNotFound
    }

    enum SidecarError: LocalizedError {
        case stale, handshakeTimeout, coreNotFound

        var errorDescription: String? {
            switch self {
            case .stale:
                return "Found a stale handshake — no core is answering on that port."
            case .handshakeTimeout:
                return "The core did not report a port within 20s."
            case .coreNotFound:
                return "No bundled core, and AUTOKEKA_REPO is unset or has no .venv."
            }
        }
    }
}
