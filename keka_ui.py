"""
Keka Automate — desktop control panel.

    python keka_ui.py

Opens a NATIVE desktop window (via pywebview — macOS WebKit / Windows WebView2 /
Linux WebKitGTK) rendering the "liquid glass" dashboard in ui/index.html.

If a machine has no webview backend (e.g. a Linux box without WebKitGTK), it
automatically falls back to serving the same UI in your default browser — so it
works on every machine either way.

The 2FA OTP is entered in the window; login runs headless (no browser popup).
Everything you do is recorded in logs/history.jsonl (previous-session info).
"""

import os
import sys
import json
import time
import queue
import logging
import threading
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keka_common as kc
import license as lic

UI_HTML = os.path.join(kc.SCRIPT_DIR, "ui", "index.html")
VENV_PY = sys.executable

# How long a sign-in waits for the user to type the emailed OTP before giving
# up. Bounded because the wait happens while holding _pw_lock: an abandoned
# prompt (window closed, phone tab gone) must not stall the backend forever.
OTP_WAIT_SECS = 300

# How often the background thread does a LIVE Keka probe (get_status loads the
# full attendance SPA, which fans out into many API calls). This must stay
# large: a 90s probe ran ~750 loads over a 19h session and tripped Keka's
# "API rate limit exceeded". The UI stays fresh via the frontend's own 30s
# get_state poll, which is LOCAL (no Keka) — so the live probe only needs to
# reconcile out-of-band punches occasionally.
LIVE_PROBE_SECS = 900   # 15 minutes


# ─── Backend: all state + actions, push-mechanism-agnostic (self.emit) ────────
class Backend:
    def __init__(self):
        self.emit = lambda obj: None    # runner sets this (native evaluate_js / SSE)
        self._pw_lock = threading.Lock()  # serialize ALL Playwright/session access
        self._deps_lock = threading.Lock()  # serialize the heavy-dependency install
        self._deps_installing = False
        self._otp_event = threading.Event()
        self._otp_value = None
        self._status = None
        self._alive = None   # live session verdict: True/False, None = not probed yet
        self.log = logging.getLogger("keka_ui")
        self.log.setLevel(logging.INFO)
        self.log.handlers = [logging.NullHandler()]
        self._status = self._status_from_history()
        self._update = {"available": False, "current": kc.APP_VERSION,
                        "latest": None, "url": kc.RELEASES_PAGE, "notes": ""}
        threading.Thread(target=self._status_refresher, daemon=True).start()
        threading.Thread(target=self._update_checker, daemon=True).start()
        # Existing installs (onboarded before app-wrapping existed) self-heal:
        # quietly install the native wrapper + repoint autostart at it.
        if kc.is_onboarded() and not kc.desktop_app_installed():
            threading.Thread(target=self._ensure_desktop_app, daemon=True).start()

    def _update_checker(self):
        """Poll GitHub for a newer release on launch, then every 12h. Silent on
        error; pushes fresh state (with the banner) only when something changes."""
        time.sleep(4)   # let the first state load land before we hit the network
        while True:
            try:
                info = kc.check_for_update()
                if info != self._update:
                    self._update = info
                    if info.get("available"):
                        self.push_log(f"Update available: v{info['latest']} "
                                      f"(you have v{info['current']})", "info")
                    self.push_state()
            except Exception:
                pass
            time.sleep(12 * 3600)

    def _ensure_desktop_app(self):
        if kc.install_desktop_app():
            kc.install_autostart()
            self.push_log("Installed the Auto-Keka desktop app — launch it "
                          "from Applications from now on")

    # push helpers
    def push_log(self, msg, kind="info"):
        self.emit({"type": "log", "entry": {"time": datetime.now().strftime("%H:%M"),
                                             "msg": msg, "kind": kind}})

    def push_state(self):
        self.emit({"type": "state", "state": self.get_state()})

    # status (cached; background-refreshed, serialized by the lock)
    def _status_from_history(self):
        today = datetime.now().strftime("%Y-%m-%d")
        last = None
        for h in kc.read_history(200):
            if h.get("date") == today and h.get("kind") in ("in", "out"):
                last = h["kind"]
        return last

    def _status_refresher(self):
        time.sleep(2)
        while True:
            try:
                # Skip the live Keka probe entirely when there's nothing to
                # reconcile — no session, or automation paused. Cuts needless
                # load on the HR portal (get_status would only return None/quick
                # anyway, but this avoids even launching the browser).
                if os.path.exists(kc.SESSION_FILE) and not kc.is_paused():
                    with self._pw_lock:
                        s = kc.get_status()
                    if s in ("in", "out"):
                        self._status, self._alive = s, True
                    elif s == "dead":
                        # Definitive: the probe was bounced to the login flow.
                        self._alive = False
                    # None = transient/unknown (SPA settling, maintenance page) —
                    # keep the previous verdict instead of flashing "Session expired".
                    self.push_state()
            except Exception:
                pass   # deps missing / browser failed — leave verdict unchanged
            time.sleep(LIVE_PROBE_SECS)

    # ── JS API methods ──────────────────────────────────────────────────────
    def get_state(self):
        kc.reload_config()
        env = kc._load_env()
        health = kc.session_health()
        exp = health["remember_exp"]
        days = max(0, min(14, int((exp - time.time()) / 86400))) if exp else 0
        # Live probe verdict wins; fall back to the token's own expiry claim.
        alive = self._alive if self._alive is not None else health["alive"]
        hist = kc.read_history(200)
        cin, cout = self._today_punches(hist)
        activity = [{"time": h["time"], "msg": h["msg"], "kind": h["kind"],
                     "date": h.get("date")}
                    for h in reversed(hist)][:12]
        configured = bool(env.get("KEKA_EMAIL") and env.get("KEKA_PASSWORD"))
        # Treat existing users (already configured + a saved session) as onboarded
        # so the first-run wizard never re-appears for them.
        onboarded = (env.get("KEKA_ONBOARDED", "") == "1"
                     or (configured and os.path.exists(kc.SESSION_FILE)))
        linfo = lic.license_info()
        return {
            "licensed": linfo is not None,
            "licenseName": (linfo or {}).get("n", ""),
            "clockedIn": self._status == "in",
            "clockInAt": cin, "clockOutAt": cout,
            "scheduleIn": env.get("KEKA_IN_TIME", "09:00"),
            "scheduleOut": env.get("KEKA_OUT_TIME", "18:00"),
            "sessionDaysLeft": days,
            "sessionAlive": alive,
            "tokenExpiresAt": health["token_exp"] * 1000 if health["token_exp"] else None,
            "week": self._build_week(hist),
            "activity": activity,
            "depsReady": kc.deps_ready(),
            "onboarded": onboarded,
            "paused": kc.is_paused(),
            "timeoff": kc.load_timeoff(),
            "todayOff": kc.is_timeoff(datetime.now().strftime("%Y-%m-%d")),
            "stats": kc.attendance_stats(hist, env.get("KEKA_IN_TIME", "09:00")),
            "version": kc.APP_VERSION,
            "update": self._update,
            "config": {"url": env.get("KEKA_BASE_URL", ""), "email": env.get("KEKA_EMAIL", ""),
                       "configured": configured},
        }

    def install_deps(self):
        """Install the heavy deps (Chromium + tesseract) in the background,
        streaming progress to the panel. Safe to call repeatedly."""
        if kc.deps_ready():
            self.push_state()
            return {"ok": True, "ready": True}
        with self._deps_lock:
            if kc.deps_ready():
                self.push_state()
                return {"ok": True, "ready": True}
            self._deps_installing = True
            self.push_log("Setting up — downloading browser + OCR engine…")
            if kc.FROZEN:
                # No source tree/venv in the compiled build — use the bundled
                # Playwright driver for Chromium; tesseract needs the OS package.
                ok = kc.install_chromium_frozen()
                rc = 0 if ok else 1
                if not kc._find_tesseract():
                    self.push_log("Install the tesseract OCR engine: "
                                  "macOS 'brew install tesseract' · Windows "
                                  "UB-Mannheim installer · Linux distro package.", "out")
            else:
                plat = sys.platform
                if plat.startswith("win"):
                    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File",
                           os.path.join(kc.SCRIPT_DIR, "setup.ps1"), "-Phase", "heavy"]
                else:
                    cmd = ["bash", os.path.join(kc.SCRIPT_DIR, "setup.sh"), "--phase", "heavy"]
                rc = self._run_stream(cmd)
            ready = kc.deps_ready()
            self._deps_installing = False
            self.push_state()
            if ready:
                self.push_log("Setup complete — you're ready to sign in ✓", "in")
            else:
                self.push_log("Some components need a manual step — see the README "
                              "or run setup in a terminal.", "out")
            return {"ok": rc == 0 and ready, "ready": ready}

    def remote_info(self):
        """URL + QR for the phone remote (empty when the server isn't up)."""
        url = _REMOTE.get("url")
        if not url:
            return {"enabled": False}
        qr = None
        try:
            import io
            import base64
            import qrcode
            buf = io.BytesIO()
            qrcode.make(url).save(buf, format="PNG")
            qr = base64.b64encode(buf.getvalue()).decode()
        except Exception:
            pass                     # no qrcode lib — the URL alone still works
        return {"enabled": True, "url": url, "qr": qr}

    def activate_license(self, key):
        """Validate + store a license key. Returns {ok, name|message}."""
        info = lic.verify_key(key or "")
        if info:
            lic.save_license(key)
            kc.log_history("info", "License activated")
            self.push_state()
            return {"ok": True, "name": info.get("n", "")}
        return {"ok": False, "message": "Invalid or expired license key"}

    def finish_onboarding(self):
        """Mark first-run complete, install the native app wrapper (so future
        launches are 'Auto-Keka' with an icon, not a python file), and register
        it to open at login. Order matters: the macOS autostart prefers the
        installed bundle."""
        kc.mark_onboarded()
        kc.install_desktop_app()
        auto = kc.install_autostart()
        kc.log_history("info", "Setup finished — automation armed")
        self.push_state()
        return {"ok": True, "autostart": bool(auto)}

    def clock_in(self):
        return self._do_punch("in")

    def clock_out(self):
        return self._do_punch("out")

    def refresh_session(self):
        kc.reload_config()
        if not kc.EMAIL or not kc.PASSWORD:
            return {"ok": False, "message": "Set your email and password in Settings first"}
        with self._pw_lock:
            ok = kc.interactive_login(self._otp_getter, self.log, headless=True)
            if ok:
                self._alive = True
                kc.log_history("info", "Session refreshed")
            try:
                s = kc.get_status()
                if s in ("in", "out"):
                    self._status, self._alive = s, True
                    # The login flow may have bailed (e.g. cancelled OTP) while
                    # the existing session is in fact alive — report the truth.
                    ok = True
                elif s == "dead":
                    self._alive = False
            except Exception:
                pass
        self.push_state()
        exp = kc.session_health()["remember_exp"]
        days = max(0, min(14, int((exp - time.time()) / 86400))) if exp else 0
        return {"ok": ok, "message": (f"Session refreshed — device pass valid {days} days"
                if ok else "Login did not complete")}

    def submit_otp(self, code):
        self._otp_value = (code or "").strip()
        self.emit({"type": "otpDone"})
        self._otp_event.set()
        return {"ok": True}

    def save_creds(self, obj):
        obj = obj or {}
        # Only update fields the user actually filled in, so editing (e.g.) just
        # the URL never wipes a saved password.
        updates = {}
        if (obj.get("url") or "").strip():   updates["KEKA_BASE_URL"] = obj["url"].strip()
        if (obj.get("email") or "").strip(): updates["KEKA_EMAIL"] = obj["email"].strip()
        if obj.get("password"):              updates["KEKA_PASSWORD"] = obj["password"]
        if updates:
            kc.update_env(updates)
        kc.log_history("info", "Credentials saved")
        return {"ok": True}

    def apply_schedule(self, obj):
        obj = obj or {}
        it, ot = (obj.get("inTime") or "").strip(), (obj.get("outTime") or "").strip()
        kc.update_env({"KEKA_IN_TIME": it, "KEKA_OUT_TIME": ot})
        if kc.FROZEN:
            # Compiled build: schedule natively — jobs call this binary --punch.
            ok = kc.install_schedule_native(it, ot)
            kc.log_history("info", f"Schedule set · in {it}, out {ot}")
            self.push_state()
            return {"ok": bool(ok)}
        sd = os.path.join(kc.SCRIPT_DIR, "scheduling")
        plat = sys.platform
        if plat == "darwin":
            cmd = ["bash", os.path.join(sd, "install_macos.sh")]
        elif plat.startswith("linux"):
            cmd = ["bash", os.path.join(sd, "install_linux.sh")]
        elif plat.startswith("win"):
            cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File",
                   os.path.join(sd, "install_windows.ps1")]
        else:
            return {"ok": False, "message": "Unsupported OS"}
        rc = self._run_stream(cmd)
        kc.log_history("info", f"Schedule set · in {it}, out {ot}")
        self.push_state()
        return {"ok": rc == 0}

    # ── time off (holidays / planned leave) ──────────────────────────────────
    def get_timeoff(self):
        return {"ok": True, "entries": kc.load_timeoff()}

    def add_timeoff(self, obj):
        obj = obj or {}
        date = (obj.get("date") or "").strip()
        if not kc._valid_date(date):
            return {"ok": False, "message": "Pick a valid date (YYYY-MM-DD)."}
        entries = kc.load_timeoff() + [{"date": date,
                                        "kind": obj.get("kind") or "leave",
                                        "note": obj.get("note") or ""}]
        saved = kc.save_timeoff(entries)
        kc.log_history("info", f"Time off added · {date} ({obj.get('kind') or 'leave'})")
        self.push_state()
        return {"ok": True, "entries": saved}

    def remove_timeoff(self, obj):
        date = ((obj or {}).get("date") or "").strip()
        saved = kc.save_timeoff([e for e in kc.load_timeoff() if e.get("date") != date])
        self.push_state()
        return {"ok": True, "entries": saved}

    # ── pause / resume automation ────────────────────────────────────────────
    def set_pause(self, obj):
        paused = bool((obj or {}).get("paused"))
        kc.set_paused(paused)
        kc.log_history("info", "Automation paused" if paused else "Automation resumed")
        self.push_state()
        return {"ok": True, "paused": kc.is_paused()}

    # ── software update ──────────────────────────────────────────────────────
    def check_update(self):
        """Force an update check now (the banner's 'Check again'). Returns the
        {available, current, latest, url, notes} dict and refreshes state."""
        self._update = kc.check_for_update()
        self.push_state()
        return {"ok": True, "update": self._update}

    def open_release(self, obj=None):
        """Open the release download page in the user's browser. Only ever opens
        our own GitHub releases URL — never an arbitrary URL from the caller."""
        url = (obj or {}).get("url") or self._update.get("url") or kc.RELEASES_PAGE
        allowed = f"https://github.com/{kc.GITHUB_REPO}/releases"
        if not str(url).startswith(allowed):
            url = kc.RELEASES_PAGE
        import webbrowser
        try:
            webbrowser.open(url)
            return {"ok": True, "url": url}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    # ── attendance export ────────────────────────────────────────────────────
    def export_csv(self):
        try:
            path = kc.export_history_csv()
            self.push_log(f"Attendance exported to {path}", "in")
            kc.log_history("info", "Attendance exported to CSV")
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    # ── internals ────────────────────────────────────────────────────────────
    def _otp_getter(self, retry=False):
        self.emit({"type": "otp", "retry": bool(retry)})
        self._otp_event.clear()
        if not self._otp_event.wait(timeout=OTP_WAIT_SECS):
            self.emit({"type": "otpDone"})   # retract the now-stale prompt
            self.push_log("No OTP entered in 5 minutes — sign-in cancelled", "out")
            return None                      # interactive_login treats None as cancel
        return self._otp_value

    def _today_punches(self, hist):
        today = datetime.now().strftime("%Y-%m-%d")
        cin = cout = None
        for h in hist:
            if h.get("date") != today:
                continue
            if h["kind"] == "in" and cin is None:
                cin = h["ts"]
            if h["kind"] == "out":
                cout = h["ts"]
        return cin, cout

    def _build_week(self, hist):
        now = datetime.now()
        monday_ord = now.toordinal() - now.weekday()
        names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
        by_date = {}
        for h in hist:
            d = h.get("date")
            if not d:
                continue
            slot = by_date.setdefault(d, {"in": None, "out": None})
            if h["kind"] == "in" and slot["in"] is None:
                slot["in"] = h["time"]
            if h["kind"] == "out":
                slot["out"] = h["time"]
        week = []
        for i, name in enumerate(names):
            day = datetime.fromordinal(monday_ord + i)
            dstr = day.strftime("%Y-%m-%d")
            slot = by_date.get(dstr, {})
            week.append({"day": name, "date": f"{day.month}/{day.day}",
                         "in": slot.get("in") or "—", "out": slot.get("out") or "—",
                         "today": day.date() == now.date(), "dim": day.date() > now.date()})
        return week

    def _run_stream(self, cmd):
        try:
            p = subprocess.Popen(cmd, cwd=kc.SCRIPT_DIR, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, bufsize=1)
        except Exception as e:
            self.push_log(f"Could not run: {e}")
            return 1
        for line in p.stdout:
            line = line.strip()
            if any(k in line for k in ("INFO", "WARNING", "ERROR")):
                self.push_log(line.split("  ", 1)[-1] if "  " in line else line)
        p.wait()
        return p.returncode

    def _do_punch(self, action):
        with self._pw_lock:
            kc.reload_config()
            if kc.FROZEN:   # compiled build: re-invoke this binary in punch mode
                cmd = [sys.executable, "--punch", action]
            else:
                script = "keka_punch_in.py" if action == "in" else "keka_punch_out.py"
                cmd = [VENV_PY, os.path.join(kc.SCRIPT_DIR, script)]
            rc = self._run_stream(cmd)
            if rc != 0:
                self.push_log("Session expired — logging in first…")
                if kc.interactive_login(self._otp_getter, self.log, headless=True):
                    rc = self._run_stream(cmd)
            if rc == 0:
                self._alive = True   # punch reached Keka — session verified live
            try:
                s = kc.get_status()
                if s in ("in", "out"):
                    self._status, self._alive = s, True
                elif s == "dead" and rc != 0:
                    self._alive = False
            except Exception:
                pass
        self.push_state()
        ok = rc == 0
        return {"ok": ok, "message": (f"Clocked {'in' if action == 'in' else 'out'}"
                if ok else "Punch failed — check credentials")}


# ─── App identity (macOS Dock name + icon) ────────────────────────────────────
def _app_icon_path():
    """PNG icon for the runtime Dock tile; generated once into the data dir."""
    p = os.path.join(kc.DATA_DIR, "icon.png")
    if not os.path.exists(p):
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "_make_icon", os.path.join(kc.SCRIPT_DIR, "packaging", "make_icon.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.make(512).save(p)
        except Exception:
            return None
    return p


def _macos_app_identity():
    """Brand the running process as 'Auto-Keka' with our icon.

    macOS attributes a GUI process to the bundle owning its EXECUTABLE — for a
    script launch that's the Python framework's internal Python.app, so the
    Dock shows 'python3.13' with a blank icon. Rewriting the main bundle's
    in-memory name fixes the menu bar; setApplicationIconImage fixes the Dock
    tile. (The Dock LABEL is fully correct when launched via Auto-Keka.app.)
    """
    if sys.platform != "darwin":
        return
    try:
        from Foundation import NSBundle
        from AppKit import NSApplication, NSImage
        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info is not None:
            info["CFBundleName"] = "Auto-Keka"
            info["CFBundleDisplayName"] = "Auto-Keka"
        icon = _app_icon_path()
        if icon:
            img = NSImage.alloc().initWithContentsOfFile_(icon)
            if img:
                NSApplication.sharedApplication().setApplicationIconImage_(img)
    except Exception:
        pass   # cosmetic only — never block the app on it


def _platform_app_identity():
    """Per-OS process branding so the taskbar/Dock never says 'python'."""
    _macos_app_identity()
    if sys.platform.startswith("win"):
        try:
            import ctypes
            # Detach from python.exe's taskbar group; pairs with the shortcut
            # so the taskbar shows Auto-Keka's own icon and name.
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.keka.autokeka")
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        try:
            from gi.repository import GLib
            GLib.set_prgname("Auto-Keka")   # matches StartupWMClass in .desktop
        except Exception:
            pass


# ─── Native window (pywebview) ────────────────────────────────────────────────
def _push_native(window, obj):
    t = obj.get("type")
    if t == "log":
        js = f"window.KekaUI&&window.KekaUI.onLog({json.dumps(obj['entry'])})"
    elif t == "state":
        js = f"window.KekaUI&&window.KekaUI.onState({json.dumps(obj['state'])})"
    elif t == "otp":
        js = f"window.KekaUI&&window.KekaUI.onOtpRequired({json.dumps(bool(obj['retry']))})"
    elif t == "otpDone":
        js = "window.KekaUI&&window.KekaUI.onOtpDone()"
    else:
        return
    try:
        window.evaluate_js(js)
    except Exception:
        pass


class Api:
    """The methods the page calls as window.pywebview.api.*"""
    def __init__(self, backend):
        self._b = backend
    def get_state(self):        return self._b.get_state()
    def clock_in(self):         return self._b.clock_in()
    def clock_out(self):        return self._b.clock_out()
    def refresh_session(self):  return self._b.refresh_session()
    def submit_otp(self, code): return self._b.submit_otp(code)
    def save_creds(self, obj):  return self._b.save_creds(obj)
    def apply_schedule(self, obj): return self._b.apply_schedule(obj)
    def install_deps(self):     return self._b.install_deps()
    def finish_onboarding(self): return self._b.finish_onboarding()
    def activate_license(self, key): return self._b.activate_license(key)
    def remote_info(self):      return self._b.remote_info()
    def get_timeoff(self):      return self._b.get_timeoff()
    def add_timeoff(self, obj): return self._b.add_timeoff(obj)
    def remove_timeoff(self, obj): return self._b.remove_timeoff(obj)
    def set_pause(self, obj):   return self._b.set_pause(obj)
    def export_csv(self):       return self._b.export_csv()
    def check_update(self):     return self._b.check_update()
    def open_release(self, obj=None): return self._b.open_release(obj)

    # frameless-window controls (the design draws its own traffic lights)
    def win_close(self):
        import webview
        try: webview.windows[0].destroy()
        except Exception: pass
    def win_minimize(self):
        import webview
        try: webview.windows[0].minimize()
        except Exception:
            try: webview.windows[0].hide()
            except Exception: pass


def run_native():
    import webview  # raises if pywebview missing
    _platform_app_identity()
    backend = Backend()
    remote_broadcast = start_remote_server(backend)   # phone remote on the LAN
    bg = "#eef4f2"
    if sys.platform == "darwin":
        try:      # match the pre-load window color to the system theme
            r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                               capture_output=True, text=True)
            if "Dark" in (r.stdout or ""):
                bg = "#101b18"
        except Exception:
            pass
    window = webview.create_window(
        "Auto-Keka", url=UI_HTML, js_api=Api(backend),
        width=860, height=760, min_size=(560, 640), background_color=bg,
        frameless=True, easy_drag=False,   # design supplies its own title bar
    )
    def emit(obj):
        _push_native(window, obj)
        if remote_broadcast:
            remote_broadcast(obj)          # phones see the same live events
    backend.emit = emit
    webview.start()          # blocks; must be on the main thread


# ─── Browser fallback (stdlib http.server + fetch/SSE) ────────────────────────
_SHIM = """
<script>
(function(){
  window.KEKA_REMOTE = true;   // page adapts: no fake window chrome, phone layout
  const j=(r)=>r.json();
  const post=(p,b)=>fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})}).then(j);
  window.pywebview={api:{
    get_state:()=>fetch('/api/state').then(j),
    clock_in:()=>post('/api/clock_in'), clock_out:()=>post('/api/clock_out'),
    refresh_session:()=>post('/api/refresh'), submit_otp:(c)=>post('/api/submit_otp',{code:c}),
    save_creds:(o)=>post('/api/save_creds',o), apply_schedule:(o)=>post('/api/apply_schedule',o),
    install_deps:()=>post('/api/install_deps'), finish_onboarding:()=>post('/api/finish_onboarding'),
    activate_license:(k)=>post('/api/activate_license',{key:k}), remote_info:()=>post('/api/remote_info'),
    get_timeoff:()=>post('/api/get_timeoff'), add_timeoff:(o)=>post('/api/add_timeoff',o),
    remove_timeoff:(o)=>post('/api/remove_timeoff',o), set_pause:(o)=>post('/api/set_pause',o),
    export_csv:()=>post('/api/export_csv'), check_update:()=>post('/api/check_update'),
    open_release:(o)=>post('/api/open_release',o)}};
  try{const es=new EventSource('/events');es.onmessage=(e)=>{const m=JSON.parse(e.data),K=window.KekaUI||{};
    if(m.type==='log'&&K.onLog)K.onLog(m.entry);else if(m.type==='state'&&K.onState)K.onState(m.state);
    else if(m.type==='otp'&&K.onOtpRequired)K.onOtpRequired(m.retry);else if(m.type==='otpDone'&&K.onOtpDone)K.onOtpDone();};}catch(_){}
})();
</script>
"""


def _serve_http(backend, host, port, token):
    """Shared dashboard HTTP/SSE server. With a token, every request must carry
    it (?t= query on first open, then a cookie) — this is what makes the LAN
    phone remote safe to expose beyond loopback.
    Returns (httpd, broadcast, actual_port); caller runs httpd.serve_forever()."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlparse, parse_qs

    with open(UI_HTML, encoding="utf-8") as f:
        html = f.read().replace("<script>", _SHIM + "<script>", 1).encode("utf-8")

    subs, sub_lock = [], threading.Lock()

    def broadcast(obj):
        with sub_lock:
            for q in list(subs):
                q.put(obj)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _authed(self):
            if not token:
                return True
            if token in parse_qs(urlparse(self.path).query).get("t", []):
                return True
            cookies = (self.headers.get("Cookie") or "").replace(" ", "")
            return f"kt={token}" in cookies
        def _json(self, obj, code=200):
            body = json.dumps(obj).encode(); self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers()
            self.wfile.write(body)
        def do_GET(self):
            route = urlparse(self.path).path
            if route == "/icon.png":   # just the logo — public so iOS can fetch
                p = _app_icon_path()
                if p and os.path.exists(p):
                    with open(p, "rb") as f:
                        data = f.read()
                    self.send_response(200); self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(data))); self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_error(404)
                return
            if not self._authed():
                body = b"Auto-Keka: unauthorized. Scan the QR code in the app's Settings."
                self.send_response(401); self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body))); self.end_headers()
                self.wfile.write(body); return
            if route in ("/", "/index.html"):
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
                if token:   # remember the token so in-page fetch/SSE calls pass auth
                    self.send_header("Set-Cookie", f"kt={token}; Path=/; SameSite=Lax")
                self.send_header("Content-Length", str(len(html))); self.end_headers(); self.wfile.write(html)
            elif route == "/api/state":
                self._json(backend.get_state())
            elif route == "/events":
                self.send_response(200); self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache"); self.end_headers()
                q = queue.Queue()
                with sub_lock: subs.append(q)
                try:
                    while True:
                        try: data = f"data: {json.dumps(q.get(timeout=15))}\n\n".encode()
                        except queue.Empty: data = b": ping\n\n"
                        self.wfile.write(data); self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError): pass
                finally:
                    with sub_lock:
                        if q in subs: subs.remove(q)
            else:
                self.send_error(404)
        def do_POST(self):
            route = urlparse(self.path).path
            if not self._authed(): self.send_error(401); return
            n = int(self.headers.get("Content-Length", 0) or 0)
            try: body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError: body = {}
            routes = {"/api/clock_in": lambda: backend.clock_in(),
                      "/api/clock_out": lambda: backend.clock_out(),
                      "/api/refresh": lambda: backend.refresh_session(),
                      "/api/submit_otp": lambda: backend.submit_otp(body.get("code")),
                      "/api/save_creds": lambda: backend.save_creds(body),
                      "/api/apply_schedule": lambda: backend.apply_schedule(body),
                      "/api/install_deps": lambda: backend.install_deps(),
                      "/api/finish_onboarding": lambda: backend.finish_onboarding(),
                      "/api/remote_info": lambda: backend.remote_info(),
                      "/api/activate_license": lambda: backend.activate_license(body.get("key")),
                      "/api/get_timeoff": lambda: backend.get_timeoff(),
                      "/api/add_timeoff": lambda: backend.add_timeoff(body),
                      "/api/remove_timeoff": lambda: backend.remove_timeoff(body),
                      "/api/set_pause": lambda: backend.set_pause(body),
                      "/api/export_csv": lambda: backend.export_csv(),
                      "/api/check_update": lambda: backend.check_update(),
                      "/api/open_release": lambda: backend.open_release(body)}
            fn = routes.get(route)
            if not fn: self.send_error(404); return
            try: self._json(fn())
            except Exception as e: self._json({"ok": False, "message": str(e)}, 500)

    bind, tries = port, 0
    while True:
        try:
            httpd = ThreadingHTTPServer((host, bind), H)
            break
        except OSError:
            tries += 1
            if tries > 10: raise
            bind = port + tries
    return httpd, broadcast, httpd.server_address[1]


# ── Phone remote (LAN, token-protected) ───────────────────────────────────────
_REMOTE = {"url": None}


def _remote_token():
    """Persistent random access token for the phone remote (0600 in DATA_DIR)."""
    p = os.path.join(kc.DATA_DIR, "remote_token")
    try:
        if os.path.exists(p):
            tok = open(p, encoding="utf-8").read().strip()
            if tok:
                return tok
        import secrets
        tok = secrets.token_urlsafe(16)
        with open(p, "w", encoding="utf-8") as f:
            f.write(tok)
        os.chmod(p, 0o600)
        return tok
    except OSError:
        import secrets
        return secrets.token_urlsafe(16)   # per-run token if the disk write fails


def _lan_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))       # no traffic sent — just picks the LAN route
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def start_remote_server(backend):
    """Serve the dashboard on the LAN next to the native window. Returns the
    broadcast fn (for fanning out events) or None if the server can't start."""
    try:
        token = _remote_token()
        port = int(os.environ.get("KEKA_REMOTE_PORT", "8377") or 8377)
        httpd, broadcast, actual = _serve_http(backend, "0.0.0.0", port, token)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        _REMOTE["url"] = f"http://{_lan_ip()}:{actual}/?t={token}"
        return broadcast
    except Exception:
        return None


SIDECAR_FILE = os.path.join(kc.DATA_DIR, "sidecar.json")


def _exit_when_orphaned(httpd, poll=2.0):
    """Shut down once our parent goes away (getppid() drops to launchd/init).

    A front-end that crashes, is force-quit, or is SIGKILLed never gets to run
    its cleanup, so the core cannot rely on being told to stop — it would sit
    there holding a port and a token forever. Watching the parent covers every
    one of those cases.
    """
    original = os.getppid()

    def watch():
        while True:
            time.sleep(poll)
            current = os.getppid()
            if current != original or current == 1:
                httpd.shutdown()          # unblocks serve_forever -> finally
                return

    threading.Thread(target=watch, daemon=True).start()


def run_serve(port=0, exit_with_parent=False):
    """Headless API mode for a native front-end (the Swift macOS client).

    Same HTTP + SSE surface the phone remote already speaks, but bound to
    loopback only and with no browser popped open. The chosen port and token
    are written to SIDECAR_FILE so the front-end can find us without having to
    scrape stdout — the port is normally 0 (kernel-assigned) to avoid clashing
    with the phone remote on 8377.
    """
    backend = Backend()
    token = _remote_token()
    httpd, broadcast, actual = _serve_http(backend, "127.0.0.1", port, token)
    backend.emit = broadcast

    info = {"port": actual, "token": token, "pid": os.getpid()}
    try:
        with open(SIDECAR_FILE, "w", encoding="utf-8") as f:
            json.dump(info, f)
        os.chmod(SIDECAR_FILE, 0o600)      # carries the API token — owner only
    except OSError as e:
        print(f"warning: could not write {SIDECAR_FILE}: {e}", file=sys.stderr, flush=True)

    # Also emit on stdout so a parent process can read it without polling a file.
    print(json.dumps(info), flush=True)

    # A bare SIGTERM (the front-end quitting, `pkill`, logout) kills the process
    # without unwinding, so the finally below never runs and a stale handshake
    # outlives the core. Turn it into a normal shutdown instead.
    import signal

    def _shutdown(_signum, _frame):
        raise KeyboardInterrupt

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _shutdown)
        except (ValueError, OSError):
            pass                          # not on the main thread — best effort

    if exit_with_parent:
        _exit_when_orphaned(httpd)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            os.remove(SIDECAR_FILE)        # never leave a stale port/token behind
        except OSError:
            pass


def run_browser():
    import webbrowser
    backend = Backend()
    httpd, broadcast, port = _serve_http(backend, "127.0.0.1", 0, None)
    backend.emit = broadcast
    url = f"http://127.0.0.1:{port}/"
    print(f"Native window unavailable — opened in your browser: {url}", flush=True)
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try: httpd.serve_forever()
    except KeyboardInterrupt: pass


USAGE = (
    "Auto-Keka — automatic Keka attendance\n"
    "  Auto-Keka                 open the dashboard window (default)\n"
    "  Auto-Keka --serve [port]  run the headless API (for the native client)\n"
    "  Auto-Keka --punch in|out  clock in/out once (used by the scheduler)\n"
    "  Auto-Keka --check         run the reauth watchdog\n"
    "  Auto-Keka --version       print the version and exit\n"
    "  Auto-Keka --help          show this help\n"
)


def main():
    # Headless dispatch — lets the compiled binary act as its own punch/check
    # tool for the scheduler:  Auto-Keka --punch in|out  ·  Auto-Keka --check
    args = sys.argv[1:]
    # Trivial, side-effect-free flags first — these double as the CI build
    # smoke test (a compiled binary that can't even print its version is broken).
    if args[:1] in (["--version"], ["-v"]):
        print(f"Auto-Keka {kc.APP_VERSION}")
        return
    if args[:1] in (["--help"], ["-h"]):
        print(USAGE)
        return
    if args[:1] == ["--punch"] and len(args) > 1 and args[1] in ("in", "out"):
        kc.run_punch(args[1], kc.log_path(f"keka_punch_{args[1]}.log"))
        return
    if args[:1] == ["--check"]:
        import keka_check
        keka_check.main()
        return
    # An UNRECOGNIZED flag must NOT fall through to launching the GUI (that made
    # e.g. `Auto-Keka --foo` open a window and hang in headless contexts). Only a
    # bare invocation (no args) opens the dashboard.
    if args and args[0].startswith("-") and args[0] not in ("--serve",):
        print(f"unknown option: {args[0]}\n\n{USAGE}", file=sys.stderr)
        sys.exit(2)
    if args[:1] == ["--serve"]:
        # Auto-Keka --serve [port] [--exit-with-parent]
        #   headless API for a native front-end (the Swift macOS client).
        rest = args[1:]
        exit_with_parent = "--exit-with-parent" in rest
        positional = [a for a in rest if not a.startswith("--")]
        try:
            port = int(positional[0]) if positional else 0
        except ValueError:
            print(f"invalid port: {positional[0]}", file=sys.stderr); sys.exit(2)
        run_serve(port, exit_with_parent=exit_with_parent)
        return

    if not os.path.exists(UI_HTML):
        print(f"UI file not found: {UI_HTML}", file=sys.stderr); sys.exit(1)
    try:
        run_native()
    except Exception as e:
        print(f"(native window unavailable: {e})", flush=True)
        run_browser()


if __name__ == "__main__":
    main()
