import Foundation

/// Talks to the Python core over the same token-authed HTTP + SSE API the
/// phone remote already uses:
///
///   GET  /api/state    -> full snapshot
///   GET  /events       -> text/event-stream (state / otp / otpDone / log)
///   POST /api/<action> -> clock_in, clock_out, refresh_session, submit_otp, …
///
/// Auth is a `?t=<token>` query parameter; the core answers 401 without it.
actor KekaClient {
    private let info: SidecarInfo
    private let session: URLSession

    init(info: SidecarInfo) {
        self.info = info
        let cfg = URLSessionConfiguration.ephemeral
        // The SSE stream is deliberately long-lived, so no resource timeout.
        cfg.timeoutIntervalForRequest = 30
        cfg.timeoutIntervalForResource = .infinity
        self.session = URLSession(configuration: cfg)
    }

    private func url(_ path: String) -> URL {
        var c = URLComponents()
        c.scheme = "http"
        c.host = "127.0.0.1"
        c.port = info.port
        c.path = path
        c.queryItems = [URLQueryItem(name: "t", value: info.token)]
        return c.url!
    }

    // MARK: - Requests

    func fetchState() async throws -> KekaState {
        let (data, response) = try await session.data(from: url("/api/state"))
        try Self.check(response, data: data)
        return try JSONDecoder().decode(KekaState.self, from: data)
    }

    /// POSTs an action. `body` is encoded as JSON when present — `submit_otp`
    /// and `save_creds` need it, the punch actions do not.
    @discardableResult
    func post(_ action: String, body: [String: Any]? = nil) async throws -> ActionResult {
        var req = URLRequest(url: url("/api/\(action)"))
        req.httpMethod = "POST"
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await session.data(for: req)
        try Self.check(response, data: data)
        // Some actions return a bare state object rather than {ok, message}.
        return (try? JSONDecoder().decode(ActionResult.self, from: data))
            ?? ActionResult(ok: true, message: nil)
    }

    // MARK: - Event stream

    enum Event {
        case state(KekaState)
        case otpRequired(retry: Bool)
        case otpDone
        case log(String)
    }

    /// Consumes `/events` and yields decoded events until the stream drops.
    /// The caller is responsible for reconnecting — see `AppModel.listen()`.
    func events() -> AsyncThrowingStream<Event, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let (bytes, response) = try await session.bytes(from: url("/events"))
                    try Self.check(response, data: Data())
                    for try await line in bytes.lines {
                        // SSE frames arrive as `data: {...}`; anything else
                        // (comments, blank keepalives) is skipped.
                        guard line.hasPrefix("data:") else { continue }
                        let json = line.dropFirst(5).trimmingCharacters(in: .whitespaces)
                        guard let payload = json.data(using: .utf8),
                              let event = Self.decodeEvent(payload) else { continue }
                        continuation.yield(event)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    private static func decodeEvent(_ data: Data) -> Event? {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = obj["type"] as? String else { return nil }
        switch type {
        case "state":
            guard let raw = obj["state"],
                  let blob = try? JSONSerialization.data(withJSONObject: raw),
                  let state = try? JSONDecoder().decode(KekaState.self, from: blob)
            else { return nil }
            return .state(state)
        case "otp":
            return .otpRequired(retry: (obj["retry"] as? Bool) ?? false)
        case "otpDone":
            return .otpDone
        case "log":
            let entry = obj["entry"] as? [String: Any]
            return .log((entry?["msg"] as? String) ?? "")
        default:
            return nil
        }
    }

    // MARK: - Errors

    enum ClientError: LocalizedError {
        case unauthorized
        case http(Int)

        var errorDescription: String? {
            switch self {
            case .unauthorized:
                return "The core rejected our token — the sidecar was likely restarted."
            case .http(let code):
                return "The core returned HTTP \(code)."
            }
        }
    }

    private static func check(_ response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else { return }
        if http.statusCode == 401 { throw ClientError.unauthorized }
        guard (200..<300).contains(http.statusCode) else {
            throw ClientError.http(http.statusCode)
        }
    }
}
