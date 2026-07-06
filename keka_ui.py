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
import keka_check as kck

UI_HTML = os.path.join(kc.SCRIPT_DIR, "ui", "index.html")
VENV_PY = sys.executable


# ─── Backend: all state + actions, push-mechanism-agnostic (self.emit) ────────
class Backend:
    def __init__(self):
        self.emit = lambda obj: None    # runner sets this (native evaluate_js / SSE)
        self._pw_lock = threading.Lock()  # serialize ALL Playwright/session access
        self._otp_event = threading.Event()
        self._otp_value = None
        self._status = None
        self.log = logging.getLogger("keka_ui")
        self.log.setLevel(logging.INFO)
        self.log.handlers = [logging.NullHandler()]
        self._status = self._status_from_history()
        threading.Thread(target=self._status_refresher, daemon=True).start()

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
                with self._pw_lock:
                    s = kc.get_status()
                if s:
                    self._status = s
                    self.push_state()
            except Exception:
                pass
            time.sleep(90)

    # ── JS API methods ──────────────────────────────────────────────────────
    def get_state(self):
        kc.reload_config()
        env = kc._load_env()
        exp = kck.remember_cookie_expiry()
        days = max(0, min(14, int((exp - time.time()) / 86400))) if exp else 0
        hist = kc.read_history(200)
        cin, cout = self._today_punches(hist)
        activity = [{"time": h["time"], "msg": h["msg"], "kind": h["kind"]}
                    for h in reversed(hist)][:5]
        return {
            "clockedIn": self._status == "in",
            "clockInAt": cin, "clockOutAt": cout,
            "scheduleIn": env.get("KEKA_IN_TIME", "09:00"),
            "scheduleOut": env.get("KEKA_OUT_TIME", "18:00"),
            "sessionDaysLeft": days,
            "week": self._build_week(hist),
            "activity": activity,
            "config": {"url": env.get("KEKA_BASE_URL", ""), "email": env.get("KEKA_EMAIL", "")},
        }

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
                kc.log_history("info", "Session refreshed")
            try:
                self._status = kc.get_status()
            except Exception:
                pass
        self.push_state()
        exp = kck.remember_cookie_expiry()
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
        kc.update_env({"KEKA_BASE_URL": (obj.get("url") or "").strip(),
                       "KEKA_EMAIL": (obj.get("email") or "").strip(),
                       "KEKA_PASSWORD": obj.get("password") or ""})
        kc.log_history("info", "Credentials saved")
        return {"ok": True}

    def apply_schedule(self, obj):
        obj = obj or {}
        it, ot = (obj.get("inTime") or "").strip(), (obj.get("outTime") or "").strip()
        kc.update_env({"KEKA_IN_TIME": it, "KEKA_OUT_TIME": ot})
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

    # ── internals ────────────────────────────────────────────────────────────
    def _otp_getter(self, retry=False):
        self.emit({"type": "otp", "retry": bool(retry)})
        self._otp_event.clear()
        self._otp_event.wait()
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
            script = "keka_punch_in.py" if action == "in" else "keka_punch_out.py"
            rc = self._run_stream([VENV_PY, os.path.join(kc.SCRIPT_DIR, script)])
            if rc != 0:
                self.push_log("Session expired — logging in first…")
                if kc.interactive_login(self._otp_getter, self.log, headless=True):
                    rc = self._run_stream([VENV_PY, os.path.join(kc.SCRIPT_DIR, script)])
            try:
                self._status = kc.get_status()
            except Exception:
                pass
        self.push_state()
        ok = rc == 0
        return {"ok": ok, "message": (f"Clocked {'in' if action == 'in' else 'out'}"
                if ok else "Punch failed — check credentials")}


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
    """Exactly the 7 methods the page calls as window.pywebview.api.*"""
    def __init__(self, backend):
        self._b = backend
    def get_state(self):        return self._b.get_state()
    def clock_in(self):         return self._b.clock_in()
    def clock_out(self):        return self._b.clock_out()
    def refresh_session(self):  return self._b.refresh_session()
    def submit_otp(self, code): return self._b.submit_otp(code)
    def save_creds(self, obj):  return self._b.save_creds(obj)
    def apply_schedule(self, obj): return self._b.apply_schedule(obj)


def run_native():
    import webview  # raises if pywebview missing
    backend = Backend()
    window = webview.create_window(
        "Auto-Keka", url=UI_HTML, js_api=Api(backend),
        width=860, height=760, min_size=(560, 640), background_color="#0e5f57",
    )
    backend.emit = lambda obj: _push_native(window, obj)
    webview.start()          # blocks; must be on the main thread


# ─── Browser fallback (stdlib http.server + fetch/SSE) ────────────────────────
_SHIM = """
<script>
(function(){
  const j=(r)=>r.json();
  const post=(p,b)=>fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})}).then(j);
  window.pywebview={api:{
    get_state:()=>fetch('/api/state').then(j),
    clock_in:()=>post('/api/clock_in'), clock_out:()=>post('/api/clock_out'),
    refresh_session:()=>post('/api/refresh'), submit_otp:(c)=>post('/api/submit_otp',{code:c}),
    save_creds:(o)=>post('/api/save_creds',o), apply_schedule:(o)=>post('/api/apply_schedule',o)}};
  try{const es=new EventSource('/events');es.onmessage=(e)=>{const m=JSON.parse(e.data),K=window.KekaUI||{};
    if(m.type==='log'&&K.onLog)K.onLog(m.entry);else if(m.type==='state'&&K.onState)K.onState(m.state);
    else if(m.type==='otp'&&K.onOtpRequired)K.onOtpRequired(m.retry);else if(m.type==='otpDone'&&K.onOtpDone)K.onOtpDone();};}catch(_){}
})();
</script>
"""


def run_browser():
    import webbrowser
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    backend = Backend()
    subs, sub_lock = [], threading.Lock()

    def emit(obj):
        with sub_lock:
            for q in list(subs):
                q.put(obj)
    backend.emit = emit

    with open(UI_HTML, encoding="utf-8") as f:
        html = f.read().replace("<script>", _SHIM + "<script>", 1).encode("utf-8")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _json(self, obj, code=200):
            body = json.dumps(obj).encode(); self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers()
            self.wfile.write(body)
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html))); self.end_headers(); self.wfile.write(html)
            elif self.path == "/api/state":
                self._json(backend.get_state())
            elif self.path == "/events":
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
            n = int(self.headers.get("Content-Length", 0) or 0)
            try: body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError: body = {}
            routes = {"/api/clock_in": lambda: backend.clock_in(),
                      "/api/clock_out": lambda: backend.clock_out(),
                      "/api/refresh": lambda: backend.refresh_session(),
                      "/api/submit_otp": lambda: backend.submit_otp(body.get("code")),
                      "/api/save_creds": lambda: backend.save_creds(body),
                      "/api/apply_schedule": lambda: backend.apply_schedule(body)}
            fn = routes.get(self.path)
            if not fn: self.send_error(404); return
            try: self._json(fn())
            except Exception as e: self._json({"ok": False, "message": str(e)}, 500)

    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), H)
    url = f"http://127.0.0.1:{port}/"
    print(f"Native window unavailable — opened in your browser: {url}", flush=True)
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try: httpd.serve_forever()
    except KeyboardInterrupt: pass


def main():
    if not os.path.exists(UI_HTML):
        print(f"UI file not found: {UI_HTML}", file=sys.stderr); sys.exit(1)
    try:
        run_native()
    except Exception as e:
        print(f"(native window unavailable: {e})", flush=True)
        run_browser()


if __name__ == "__main__":
    main()
