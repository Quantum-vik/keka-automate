**Clock in/out on Keka, automatically — compiled apps for macOS, Windows, and Linux. No source, no Python needed.**

### 📥 Install
1. Download the file for **your OS** below.
2. Run it:

| OS | Download | Run |
|----|----------|-----|
| 🍎 macOS   | `Auto-Keka-macos.dmg`       | open it, drag `Auto-Keka.app` to Applications, then open it |
| 🪟 Windows | `Auto-Keka.exe`             | move it somewhere permanent (e.g. `Documents`), then double-click |
| 🐧 Linux   | `Auto-Keka-x86_64.AppImage` | `chmod +x Auto-Keka-x86_64.AppImage && ./Auto-Keka-x86_64.AppImage` — any distro |

   `Auto-Keka-macos-native.dmg` is the optional native macOS menu-bar client.
   Keep the app where you first run it: the punch schedule launches it from there.

3. The app walks you through everything: license key → Keka login → OTP from
   your email → pick clock-in/out times → done. It punches Mon–Fri on your
   schedule (jobs run even with the window closed) and re-opens at login.

### 🔧 First run
- The app downloads its private browser engine automatically (one time, ~100 MB).
- The captcha reader (tesseract) comes from your OS:
  **macOS** `brew install tesseract` · **Windows** [UB-Mannheim installer](https://github.com/UB-Mannheim/tesseract) ·
  **Linux** `sudo apt install tesseract-ocr` (or your distro's package).
  The app tells you in-window if it's missing.
- **Linux window:** the app draws its window with your system's WebKitGTK, which
  Ubuntu desktop already includes. If it's missing the dashboard opens in your
  browser instead; for the native window install `gir1.2-webkit2-4.1`
  (Fedora `webkit2gtk4.1`, Arch `webkit2gtk-4.1`).

### ⚠️ First-open "unknown developer" warning
The app isn't code-signed, so your OS may warn once:
- **macOS** → right-click `Auto-Keka.app` → **Open** → **Open**.
- **Windows** → **More info** → **Run anyway**.

### 🔑 License
The app asks for your license key on first open — paste the key you received
when you purchased.
