**Clock in/out on Keka, automatically — on macOS, Linux, and Windows.**

### 📥 Install (no terminal)
1. Download the zip below and **unzip** it anywhere.
2. Double-click the launcher for your OS inside the folder:

| OS | Double-click |
|----|--------------|
| 🍎 macOS   | `Auto-Keka.command` |
| 🪟 Windows | `Auto-Keka.bat` |
| 🐧 Linux   | `Auto-Keka.sh` |

3. First run shows a **"Setting up…"** panel while it installs the browser + OCR
   engine (one time), then a **wizard**: Keka login → OTP from your email → pick
   clock-in/out times → done. It then runs in the background, Mon–Fri, and
   re-opens at login.

### ⚠️ First-open "unknown developer" warning
The app isn't code-signed, so your OS may warn once:
- **macOS** → right-click `Auto-Keka.command` → **Open** → **Open**.
- **Windows** → **More info** → **Run anyway**.

### 🐧 Linux note
The OCR engine (tesseract) installs via your package manager, which needs `sudo`.
If the in-app setup can't get root, run `./setup.sh --phase heavy` once in a
terminal. macOS & Windows need no admin.
