#!/usr/bin/env bash
#
# Post-build correctness check for a COMPILED Auto-Keka artifact.
#
#   packaging/smoke_test.sh <path-to-binary>
#
# A binary can compile cleanly under Nuitka yet be broken at runtime — a missing
# include-module, an unbundled data dir (ui/), a bad entry point. This runs the
# real artifact and fails the release build BEFORE such a binary ever ships:
#   1. `--version` must print and exit 0  (proves it launches + all imports resolve)
#      and `--app-path` must name this binary (what the scheduler relaunches)
#   2. `--serve` must hand off a port+token, answer /api/state 200 with our
#      version, and serve the bundled dashboard HTML  (proves data bundling +
#      the whole backend actually work in the compiled build)
set -euo pipefail

BIN="${1:?usage: smoke_test.sh <binary>}"
[ -x "$BIN" ] || { echo "smoke: not executable: $BIN"; exit 1; }

echo "smoke: $BIN --version"
out="$("$BIN" --version)"
echo "  -> $out"
case "$out" in
  "Auto-Keka "*) ;;
  *) echo "smoke FAIL: unexpected --version output"; exit 1 ;;
esac

# Schedules, autostart and the punch buttons relaunch the app via --app-path's
# answer. It must be THIS binary and must outlive the process: a onefile build
# once named '<temp extraction dir>/python', which never existed.
echo "smoke: $BIN --app-path (what schedules and autostart launch)"
app="$("$BIN" --app-path)"
echo "  -> $app"
[ -f "$app" ] || { echo "smoke FAIL: --app-path is not a file: $app"; exit 1; }
real() { python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$1"; }
[ "$(real "$app")" = "$(real "$BIN")" ] || { echo "smoke FAIL: --app-path is not $BIN"; exit 1; }

echo "smoke: $BIN --serve (handshake + /api/state + dashboard)"
tmp="$(mktemp)"
"$BIN" --serve 0 > "$tmp" 2>/dev/null &
pid=$!
cleanup() { kill "$pid" 2>/dev/null || true; rm -f "$tmp" /tmp/ak_state.json /tmp/ak_index.html; }
trap cleanup EXIT

# The core prints its handshake JSON as the first stdout line. Wait up to ~30s.
port=""; token=""
for _ in $(seq 1 60); do
  line="$(head -n 1 "$tmp" 2>/dev/null || true)"
  if printf '%s' "$line" | grep -q '"port"'; then
    port="$(printf '%s' "$line" | sed -E 's/.*"port"[: ]+([0-9]+).*/\1/')"
    token="$(printf '%s' "$line" | sed -E 's/.*"token"[: ]+"([^"]+)".*/\1/')"
    break
  fi
  kill -0 "$pid" 2>/dev/null || { echo "smoke FAIL: --serve exited early"; cat "$tmp"; exit 1; }
  sleep 0.5
done
[ -n "$port" ] || { echo "smoke FAIL: no handshake from --serve"; cat "$tmp"; exit 1; }
echo "  -> port=$port"

code="$(curl -s -o /tmp/ak_state.json -w '%{http_code}' "http://127.0.0.1:$port/api/state?t=$token")"
[ "$code" = "200" ] || { echo "smoke FAIL: /api/state returned $code"; exit 1; }
grep -q '"version"' /tmp/ak_state.json || { echo "smoke FAIL: state has no version field"; exit 1; }

html="$(curl -s -o /tmp/ak_index.html -w '%{http_code}' "http://127.0.0.1:$port/?t=$token")"
[ "$html" = "200" ] || { echo "smoke FAIL: dashboard / returned $html"; exit 1; }
grep -q "Auto-Keka" /tmp/ak_index.html || { echo "smoke FAIL: served HTML is not the dashboard"; exit 1; }

echo "smoke: OK"
