# 🕘 Keka Automate

> Your robot coworker who never forgets to clock in. ☕

[![CI](https://github.com/Quantum-vik/keka-automate/actions/workflows/ci.yml/badge.svg)](https://github.com/Quantum-vik/keka-automate/actions/workflows/ci.yml)
![Platforms](https://img.shields.io/badge/tested-macOS%20%C2%B7%20Linux%20%C2%B7%20Windows-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)

Ever sprinted to your laptop at 9:01 AM just to hit **Web Clock-In**? Or gotten
home and realized you never clocked out? Yeah. This fixes that.

**Keka Automate** logs into your [Keka](https://www.keka.com/) HR portal and
punches you **in at 9 AM** and **out at 6 PM**, Monday to Friday — automatically,
in the background, on **macOS, Linux, and Windows**. It even solves the login
captcha itself. 🤖

> ✅ Every push is tested on real **macOS, Linux, and Windows** runners via GitHub
> Actions — installer, OCR, and the scheduling scripts all verified per-OS.

---

## ✨ The magic in one picture

```
   9:00 AM ──►  🤖 opens Keka  ──►  ✅ Clock-In     ──►  you're marked present
   6:00 PM ──►  🤖 opens Keka  ──►  ✅ Clock-Out    ──►  you're marked done
                        │
                        └─ session expired? ──► 🔓 re-logs in by itself
                                                 (solves captcha, no you needed)
```

You do **nothing** day-to-day. The only time it needs you is once every ~2 weeks
for a 10-second security code (more on that below 👇).

---

## 🚀 How to use it (start here)

**No terminal, no Python needed.** Auto-Keka ships as a single self-contained app.

**1 · Download the zip for your OS** and unzip it anywhere (Desktop is fine):

| OS | Zip | Run |
|----|-----|-----|
| 🍎 macOS   | `Auto-Keka-macos.zip`   | drag `Auto-Keka.app` to Applications, then open it |
| 🪟 Windows | `Auto-Keka-windows.zip` | double-click `Auto-Keka.exe` |
| 🐧 Linux   | `Auto-Keka-linux.zip`   | `chmod +x Auto-Keka && ./Auto-Keka` |

- **First run:** the app downloads its private browser engine automatically (one
  time, ~130 MB), shown live in a *"Setting up…"* panel. The captcha reader
  (tesseract) comes from your OS — the app tells you the one command if it's
  missing (**macOS** `brew install tesseract` · **Windows** [UB-Mannheim installer](https://github.com/UB-Mannheim/tesseract) · **Linux** `sudo apt install tesseract-ocr`).
- **Unknown-developer warning?** The app isn't code-signed, so your OS may warn once:
  **macOS** → right-click `Auto-Keka.app` → *Open* → *Open*. **Windows** → *More info*
  → *Run anyway*. After that it opens normally.

**2 · Follow the wizard** — it walks you through everything, in the window:
```
①  Activate your license key                      →  Continue
②  Enter your Keka URL · email · password         →  Continue
③  It signs you in automatically (solves captcha) →  📧 type the OTP from your email
④  Pick your clock-in & clock-out times           →  Finish
⑤  ✅ Done — the background schedule is armed
```

**That's it — it now runs itself.** It clocks you **in and out at your set times,
Mon–Fri**, in the background — *even when the app window is closed*, and it
**re-opens automatically when you log into your computer**. Any time, you can also:
- ☀️ **Clock In** / 🌙 **Clock Out** on demand (it never double-punches)
- 🔑 **Sign in again** right on the dashboard when the session expires (the app
  shows a real *"Session expired"* verdict, not a guess)
- 📱 **Control it from your phone** — Settings shows a QR code; scan it from an
  iPhone/Android on the same Wi-Fi to open the full dashboard (status, punch,
  and the OTP box) in your phone's browser
- Watch **This Week** (with per-day worked hours) + **Activity** to see what it's done
- Change times / credentials from the **⚙️ gear** (top-right) — 🌗 the whole UI
  follows your system light/dark theme
- **Every ~14 days** an OTP box pops again — enter a fresh code, set for another 2 weeks

> **Developers / running from source:** clone the repo and run the classic
> one-shot installer instead of the app: `./setup.sh` (macOS/Linux) or
> `powershell -ExecutionPolicy Bypass -File setup.ps1` (Windows). See
> **Running from source** and **Handy commands** below.

> **🐧 Linux note:** the OCR engine (tesseract) installs via your package manager,
> which needs `sudo`. If the in-app setup can't get root, it'll tell you — just run
> `./setup.sh --phase heavy` once in a terminal. macOS & Windows install with no
> admin rights.

---

## 🧠 Why this is trickier than it sounds

Keka doesn't just let a robot walk in. It throws up **three walls**:

| Wall | What it is | How we get past it |
|------|-----------|--------------------|
| 🔑 Password | Standard login | Stored safely in a local `.env` file |
| 🔡 Captcha | Squiggly text image | Read automatically with **OCR** (tesseract) |
| 📱 2FA / OTP | One-time code to your phone/email | **You** type it — *once every ~14 days* |

Here's the clever part: after you enter the OTP **once**, Keka hands out a
**"remember this device" pass that's good for ~14 days**. During those two weeks,
the robot can re-login all by itself (password + captcha, **no OTP**). So you go
from "log in every single day" → "tap a code roughly twice a month." 🎉

---

## 🎬 How it actually works

There are 5 small scripts. Think of them as a little crew:

| Script | Role | Nickname |
|--------|------|----------|
| `keka_setup.py` | Logs in + you enter the OTP once → saves your session | 🪪 The Bouncer |
| `keka_punch_in.py` | Clocks you IN | ☀️ Morning Person |
| `keka_punch_out.py` | Clocks you OUT | 🌙 Night Owl |
| `keka_check.py` | Watches the ~14-day pass; nudges you before it expires | 🐕 The Watchdog |
| `keka_common.py` | Shared brains (login, captcha, session, clicking) | 🧠 The Brain |

**The flow:**
1. **Once:** run `keka_setup.py` → it fills your password, reads the captcha, you
   type the OTP → your logged-in session is saved to `session.json`.
2. **Every day:** the punch scripts reuse that session and click the button. If
   the session went stale, they **quietly re-login themselves**.
3. **Every ~14 days:** the Watchdog notices the "remember me" pass is about to
   expire, **pops open the browser + a notification**, you type one OTP, and
   you're set for another two weeks.

That's it. Clock-in is a single click; clock-out is a two-click confirm; and if
you're already clocked in/out, it just shrugs and exits (no double-punching). 🙌

---

## 🖥️ The dashboard

A native **"liquid glass"** window (in the released binary it's already the
whole app; from source it's `keka_ui.py`) showing:
- ⏱️ **"Am I clocked in?"** hero with a live worked-time timer + workday progress
- ⏭️ **Next scheduled** punch countdown and a **real session-health verdict** —
  it decodes the saved login token's own expiry (plus a live probe), so
  "Session expired" means expired, and a **Sign in again (OTP)** button appears
  right on the card
- 🗓️ **This week** clock-in/out strip (with per-day worked hours) and a live,
  scrollable **activity** feed
- ☀️🌙 **Clock in / out** buttons (with busy states) and 🔑 **Refresh session**
- 📱 A **Phone remote** QR code in Settings — scan it to drive the whole
  dashboard from your phone over the LAN (token-protected)
- 🌗 **Dark mode** that follows your system theme, and native time pickers
- 🔐 A **Settings** sheet (gear icon) for Keka URL / email / password and
  clock-in / clock-out times
- When Keka needs the 2FA code, an **OTP box appears right in the app** — read
  the code from your email, type it in; login finishes headlessly (no browser popup).

**How it renders (cross-platform):** a native window via
[pywebview](https://pywebview.flowlib.org/) — macOS **WebKit**, Windows
**WebView2**, Linux **WebKitGTK**. If a machine has no webview backend, it
automatically **falls back to opening the same dashboard in your default
browser**, so it works everywhere. On macOS/Windows the app also brands itself
("Auto-Keka" + icon in the Dock/taskbar, not "python"). Every action is recorded
in `logs/history.jsonl` so you can see previous sessions.

---

## 📱 Phone remote

The dashboard runs a small token-protected web server on your LAN so you can
control Auto-Keka from your phone (the automation itself still runs on the
computer — this is a remote control, which is all iOS allows):

1. On the computer, open **Settings** → **Phone remote**.
2. Scan the QR code with your phone's camera (phone + computer on the same Wi-Fi).
3. The full dashboard opens in your phone browser — check status, clock in/out,
   and **type the ~14-day OTP** without walking back to the computer.

> 🔒 The link carries a private access token; every request needs it. It's plain
> HTTP on your local network — fine for home/office Wi-Fi; don't port-forward it
> to the internet (put [Tailscale](https://tailscale.com/) in front if you need
> access from anywhere). Override the port with `KEKA_REMOTE_PORT`.

---

## 🛠️ Running from source (developers)

Clone the repo, then run the installer for your OS. It does **everything**:
Python venv, dependencies, Chromium, tesseract (+ desktop packages on Linux),
your `.env`, the one-time OTP login, and the schedule. It's safe to re-run.

```bash
# 🍎 macOS  /  🐧 Linux
./setup.sh

# 🪟 Windows (in PowerShell)
powershell -ExecutionPolicy Bypass -File setup.ps1
```

That's the whole install. It'll prompt for your Keka URL / email / password, then
open a browser once for your OTP. Handy flags: `--no-login` / `--no-schedule`
(bash) or `-NoLogin` / `-NoSchedule` (PowerShell).

<details>
<summary>Prefer to do it by hand? (manual steps)</summary>

```bash
# 1) Python environment + libraries
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip
.venv/bin/python -m playwright install chromium

# 2) Install tesseract + desktop bits
#    macOS:    brew install tesseract
#    Linux:    sudo apt install tesseract-ocr tesseract-ocr-eng python3-tk zenity libnotify-bin
#    Windows:  winget install UB-Mannheim.TesseractOCR   (auto-detected)

# 3) Add your details to a .env file (see below) and log in once
.venv/bin/python keka_setup.py                     # a browser opens → type your OTP

# 4) Put it on autopilot — pick your OS
bash scheduling/install_macos.sh                                         # 🍎 macOS  (launchd)
bash scheduling/install_linux.sh                                         # 🐧 Linux  (cron)
powershell -ExecutionPolicy Bypass -File scheduling\install_windows.ps1  # 🪟 Windows (Task Scheduler)
```
</details>

### 🔐 Your `.env` file
Your settings live in a **per-user data folder** (so they survive app updates and
compiled builds — see `.env.example` in the repo for the full template):

| OS | Location |
|----|----------|
| 🍎 macOS   | `~/Library/Application Support/Auto-Keka/.env` |
| 🐧 Linux   | `~/.local/share/Auto-Keka/.env` |
| 🪟 Windows | `%APPDATA%\Auto-Keka\.env` |

```ini
KEKA_BASE_URL=https://your-company.keka.com
KEKA_EMAIL=you@company.com
KEKA_PASSWORD=your-password
KEKA_IN_TIME=09:00
KEKA_OUT_TIME=18:00
```

> 💡 The app's **Settings sheet** and the installers write this file for you — you
> only edit it by hand for headless setups. It's created `chmod 600` (owner-only)
> and **never uploaded anywhere**. A legacy `.env` next to the scripts is
> auto-migrated on first run.

---

## ⏰ The schedule

Same three jobs on every OS (set up by the installer for your platform):

| Job | When | What it does |
|-----|------|--------------|
| ☀️ Punch in  | Your `KEKA_IN_TIME` (default 9:00 AM), Mon–Fri | Clock in |
| 🌙 Punch out | Your `KEKA_OUT_TIME` (default 6:00 PM), Mon–Fri | Clock out |
| 🐕 Watchdog  | 10:00 AM daily + at login | Only bugs you if the ~14-day pass is about to expire |

**Under the hood, per OS:**
- 🍎 **macOS (launchd)** — re-runs missed jobs when your Mac wakes, and can pop
  the login browser. *No Full Disk Access needed.*
- 🐧 **Linux (cron)** — headless punches; the watchdog gets `DISPLAY` so the
  browser can appear.
- 🪟 **Windows (Task Scheduler)** — watchdog runs interactively so its window
  shows up.

📁 Logs land in `logs/` (same place on every OS): `keka_punch_in.log`,
`keka_punch_out.log`, `keka_reauth.log`.

---

## 🎮 Handy commands

**Run something right now (test it):**
```bash
.venv/bin/python keka_doctor.py       # 🩺 health check: deps, config, session token, schedule
.venv/bin/python keka_punch_in.py     # clock in now   (Windows: .venv\Scripts\python)
.venv/bin/python keka_punch_out.py    # clock out now
.venv/bin/python keka_setup.py        # force a fresh OTP login
.venv/bin/python keka_check.py        # run the watchdog check now
```

**Manage the schedule:**
```bash
# 🍎 macOS
launchctl list | grep keka                          # status
launchctl kickstart -k gui/$(id -u)/com.keka.punchin  # run now
bash scheduling/install_macos.sh                    # (re)install everything

# 🐧 Linux
crontab -l                                          # view jobs
crontab -l | grep -v 'keka_' | crontab -            # remove keka jobs

# 🪟 Windows
schtasks /Query /FO LIST /TN Keka\PunchIn           # status
schtasks /Delete /F /TN Keka\PunchIn                # remove (also PunchOut, Reauth, ReauthLogon)
```

---

## 🧩 Good to know

- 💤 **Your computer has to be awake** around 9 AM / 6 PM for the punch to fire.
  macOS runs missed jobs on the next wake; cron/Task Scheduler are stricter.
- 🔔 The first time the Watchdog alerts you, your OS may ask permission to show
  notifications — say yes. (There's also a pop-up dialog as a backup, so you
  won't miss it either way.)
- 🙅 **It never double-punches.** Already clocked in? It just exits quietly.

---

## 📁 What's in the box

```
bootstrap.py / .ps1    🥾  what the app runs FIRST — self-installs deps, then opens the UI
setup.sh / setup.ps1   🚀  one-command installer / dep engine (--phase light|heavy|all)
keka_ui.py             🖥️  desktop app: first-run wizard + control panel + in-app OTP box
keka_setup.py          🪪  one-time login + OTP → saves session
keka_punch_in.py       ☀️  clock in
keka_punch_out.py      🌙  clock out
keka_check.py          🐕  reauth watchdog
keka_common.py         🧠  shared logic (login, captcha OCR, session health, deps, autostart)
keka_doctor.py         🩺  one-shot health check (deps, config, session token, schedule)
ui/index.html          🎨  the glass dashboard + setup/wizard overlays
tests/                 🧪  pytest unit suite (session health, env, history, license)
requirements.txt       📦  Python dependencies (+ requirements-dev.txt for tests)
.env.example           📋  template of every config key (real .env lives in the data dir)
packaging/             📦  build the clickable app (name + icon) per OS
scheduling/            ⏰  install_macos.sh · install_linux.sh · install_windows.ps1
.github/workflows/     🧪  CI — tests installers + OCR on macOS/Linux/Windows
.env                   🔐  your secrets (git-ignored)
session.json           🍪  saved login (git-ignored)
logs/                  📄  run logs (git-ignored)
```

**How the app starts itself (under the hood):** the launcher runs `bootstrap.py`,
which installs only the *light* deps (venv + pip packages — no admin) behind a
small splash, then opens the window. The window installs the *heavy* deps
(Chromium + tesseract) in the background, live in the *"Setting up…"* panel. When
you finish the wizard it registers an **auto-open-at-login** entry (a `RunAtLoad`
LaunchAgent on macOS, a `~/.config/autostart` entry on Linux, a `Run` key on
Windows). Closing the window never stops the schedule — that's a separate OS-level
job (launchd / cron / Task Scheduler).

---

## 💳 Licensing (seller notes)

The app is gated by an **offline license key** (Ed25519-signed). `license.py`
ships the **public** key only, so the app verifies keys with no server; the
**private** key (`tools/license_private.pem`, git-ignored) only you hold.

```bash
# One-time: create your keypair + your first key, then paste the printed
# PUBLIC KEY into license.py → PUBLIC_KEY_HEX.
python tools/gen_license.py --name "Jane Doe" --email jane@acme.com
python tools/gen_license.py --name "Trial" --days 14        # time-limited key
```

**Cut a release (compiled binaries, all three OSes):** push a version tag and CI
does the rest — `.github/workflows/release.yml` builds source-hidden **Nuitka**
binaries (macOS `.app`, Windows `.exe`, Linux onefile), bakes in the app
name/icon/metadata, and attaches the zips to a GitHub Release. **Source is never
shipped**, and if no binary compiles the release is refused (nothing leaks).
```bash
git tag v1.0.1 && git push origin v1.0.1     # → Release with Auto-Keka-{macos,linux,windows}.zip
```
The compiled app is fully self-contained: it punches via `<binary> --punch in|out`,
schedules itself natively (launchd/cron/Task Scheduler), and downloads Chromium
through its bundled Playwright driver on first run. To build one locally instead:
```bash
bash packaging/build_binary.sh          # Nuitka onefile for this OS → dist/
```

**Before selling, remember:**
- 🔒 Keep the **GitHub repo private** — a public repo exposes the source, binary
  or not. (This repo is private; its Releases are private too, so you deliver the
  zips through your store rather than linking the Releases page.)
- 🗝️ **Back up `license_private.pem`.** Lose it and you can't verify sold keys;
  leak it and anyone can mint free ones.
- ✍️ **Code-sign / notarize** for a clean first launch — the binaries are
  unsigned, so buyers hit the one-time "unknown developer" prompt (documented in
  the release notes). Signing needs your Apple Developer / Windows certificates.
- 🏪 Sell + deliver keys via a store (Gumroad / Lemon Squeezy / Paddle) — they
  handle payment, tax, and key hand-off. Swap to their online key-validation API
  later if you want activation limits.

---

## 🧪 Testing

CI (`.github/workflows/ci.yml`) runs on every push across **three real OSes**:

- **installer** (ubuntu · macOS · windows) — runs the actual `setup.sh` / `setup.ps1`,
  then a smoke test: module import, real tesseract **OCR**, BOM-safe `.env` parsing.
- **shell-lint** — `shellcheck` + `bash -n` on the Unix installers.
- **powershell** (windows) — parse-check, PSScriptAnalyzer, and a live
  `Register-ScheduledTask` cmdlet check (paths-with-spaces safe).

- **unit tests** (all three OSes) — `pytest` suite in `tests/`: session-health
  token decoding, `.env` parsing/merging, history log, license signature
  verification (forgery/expiry/tamper), and the watchdog + UI helpers.

Run the checks locally:
```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q              # unit tests
.venv/bin/python -m py_compile *.py               # syntax
.venv/bin/python .github/scripts/smoke.py         # OCR + env smoke
.venv/bin/python keka_doctor.py                   # live installation health
```

---

## ⚠️ Use responsibly

This is a personal-productivity toy built to learn browser automation. Automating
attendance may go against your company's policies — **check first, and only log
time you actually work.** You're responsible for how you use it. 🙏

---

<sub>Built with 🐍 Python + 🎭 Playwright + 👁️ tesseract OCR.</sub>
