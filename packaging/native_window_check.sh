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

# The onefile dir is on the loader path, so any system library we ship SHADOWS
# the user's. That is invisible here — CI distros are older than or equal to the
# build host, so their GTK is always compatible with what we vendored — and it
# only breaks on newer ones (fontconfig >= 2.17: "libpangoft2 ... undefined
# symbol: FcConfigSetDefaultSubstitute"). Testing more distros just moves the
# goalposts, so assert the payload directly: the graphics/font/X11 stack must
# come from the user's system. Keep in sync with the nuitka-project block in
# keka_ui.py. OpenSSL is deliberately absent: Python's _ssl needs the version
# we built against, so it stays vendored.
payload="$(dirname "$(readlink -f "/proc/$webkit/exe")")"
banned=0
for lib in libglib-2.0.so libgobject-2.0.so libgio-2.0.so libgmodule-2.0.so \
           libgirepository-1.0.so libfontconfig.so libfreetype.so libpng16.so \
           libexpat.so libbrotlicommon.so libbrotlidec.so libbsd.so libmd.so \
           libffi.so libuuid.so libX11.so libXau.so libXdmcp.so libXext.so \
           libXft.so libXrender.so libXss.so libxcb.so; do
  # Wheel-vendored copies carry a hash (libfreetype-9fc94c80.so.6...) and are
  # private to their own module, so they cannot shadow anything. Only the bare
  # SONAME does, which is what "$lib"* matches and the hashed form does not.
  for hit in "$payload/$lib"*; do
    [ -e "$hit" ] || continue
    echo "native FAIL: payload ships $(basename "$hit") — it will shadow the user's"
    banned=1
  done
done
[ "$banned" -eq 0 ] || exit 1
echo "native: payload ships no shadowing system libs"
