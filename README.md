# Keka Auto Attendance

Automatically clocks in/out on your Keka HR portal (`https://<company-name>.keka.com`)
via Playwright. **Cross-platform** — runs on macOS, Linux, and Windows.

## Files
| File | Purpose |
|------|---------|
| `keka_common.py` | Shared logic: captcha OCR, login, session, auto-relogin, clock in/out |
| `keka_setup.py`  | Interactive login + 2FA OTP → saves `session.json` (auto-opened when needed) |
| `keka_punch_in.py`  | Clocks IN using saved session (auto-relogins if expired) |
| `keka_punch_out.py` | Clocks OUT using saved session (auto-relogins if expired) |
| `keka_check.py`  | Reauth watchdog: opens `keka_setup.py` when the ~14-day cookie is near expiry |
| `session.json`   | Saved auth session (cookies + tokens) |
| `.env`           | Credentials (`KEKA_EMAIL`, `KEKA_PASSWORD`), `chmod 600` |
| `requirements.txt` | Python deps (playwright, pytesseract, pillow) |
| `scheduling/`    | Per-OS installers: `install_macos.sh`, `install_linux.sh`, `install_windows.ps1` |
| `logs/`          | Run logs (same path on every OS) |
| `.venv/`         | Python virtual environment |

## Install (any OS)
```bash
# 1. Python env + deps
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip
.venv/bin/python -m playwright install chromium

# 2. Install tesseract OCR engine (system package):
#    macOS:   brew install tesseract
#    Linux:   sudo apt install tesseract-ocr
#    Windows: install from github.com/UB-Mannheim/tesseract (auto-detected)

# 3. Create .env with your credentials (see below), then log in once:
.venv/bin/python keka_setup.py                     # enter the OTP in the browser

# 4. Schedule it (pick your OS):
bash scheduling/install_macos.sh                   # macOS  (launchd)
bash scheduling/install_linux.sh                   # Linux  (cron)
powershell -ExecutionPolicy Bypass -File scheduling\install_windows.ps1   # Windows (Task Scheduler)
```

Portability notes: logs go to `./logs/` on every OS; tesseract is found via PATH
or standard install dirs; notifications use osascript (macOS) / notify-send
(Linux) / PowerShell toast (Windows); the reauth dialog falls back to tkinter
so it works everywhere.

## Credentials & tenant
Stored in `.env` (owner-only, `chmod 600`), read by `keka_common.py`:
```
KEKA_BASE_URL=https://<company-name>.keka.com
KEKA_EMAIL=you@example.com
KEKA_PASSWORD=yourpassword
```
Set `KEKA_BASE_URL` to your organization's Keka subdomain. Environment variables
of the same name override the file. `.env` is gitignored — never committed.

## How it works
Keka enforces **captcha + 2FA (email/mobile OTP)** after password login. The OTP
can't be automated, so:

- **`keka_setup.py`:** does password + OCR-captcha, you enter the OTP once. Keka
  then sets a **`TwoFactorRememberMe` cookie (~14 days)** = "trust this device,
  skip OTP". The full session is saved to `session.json`.
- **Punch scripts:** load `session.json` and click punch. If the session has
  expired, they **auto-relogin** with password + OCR-captcha only — **no OTP**
  while the remember-device cookie is valid — then re-save the session.
- **`keka_check.py` (reauth watchdog):** runs daily + at login. The remember
  cookie does NOT refresh on relogin, so ~every 14 days it lapses. When it's
  within ~1.5 days of expiry, the watchdog **auto-opens the browser** (via
  `keka_setup.py`) and posts a notification so you just enter the OTP. Otherwise
  it exits silently.

So the only manual step, ~once every 14 days: **type the OTP into a browser that
opens itself.** Everything else is hands-off.

- **Clock-in**: single click of "Web Clock-In".
- **Clock-out**: two clicks — "Web Clock-out" then the red "Clock-out" confirm.
- **Idempotent**: if already in the target state, it logs and exits cleanly.
- **Captcha OCR**: tesseract; rejects bad-length reads, retries up to 12×.

## Schedule
Same three jobs on every OS (installed by the `scheduling/` script for your OS):

| Job | When | Action |
|-----|------|--------|
| punch in  | 9:00 AM Mon–Fri  | clock in |
| punch out | 6:00 PM Mon–Fri  | clock out |
| reauth    | 10:00 AM daily + at login | open OTP browser only if the ~14-day cookie is near expiry |

Logs: `logs/keka_punch_in.log`, `logs/keka_punch_out.log`, `logs/keka_reauth.log`

- **macOS (launchd):** re-runs missed jobs on wake, runs in your GUI session so
  the reauth browser can appear. **No Full Disk Access needed.**
- **Linux (cron):** punch jobs are headless; the reauth job passes `DISPLAY` so
  the browser can open on your desktop.
- **Windows (Task Scheduler):** reauth tasks use `/IT` (interactive) so the
  browser + dialog appear.

### Managing (macOS)
```bash
UID=$(id -u)
launchctl list | grep keka                              # status
launchctl kickstart -k gui/$UID/com.keka.punchin        # run now (test)
launchctl bootout   gui/$UID/com.keka.punchin           # disable one
bash scheduling/install_macos.sh                        # (re)install all
```
### Managing (Linux)
```bash
crontab -l                                              # view
crontab -l | grep -v 'keka_' | crontab -                # remove keka jobs
```
### Managing (Windows)
```powershell
schtasks /Query /FO LIST /TN Keka\PunchIn               # status
schtasks /Delete /F /TN Keka\PunchIn                    # remove one (also PunchOut, Reauth, ReauthLogon)
```

## Manual run / test
```bash
.venv/bin/python keka_punch_in.py     # clock in now   (Windows: .venv\Scripts\python)
.venv/bin/python keka_punch_out.py    # clock out now
.venv/bin/python keka_setup.py        # force a fresh OTP login
.venv/bin/python keka_check.py        # run the reauth check now
```

## Notes
- **Machine must be awake around 9 AM / 6 PM** for the punch to fire. macOS
  launchd runs missed jobs on the next wake; cron/Task Scheduler behavior varies.
- First time the reauth watchdog notifies you, the OS may ask to allow
  notifications — allow it so you're told when to enter the OTP. Either way the
  blocking dialog is the guaranteed alert.
