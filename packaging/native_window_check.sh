#!/usr/bin/env bash
#
# Linux: does a COMPILED Auto-Keka open its native WebKitGTK window, or does it
# silently fall back to the browser?
#
#   packaging/native_window_check.sh <path-to-binary> [seconds]
#
# Launches the dashboard (needs a display — use `xvfb-run -a` in CI) and passes
# only if the app never printed its browser-fallback line AND WebKitGTK is
# actually mapped into one of its processes. The GTK stack comes from THIS
# machine, so run it on the oldest and a newer distro to prove the binary isn't
# tied to the build host's GLib.
set -euo pipefail

BIN="${1:?usage: native_window_check.sh <binary> [seconds]}"
WAIT="${2:-20}"
[ -x "$BIN" ] || { echo "native: not executable: $BIN"; exit 1; }

log="$(mktemp)"
# Throwaway data dir + a no-op browser: the check must never touch the real
# user's config, and a fallback must not pop a browser tab.
data="$(mktemp -d)"
XDG_DATA_HOME="$data" BROWSER=true "$BIN" > "$log" 2>&1 &
pid=$!
cleanup() {
  pkill -P "$pid" 2>/dev/null || true
  kill "$pid" 2>/dev/null || true
  # The onefile launcher waits for its child to wind down; don't leave orphans.
  for _ in $(seq 1 10); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  pkill -9 -P "$pid" 2>/dev/null || true
  kill -9 "$pid" 2>/dev/null || true
  rm -rf "$log" "$data"
}
trap cleanup EXIT

webkit=""
for _ in $(seq 1 "$WAIT"); do
  sleep 1
  kill -0 "$pid" 2>/dev/null || { echo "native FAIL: app exited early"; cat "$log"; exit 1; }
  grep -q "native window unavailable" "$log" && break
  # A onefile binary re-executes itself from a temp dir, so look at the whole tree.
  for p in "$pid" $(pgrep -P "$pid" || true); do
    if grep -q libwebkit2gtk "/proc/$p/maps" 2>/dev/null; then webkit="$p"; fi
  done
  [ -n "$webkit" ] && break
done

if grep -q "native window unavailable" "$log"; then
  echo "native FAIL: fell back to the browser"; cat "$log"; exit 1
fi
[ -n "$webkit" ] || { echo "native FAIL: WebKitGTK never loaded within ${WAIT}s"; cat "$log"; exit 1; }
echo "native: OK (WebKitGTK loaded in pid $webkit: $(grep -o '/[^ ]*libwebkit2gtk[^ ]*' "/proc/$webkit/maps" | head -1))"
