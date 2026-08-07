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

**No terminal needed.** Just open the app and follow the on-screen wizard.

**1 · Download** the latest zip from the
[**Releases**](https://github.com/Quantum-vik/keka-automate/releases) page and
**unzip** it anywhere (Desktop is fine).

**2 · Double-click the launcher for your OS** (inside the unzipped folder):

| OS | Double-click |
|----|--------------|
| 🍎 macOS   | `Auto-Keka.command` |
| 🪟 Windows | `Auto-Keka.bat` |
| 🐧 Linux   | `Auto-Keka.sh` |

- **First run:** a *"Setting up…"* panel appears and quietly downloads the browser
  + OCR engine it needs (one time). No terminal, no `./setup.sh`.
- **Unknown-developer warning?** The app isn't code-signed, so your OS may warn once:
  **macOS** → right-click the launcher → *Open* → *Open*. **Windows** → *More info* →
  *Run anyway*. After that it opens normally.
- *Want a proper Dock/Start-menu icon?* Run `packaging/build_macos_app.sh`
  (or `build_linux_app.sh` / `build_windows_app.ps1`) for a named, icon'd app.

**3 · Follow the wizard** — it walks you through everything, in the window:
```
①  Enter your Keka URL · email · password        →  Continue
②  It signs you in automatically (solves captcha) →  📧 type the OTP from your email
③  Pick your clock-in & clock-out times           →  Finish
④  ✅ Done — the background schedule is armed
```

**That's it — it now runs itself.** It clocks you **in and out at your set times,
Mon–Fri**, in the background — *even when the app window is closed*, and it
**re-opens automatically when you log into your computer**. Any time, you can also:
- ☀️ **Clock In** / 🌙 **Clock Out** on demand (it never double-punches)
- Watch **This Week** + **Activity** to see what it's done
- Change times / credentials from the **⚙️ gear** (top-right)
- **Every ~14 days** an OTP box pops again — enter a fresh code, set for another 2 weeks

> **Prefer the terminal?** You can still run the classic one-shot installer instead
> of the app: `./setup.sh` (macOS/Linux) or
> `powershell -ExecutionPolicy Bypass -File setup.ps1` (Windows). See
> **Handy commands** below.

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

## 🖥️ Desktop app

Prefer buttons over a terminal? There's a **native "liquid glass" dashboard**:

```bash
.venv/bin/python keka_ui.py        # Windows: .venv\Scripts\python keka_ui.py
```

**Make it a real app (name + icon), per OS** — so it shows as "Auto-Keka" with a
clock icon instead of "python". Run the packager for your platform once:
```bash
bash packaging/build_macos_app.sh                              # 🍎 → Auto-Keka.app (Dock / Applications)
bash packaging/build_linux_app.sh                              # 🐧 → app-menu entry (.desktop + icon)
powershell -ExecutionPolicy Bypass -File packaging\build_windows_app.ps1   # 🪟 → Desktop + Start-Menu shortcuts (.ico)
```
All three share one icon generator (`packaging/make_icon.py`). The app itself
runs everywhere regardless (native window, or browser fallback on Linux without
WebKitGTK).

A real desktop window opens showing:
- ⏱️ **"Am I clocked in?"** hero with a live worked-time timer + workday progress
- ⏭️ **Next scheduled** punch countdown and a **real session-health verdict** —
  it decodes the saved login token's own expiry (plus a live probe), so
  "Session expired" means expired, and a **Sign in again (OTP)** button appears
  right on the card
- 🗓️ **This week** clock-in/out strip and a live **activity** feed
- ☀️🌙 **Clock in / out** buttons and 🔑 **Refresh session**
- 🔐 A **Settings** sheet (gear icon) for Keka URL / email / password and
  clock-in / clock-out times
- When Keka needs the 2FA code, an **OTP box appears right in the app** — read
  the code from your email, type it in; login finishes headlessly (no browser popup).

**How it renders (cross-platform):** a native window via
[pywebview](https://pywebview.flowlib.org/) — macOS **WebKit**, Windows
**WebView2**, Linux **WebKitGTK**. If a machine has no webview backend, it
automatically **falls back to opening the same dashboard in your default
browser**, so it works everywhere. Every action is recorded in
`logs/history.jsonl` so you can see previous sessions.

---

## 🚀 Setup — one command

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

Ship a **compiled** binary (so the check can't be edited out of the source):
```bash
bash packaging/build_binary.sh          # Nuitka onefile for this OS → dist/
```

**Before selling, remember:**
- 🔒 Make the **GitHub repo private** — a public repo already exposes the source,
  binary or not.
- 🗝️ **Back up `license_private.pem`.** Lose it and you can't verify sold keys;
  leak it and anyone can mint free ones.
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
