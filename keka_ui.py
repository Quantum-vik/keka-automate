"""
Keka Automate — desktop control panel (Tkinter, cross-platform).

    python keka_ui.py

- Set your Keka URL / email / password and clock-in / clock-out times.
- Clock in or out on demand.
- "Login / Refresh Session" logs in headlessly; when Keka needs the 2FA code
  it pops an OTP box right here — read the code from your email, type it in,
  and it finishes automatically (no browser window).
- "Apply Schedule" installs the per-OS scheduler (launchd / cron / Task
  Scheduler) using the times you set.

Everything runs on a background thread so the window never freezes.
"""

import os
import sys
import queue
import logging
import threading
import subprocess

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keka_common as kc

VENV_PY = sys.executable  # this script is launched by the venv python


class QueueLogHandler(logging.Handler):
    """Routes background-thread log records to the UI via a queue."""
    def __init__(self, q):
        super().__init__()
        self.q = q

    def emit(self, record):
        self.q.put(("log", self.format(record)))


class KekaUI:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.busy = False
        self._otp_event = threading.Event()
        self._otp_value = None

        self.log = logging.getLogger("keka_ui")
        self.log.setLevel(logging.INFO)
        self.log.handlers = []
        h = QueueLogHandler(self.q)
        h.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        self.log.addHandler(h)

        root.title("Keka Automate")
        root.minsize(560, 640)
        self._build()
        self._load_values()
        self.root.after(100, self._drain_queue)

    # ── layout ────────────────────────────────────────────────────────────────
    def _build(self):
        pad = dict(padx=10, pady=6)
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        tk.Label(self.root, text="🕘  Keka Automate",
                 font=("Helvetica", 18, "bold")).pack(pady=(12, 2))
        tk.Label(self.root, text="Auto clock-in / clock-out for your Keka HR portal",
                 fg="#666").pack(pady=(0, 8))

        # Account
        acc = ttk.LabelFrame(self.root, text=" Account ")
        acc.pack(fill="x", **pad)
        self.url_var = tk.StringVar()
        self.email_var = tk.StringVar()
        self.pass_var = tk.StringVar()
        self._row(acc, "Keka URL", self.url_var, 0, hint="https://your-company.keka.com")
        self._row(acc, "Email", self.email_var, 1)
        self._row(acc, "Password", self.pass_var, 2, show="•")
        ttk.Button(acc, text="Save credentials",
                   command=self.on_save_creds).grid(row=3, column=1, sticky="e", padx=8, pady=6)

        # Schedule
        sch = ttk.LabelFrame(self.root, text=" Schedule (Mon–Fri) ")
        sch.pack(fill="x", **pad)
        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self._row(sch, "Clock-in time", self.in_var, 0, hint="HH:MM, e.g. 09:00", width=10)
        self._row(sch, "Clock-out time", self.out_var, 1, hint="HH:MM, e.g. 18:00", width=10)
        ttk.Button(sch, text="Save times & apply schedule",
                   command=self.on_apply_schedule).grid(row=2, column=1, sticky="e", padx=8, pady=6)

        # Actions
        act = ttk.LabelFrame(self.root, text=" Actions ")
        act.pack(fill="x", **pad)
        self.btn_in = ttk.Button(act, text="☀️  Clock In now", command=lambda: self.on_punch("in"))
        self.btn_out = ttk.Button(act, text="🌙  Clock Out now", command=lambda: self.on_punch("out"))
        self.btn_login = ttk.Button(act, text="🔑  Login / Refresh session", command=self.on_login)
        self.btn_in.grid(row=0, column=0, padx=8, pady=8, sticky="ew")
        self.btn_out.grid(row=0, column=1, padx=8, pady=8, sticky="ew")
        self.btn_login.grid(row=0, column=2, padx=8, pady=8, sticky="ew")
        act.columnconfigure((0, 1, 2), weight=1)

        # OTP (hidden until needed)
        self.otp_frame = ttk.LabelFrame(self.root, text=" 2FA — enter the code from your email ")
        self.otp_var = tk.StringVar()
        self.otp_entry = ttk.Entry(self.otp_frame, textvariable=self.otp_var, width=14, font=("Helvetica", 14))
        self.otp_entry.grid(row=0, column=0, padx=8, pady=8)
        self.otp_btn = ttk.Button(self.otp_frame, text="Submit OTP", command=self.on_submit_otp)
        self.otp_btn.grid(row=0, column=1, padx=8, pady=8)
        self.otp_entry.bind("<Return>", lambda e: self.on_submit_otp())

        # Log
        logf = ttk.LabelFrame(self.root, text=" Activity ")
        logf.pack(fill="both", expand=True, **pad)
        self.logbox = scrolledtext.ScrolledText(logf, height=10, state="disabled",
                                                 font=("Menlo", 10), wrap="word")
        self.logbox.pack(fill="both", expand=True, padx=6, pady=6)

        self.status = tk.StringVar(value="Ready.")
        tk.Label(self.root, textvariable=self.status, anchor="w",
                 fg="#333", relief="sunken").pack(fill="x", side="bottom")

    def _row(self, parent, label, var, r, hint=None, show=None, width=34):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(parent, textvariable=var, show=show, width=width).grid(
            row=r, column=1, sticky="w", padx=8, pady=4)
        if hint:
            ttk.Label(parent, text=hint, foreground="#999").grid(
                row=r, column=2, sticky="w", padx=4)
        parent.columnconfigure(1, weight=1)

    def _load_values(self):
        kc.reload_config()
        env = kc._load_env()
        self.url_var.set(env.get("KEKA_BASE_URL", ""))
        self.email_var.set(env.get("KEKA_EMAIL", ""))
        self.pass_var.set(env.get("KEKA_PASSWORD", ""))
        self.in_var.set(env.get("KEKA_IN_TIME", "09:00"))
        self.out_var.set(env.get("KEKA_OUT_TIME", "18:00"))

    # ── helpers ─────────────────────────────────────────────────────────────
    def _log(self, msg):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", msg + "\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def _set_busy(self, busy, status=None):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.btn_in, self.btn_out, self.btn_login):
            b.configure(state=state)
        if status:
            self.status.set(status)

    def _run_bg(self, fn, status):
        if self.busy:
            return
        self._set_busy(True, status)
        threading.Thread(target=self._bg_wrap, args=(fn,), daemon=True).start()

    def _bg_wrap(self, fn):
        try:
            fn()
        except Exception as e:
            self.q.put(("log", f"ERROR: {e}"))
        finally:
            self.q.put(("done", None))

    def _drain_queue(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "otp_prompt":
                    self._show_otp(retry=payload)
                elif kind == "otp_hide":
                    self.otp_frame.pack_forget()
                elif kind == "status":
                    self.status.set(payload)
                elif kind == "done":
                    self._set_busy(False, "Ready.")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_queue)

    # ── OTP bridge (worker thread <-> UI) ────────────────────────────────────
    def _otp_getter(self, retry=False):
        self.q.put(("otp_prompt", retry))
        self._otp_event.clear()
        self._otp_event.wait()          # block worker until Submit OTP
        return self._otp_value

    def _show_otp(self, retry):
        self.otp_frame.pack(fill="x", padx=10, pady=6, before=self.logbox.master)
        self.otp_var.set("")
        self.otp_entry.focus_set()
        self.status.set("Wrong code — try again." if retry else "Enter the OTP emailed to you.")

    def on_submit_otp(self):
        self._otp_value = self.otp_var.get().strip()
        self.q.put(("otp_hide", None))
        self._otp_event.set()

    # ── button handlers ──────────────────────────────────────────────────────
    def on_save_creds(self):
        kc.update_env({
            "KEKA_BASE_URL": self.url_var.get().strip(),
            "KEKA_EMAIL": self.email_var.get().strip(),
            "KEKA_PASSWORD": self.pass_var.get(),
        })
        self._log("Saved credentials to .env")
        self.status.set("Credentials saved.")

    def on_apply_schedule(self):
        it, ot = self.in_var.get().strip(), self.out_var.get().strip()
        if not (self._valid_time(it) and self._valid_time(ot)):
            messagebox.showerror("Invalid time", "Use 24-hour HH:MM, e.g. 09:00 and 18:00.")
            return
        kc.update_env({"KEKA_IN_TIME": it, "KEKA_OUT_TIME": ot})
        self._log(f"Saved times: in {it}, out {ot}")
        self._run_bg(self._apply_schedule, "Installing schedule…")

    def on_punch(self, action):
        self._run_bg(lambda: self._punch(action),
                     f"Clocking {'in' if action == 'in' else 'out'}…")

    def on_login(self):
        self._run_bg(self._login, "Logging in…")

    # ── background workers ───────────────────────────────────────────────────
    def _apply_schedule(self):
        kc.reload_config()
        plat = sys.platform
        if plat == "darwin":
            cmd = ["bash", os.path.join(kc.SCRIPT_DIR, "scheduling", "install_macos.sh")]
        elif plat.startswith("linux"):
            cmd = ["bash", os.path.join(kc.SCRIPT_DIR, "scheduling", "install_linux.sh")]
        elif plat.startswith("win"):
            cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File",
                   os.path.join(kc.SCRIPT_DIR, "scheduling", "install_windows.ps1")]
        else:
            self.log.error("Unsupported OS for scheduling")
            return
        self._stream(cmd)
        self.log.info("Schedule applied.")

    def _punch(self, action):
        kc.reload_config()
        script = "keka_punch_in.py" if action == "in" else "keka_punch_out.py"
        rc = self._stream([VENV_PY, os.path.join(kc.SCRIPT_DIR, script)])
        if rc == 0:
            self.log.info("Done.")
            return
        # Session likely expired and auto-relogin couldn't recover -> full login
        self.log.info("Punch failed — trying an interactive login first…")
        if kc.interactive_login(self._otp_getter, self.log, headless=True):
            self._stream([VENV_PY, os.path.join(kc.SCRIPT_DIR, script)])
            self.log.info("Done.")
        else:
            self.log.error("Login failed — check your credentials and try again.")

    def _login(self):
        kc.reload_config()
        if not kc.EMAIL or not kc.PASSWORD:
            self.log.error("Set your email and password first (Save credentials).")
            return
        ok = kc.interactive_login(self._otp_getter, self.log, headless=True)
        self.log.info("Session ready." if ok else "Login did not complete.")

    # ── utils ────────────────────────────────────────────────────────────────
    def _stream(self, cmd):
        """Run a command, streaming its output to the activity log. Returns rc."""
        try:
            p = subprocess.Popen(cmd, cwd=kc.SCRIPT_DIR, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, bufsize=1)
        except Exception as e:
            self.log.error("Could not run %s: %s", cmd[0], e)
            return 1
        for line in p.stdout:
            line = line.rstrip()
            if line:
                self.q.put(("log", line))
        p.wait()
        return p.returncode

    @staticmethod
    def _valid_time(s):
        try:
            h, m = s.split(":")
            return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
        except Exception:
            return False


def main():
    root = tk.Tk()
    KekaUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
