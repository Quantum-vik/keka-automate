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

**1 · Install** — one command sets up everything:
```bash
./setup.sh                                                   # 🍎 macOS · 🐧 Linux
powershell -ExecutionPolicy Bypass -File setup.ps1           # 🪟 Windows
```
It installs the dependencies, then asks for your Keka URL / email / password and
opens a browser once for your OTP.

**2 · (Optional) Make it a clickable app** with a name + icon:
```bash
bash packaging/build_macos_app.sh                                          # 🍎 → Auto-Keka.app
bash packaging/build_linux_app.sh                                          # 🐧 → app-menu entry
powershell -ExecutionPolicy Bypass -File packaging\build_windows_app.ps1   # 🪟 → Desktop/Start-Menu shortcut
```
Now open **Auto-Keka** from your Dock / apps menu / Start menu. *(Or skip this and
just run `.venv/bin/python keka_ui.py`.)*

**3 · Set it up once** — in the app, click the **⚙️ gear** (top-right):
- **Account** → your Keka URL, email, password → **Save credentials**
- **Schedule** → clock-in and clock-out times → **Save & apply schedule**

**4 · First login** → click **🔑 Refresh session** → an **OTP box** pops up → type
the code from your email. Done.

**That's it — it now runs itself.** It clocks you **in and out at your set times,
Mon–Fri**, in the background. Any time, you can also:
- ☀️ **Clock In** / 🌙 **Clock Out** on demand (it never double-punches)
- Watch **This Week** + **Activity** to see what it's done
- **Every ~14 days** the OTP box pops again — enter a fresh code, set for another 2 weeks

> No GUI? Everything works from the terminal too — see **Handy commands** below.

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
- ⏭️ **Next scheduled** punch countdown and **device-pass** (14-day) health
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
Create a file named `.env` next to the scripts (it's **git-ignored — never
uploaded**):

```ini
KEKA_BASE_URL=https://your-company.keka.com
KEKA_EMAIL=you@company.com
KEKA_PASSWORD=your-password
```

> 💡 `KEKA_BASE_URL` is just your company's Keka web address. On macOS/Linux, lock
> the file down with `chmod 600 .env` so only you can read it.

---

## ⏰ The schedule

Same three jobs on every OS (set up by the installer for your platform):

| Job | When | What it does |
|-----|------|--------------|
| ☀️ Punch in  | 9:00 AM, Mon–Fri | Clock in |
| 🌙 Punch out | 6:00 PM, Mon–Fri | Clock out |
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
setup.sh / setup.ps1   🚀  one-command installer (macOS/Linux · Windows)
keka_ui.py             🖥️  desktop control panel (Tkinter) with in-app OTP box
keka_setup.py          🪪  one-time login + OTP → saves session
keka_punch_in.py       ☀️  clock in
keka_punch_out.py      🌙  clock out
keka_check.py          🐕  reauth watchdog
keka_common.py         🧠  shared logic (login, captcha OCR, session, clicking)
requirements.txt       📦  Python dependencies
scheduling/            ⏰  install_macos.sh · install_linux.sh · install_windows.ps1
.github/workflows/     🧪  CI — tests installers + OCR on macOS/Linux/Windows
.env                   🔐  your secrets (git-ignored)
session.json           🍪  saved login (git-ignored)
logs/                  📄  run logs (git-ignored)
```

---

## 🧪 Testing

CI (`.github/workflows/ci.yml`) runs on every push across **three real OSes**:

- **installer** (ubuntu · macOS · windows) — runs the actual `setup.sh` / `setup.ps1`,
  then a smoke test: module import, real tesseract **OCR**, BOM-safe `.env` parsing.
- **shell-lint** — `shellcheck` + `bash -n` on the Unix installers.
- **powershell** (windows) — parse-check, PSScriptAnalyzer, and a live
  `Register-ScheduledTask` cmdlet check (paths-with-spaces safe).

Run the Python checks locally:
```bash
.venv/bin/python -m py_compile *.py
.venv/bin/python .github/scripts/smoke.py
```

---

## ⚠️ Use responsibly

This is a personal-productivity toy built to learn browser automation. Automating
attendance may go against your company's policies — **check first, and only log
time you actually work.** You're responsible for how you use it. 🙏

---

<sub>Built with 🐍 Python + 🎭 Playwright + 👁️ tesseract OCR.</sub>
