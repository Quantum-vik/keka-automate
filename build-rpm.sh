#!/usr/bin/env bash
#
# One-command .rpm builder for Auto-Keka — builds a SELF-CONTAINED package.
#
#   ./build-rpm.sh
#
# It will:
#   1. Install rpm-build + rpmdevtools if they're missing (uses sudo).
#   2. Stage a clean copy of the source, then BUILD EVERYTHING INTO IT at build
#      time: a Python venv with all pip deps, and Playwright's Chromium browser.
#   3. Generate the app icon and run rpmbuild.
#
# The finished .rpm carries the venv + Chromium, and declares its system packages
# (tesseract, WebKitGTK, tkinter, …) as RPM Requires, so `dnf install` pulls them
# in once — the app then runs with NO first-run downloads and NO runtime setup.
#
# Output: dist/rpmbuild/RPMS/<arch>/auto-keka-<version>-1.*.rpm
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$REPO"
NAME="auto-keka"
SPEC="$REPO/packaging/rpm/auto-keka.spec"

# ── 1. Ensure rpmbuild is available ───────────────────────────────────────────
if ! command -v rpmbuild >/dev/null 2>&1; then
  echo "▶ rpmbuild not found — installing rpm-build + rpmdevtools…"
  if command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y rpm-build rpmdevtools
  elif command -v zypper >/dev/null 2>&1; then
    sudo zypper install -y rpm-build rpmdevtools
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y rpm-build rpmdevtools
  else
    echo "✗ No supported package manager found. Install 'rpm-build' manually."
    exit 1
  fi
fi

# ── 2. Version (single source of truth) ───────────────────────────────────────
VERSION="$(python3 -c 'import re,io;print(re.search(r"APP_VERSION\s*=\s*\"([^\"]+)\"", io.open("keka_common.py",encoding="utf-8").read()).group(1))')"
echo "▶ Building $NAME $VERSION"

TOP="$REPO/dist/rpmbuild"
rm -rf "$TOP"
mkdir -p "$TOP"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}

# ── 3. Stage the source tree (exclude VCS/build/venv/secrets) ─────────────────
STAGE="$REPO/dist/$NAME-$VERSION"
rm -rf "$STAGE"; mkdir -p "$STAGE"
rsync -a \
  --exclude '.git' --exclude '.github' \
  --exclude '.venv' --exclude 'dist' \
  --exclude '__pycache__' --exclude '*.pyc' \
  --exclude '.env' --exclude 'logs' \
  --exclude 'session.json' --exclude 'session.lock' --exclude 'license.key' \
  --exclude 'license_private.pem' \
  --exclude 'ms-playwright' \
  "$REPO"/ "$STAGE"/

# ── 3a. Bundle the Python venv (all pip deps) INTO the staged tree ─────────────
# Reuse setup.sh's light phase: it creates .venv, installs requirements.txt, and
# symlinks the system PyGObject (gi) in — no sudo, no system changes.
echo "▶ Building bundled venv (pip deps)…"
( cd "$STAGE" && bash setup.sh --phase light )

# ── 3b. Bundle Playwright's Chromium INTO the staged tree ──────────────────────
# Keep a persistent browser cache in dist/ so rebuilds don't re-download ~400 MB.
echo "▶ Bundling Playwright Chromium…"
BROWSER_CACHE="$REPO/dist/.browser-cache"
mkdir -p "$BROWSER_CACHE"
PLAYWRIGHT_BROWSERS_PATH="$BROWSER_CACHE" "$STAGE/.venv/bin/python" -m playwright install chromium
mkdir -p "$STAGE/ms-playwright"
rsync -a "$BROWSER_CACHE"/ "$STAGE/ms-playwright"/

# ── 3c. Trim the venv so it packages cleanly ──────────────────────────────────
# Drop console scripts (their shebangs would encode the build path) and caches —
# the app only ever runs '.venv/bin/python -m …', so the interpreter symlinks are
# all that's needed. This also avoids leaking the build path into RPM Requires.
find "$STAGE/.venv/bin" -maxdepth 1 -type f ! -name 'python*' -delete
find "$STAGE" -depth -type d -name '__pycache__' -exec rm -rf {} +

tar -czf "$TOP/SOURCES/$NAME-$VERSION.tar.gz" -C "$REPO/dist" "$NAME-$VERSION"

# ── 4. Extra sources: launcher, desktop entry, icon ───────────────────────────
cp "$REPO/packaging/rpm/auto-keka-launcher.sh" "$TOP/SOURCES/"
cp "$REPO/packaging/rpm/auto-keka.desktop"     "$TOP/SOURCES/"

echo "▶ Generating icon…"
python3 "$REPO/packaging/make_icon.py" "$TOP/SOURCES/auto-keka.png" 256 || {
  echo "  (Pillow unavailable — shipping a placeholder icon)"
  printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82' \
    > "$TOP/SOURCES/auto-keka.png"
}

# ── 5. Build ──────────────────────────────────────────────────────────────────
echo "▶ Running rpmbuild…"
rpmbuild \
  --define "_topdir $TOP" \
  --define "app_version $VERSION" \
  -bb "$SPEC"

RPM_PATH="$(find "$TOP/RPMS" -name '*.rpm' | head -1)"
echo ""
echo "✓ Built RPM:"
echo "  $RPM_PATH"
echo ""
echo "Install it with:"
echo "  sudo dnf install \"$RPM_PATH\""
