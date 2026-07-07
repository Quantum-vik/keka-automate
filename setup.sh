#!/usr/bin/env bash
#
# Keka Automate — one-shot setup. Clone the repo, then just run:
#
#     ./setup.sh
#
# It does EVERYTHING: Python venv, dependencies, Playwright's Chromium,
# the tesseract OCR engine, your .env credentials, the one-time OTP login,
# and the schedule (cron on Linux, launchd on macOS).
#
# Safe to re-run — it skips steps that are already done. Works on Linux & macOS.
set -euo pipefail

KEKA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$KEKA"

# ── options ───────────────────────────────────────────────────────────────────
DO_LOGIN_STEP=1
DO_SCHEDULE_STEP=1
PHASE="all"     # all | light | heavy  (the app installs 'light' then 'heavy')
while [ $# -gt 0 ]; do
    case "$1" in
        --no-login)    DO_LOGIN_STEP=0 ;;
        --no-schedule) DO_SCHEDULE_STEP=0 ;;
        --phase)       PHASE="${2:-all}"; shift ;;
        --phase=*)     PHASE="${1#*=}" ;;
        -h|--help)
            cat <<EOF
Keka Automate setup (Linux/macOS). Usage: ./setup.sh [options]
  --no-login      Skip the interactive OTP login step
  --no-schedule   Skip installing the cron/launchd schedule
  --phase P       Install only part of the deps: 'light' (venv + pip packages,
                  enough to open the app) or 'heavy' (Chromium + tesseract).
                  Default 'all' also does .env, login and schedule.
  -h, --help      Show this help
Runs everything by default: venv, deps, Chromium, tesseract, .env, login, schedule.
EOF
            exit 0 ;;
        *) echo "Unknown option: $1 (try --help)"; exit 1 ;;
    esac
    shift
done

case "$PHASE" in all|light|heavy) ;; *) echo "Bad --phase: $PHASE (use all|light|heavy)"; exit 1 ;; esac
# want <group>  →  true if this run should do that group of steps.
#   light = Python/venv/pip (+ native-window libs);  heavy = Chromium + tesseract;
#   final = .env + login + schedule (only in the default 'all' phase).
want() {
    case "$1" in
        light) [ "$PHASE" = all ] || [ "$PHASE" = light ] ;;
        heavy) [ "$PHASE" = all ] || [ "$PHASE" = heavy ] ;;
        final) [ "$PHASE" = all ] ;;
    esac
}

# ── pretty output ─────────────────────────────────────────────────────────────
b() { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }      # step header
ok() { printf "  \033[1;32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[1;33m!\033[0m %s\n" "$*"; }
die() { printf "  \033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

OS="$(uname -s)"   # Linux or Darwin

# Keep apt fully non-interactive. `playwright install --with-deps` shells out to
# apt, which can otherwise stall on a tzdata timezone prompt on a fresh/minimal
# Linux box (a real hang, seen in container testing).
if [ "$OS" = "Linux" ]; then
    export DEBIAN_FRONTEND=noninteractive
fi

VENV_PY=".venv/bin/python"   # always defined (heavy phase needs it too)

# ── 1-3. Light deps: Python + venv + pip packages ─────────────────────────────
if want light; then
# ── 1. Python ─────────────────────────────────────────────────────────────────
b "Checking Python"
PYBIN="$(command -v python3 || true)"
[ -n "$PYBIN" ] || die "python3 not found. Install Python 3.9+ and re-run."
ok "$($PYBIN --version)"

# ── 2. Virtual environment ────────────────────────────────────────────────────
b "Creating virtual environment (.venv)"
if [ ! -x ".venv/bin/python" ]; then
    "$PYBIN" -m venv .venv
    ok "created .venv"
else
    ok ".venv already exists"
fi

# ── 3. Python dependencies ────────────────────────────────────────────────────
b "Installing Python dependencies"
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -r requirements.txt
ok "playwright, pywebview, pytesseract, pillow installed"
fi  # want light

if want heavy; then
# ── 4. Playwright Chromium (+ system libs on Linux) ───────────────────────────
b "Installing Playwright's Chromium browser"
if [ "$OS" = "Linux" ]; then
    if command -v pacman >/dev/null 2>&1; then
        # Arch isn't supported by `playwright install-deps` — install libs via pacman.
        "$VENV_PY" -m playwright install chromium
        warn "Arch detected. If the browser fails to launch, install libs manually:"
        warn "  sudo pacman -S --needed nss nspr atk at-spi2-core libcups libxcomposite libxdamage libxrandr libxkbcommon gtk3 alsa-lib"
    elif command -v sudo >/dev/null 2>&1; then
        "$VENV_PY" -m playwright install --with-deps chromium || {
            warn "Couldn't auto-install system libs. Run:  sudo $VENV_PY -m playwright install-deps chromium"
            "$VENV_PY" -m playwright install chromium
        }
    else
        "$VENV_PY" -m playwright install chromium
        warn "No sudo — if the browser fails to launch, install system libs:  $VENV_PY -m playwright install-deps chromium"
    fi
else
    "$VENV_PY" -m playwright install chromium
fi
ok "Chromium ready"

# ── 5. System packages: tesseract (+eng data), tkinter, zenity, libnotify ─────
# tesseract reads the captcha; the English data pack is a SEPARATE package on
# Debian/Fedora. tkinter/zenity power the reauth dialog; libnotify the alerts.
b "Installing system packages (OCR + desktop alerts)"
if [ "$OS" = "Darwin" ]; then
    if command -v tesseract >/dev/null 2>&1; then
        ok "tesseract present: $(tesseract --version 2>&1 | head -1)"
    else
        command -v brew >/dev/null 2>&1 && brew install tesseract \
            || die "Install Homebrew, then: brew install tesseract"
    fi
    ok "macOS uses osascript for alerts — nothing else needed"
elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y tesseract-ocr tesseract-ocr-eng python3-tk zenity libnotify-bin
    ok "installed via apt"
elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y tesseract python3-tkinter zenity libnotify
    ok "installed via dnf"
elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y tesseract python3-tkinter zenity libnotify
    ok "installed via yum"
elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --needed --noconfirm tesseract tesseract-data-eng tk zenity libnotify
    ok "installed via pacman"
elif command -v zypper >/dev/null 2>&1; then
    sudo zypper install -y tesseract-ocr python3-tk zenity libnotify-tools
    ok "installed via zypper"
else
    command -v tesseract >/dev/null 2>&1 \
        || die "No known package manager. Install tesseract (+English data), python3-tk, zenity, libnotify manually."
    warn "Unknown package manager — assuming tesseract + tkinter + zenity are already present."
fi

# Native desktop window (pywebview → WebKitGTK) on Linux. Best-effort: if these
# don't install, the UI automatically falls back to opening in your browser.
if [ "$OS" = "Linux" ]; then
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get install -y python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 2>/dev/null \
            || sudo apt-get install -y python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.0 2>/dev/null \
            || warn "WebKitGTK not installed — the UI will open in your browser instead."
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y python3-gobject gtk3 webkit2gtk4.1 2>/dev/null \
            || sudo dnf install -y python3-gobject gtk3 webkit2gtk3 2>/dev/null \
            || warn "WebKitGTK not installed — the UI will open in your browser instead."
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --needed --noconfirm python-gobject gtk3 webkit2gtk 2>/dev/null \
            || warn "WebKitGTK not installed — the UI will open in your browser instead."
    else
        warn "For a native UI window install WebKitGTK + python-gobject; otherwise the UI opens in your browser."
    fi
    ok "native-window deps attempted (browser fallback always works)"
fi
fi  # want heavy

if want final; then
# ── 6. Credentials (.env) ─────────────────────────────────────────────────────
b "Setting up credentials (.env)"
if [ -f ".env" ] && grep -q "KEKA_PASSWORD=" .env && ! grep -q "KEKA_PASSWORD=$" .env; then
    ok ".env already present — leaving it as is"
else
    echo "  Enter your Keka details (stored locally in .env, never uploaded):"
    read -rp "    Company Keka URL (e.g. https://acme.keka.com): " KURL || true
    read -rp "    Email: " KMAIL || true
    read -rsp "    Password: " KPASS || true; echo
    cat > .env <<EOF
# Keka credentials + tenant. Private — keep chmod 600.
KEKA_BASE_URL=$KURL
KEKA_EMAIL=$KMAIL
KEKA_PASSWORD=$KPASS
EOF
    chmod 600 .env
    ok ".env created (chmod 600)"
fi

# ── 7. One-time login (you enter the OTP) ─────────────────────────────────────
b "Logging in to Keka (one-time OTP)"
if [ "$DO_LOGIN_STEP" = "0" ]; then
    ok "skipped (--no-login)"
else
    DO_LOGIN=1
    if [ -f "session.json" ]; then
        read -rp "  A saved session already exists. Re-do the login? [y/N] " ans || true
        case "${ans:-N}" in y|Y) DO_LOGIN=1 ;; *) DO_LOGIN=0 ;; esac
    fi
    if [ "$DO_LOGIN" = "1" ]; then
        echo "  A browser will open. Complete any 2FA / OTP prompt, then it saves your session."
        "$VENV_PY" keka_setup.py
        [ -f "session.json" ] || die "Login didn't complete — no session saved. Re-run ./setup.sh"
        ok "session saved"
    else
        ok "keeping existing session"
    fi
fi

# ── 8. Schedule it ────────────────────────────────────────────────────────────
b "Installing the schedule"
if [ "$DO_SCHEDULE_STEP" = "0" ]; then
    ok "skipped (--no-schedule)"
elif [ "$OS" = "Darwin" ]; then
    bash scheduling/install_macos.sh
elif [ "$OS" = "Linux" ]; then
    bash scheduling/install_linux.sh
else
    warn "Unknown OS — set up scheduling manually (see README)."
fi
fi  # want final

# ── done ──────────────────────────────────────────────────────────────────────
if [ "$PHASE" = "all" ]; then
    printf "\n\033[1;32m🎉 All set!\033[0m Keka Automate will clock you in and out on your schedule, Mon–Fri.\n"
    printf "   Logs:        %s/logs/\n" "$KEKA"
    printf "   Test it now: %s keka_punch_in.py   (then keka_punch_out.py)\n\n" "$VENV_PY"
else
    printf "\n\033[1;32m✓ %s dependencies installed.\033[0m\n" "$PHASE"
fi
