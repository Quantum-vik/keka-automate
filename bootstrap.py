#!/usr/bin/env python3
"""
Auto-Keka bootstrap (macOS / Linux).

This is what the downloadable app runs FIRST. It uses only the Python standard
library, so it works before anything is installed. Its whole job:

  1. If the "light" dependencies (the venv + pip packages that draw the window)
     are missing, install them once — showing a small "Setting up…" splash so
     the user isn't staring at nothing.
  2. Hand off to keka_ui.py, which opens the real panel and installs the HEAVY
     dependencies (Chromium + tesseract) in the background, live in that panel.

So the user just downloads, double-clicks, and follows the on-screen wizard —
no terminal, no ./setup.sh.
"""

import os
import sys
import queue
import threading
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def venv_python():
    return os.path.join(HERE, ".venv", "bin", "python")


def light_ready():
    """True if the venv exists and can import pywebview (the window toolkit)."""
    py = venv_python()
    if not os.path.exists(py):
        return False
    try:
        return subprocess.run([py, "-c", "import webview"],
                              capture_output=True).returncode == 0
    except Exception:
        return False


def run_light(on_line):
    """Run setup.sh --phase light, streaming each output line to on_line()."""
    cmd = ["bash", os.path.join(HERE, "setup.sh"), "--phase", "light"]
    try:
        p = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
    except Exception as e:
        on_line(f"Could not start setup: {e}")
        return 1
    for line in p.stdout:
        line = line.rstrip()
        if line:
            on_line(line)
    p.wait()
    return p.returncode


def launch_app():
    """Replace this process with the real app (venv python keka_ui.py)."""
    py = venv_python()
    ui = os.path.join(HERE, "keka_ui.py")
    if not os.path.exists(py):
        # Light install failed — fall back to the system interpreter so the user
        # at least gets an error dialog from keka_ui rather than a silent exit.
        py = sys.executable
    os.execv(py, [py, ui])


# ── Splash (tkinter if available; console otherwise) ──────────────────────────
def bootstrap():
    if light_ready():
        launch_app()
        return

    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        # No tkinter yet (fresh Linux) — fall back to plain console output.
        print("Setting up Auto-Keka (first run, one time)…\n")
        rc = run_light(lambda l: print("  " + l))
        if rc != 0:
            print("\nSetup could not finish. Try running:  ./setup.sh --phase light")
            sys.exit(1)
        launch_app()
        return

    q = queue.Queue()
    result = {"rc": None}

    root = tk.Tk()
    root.title("Auto-Keka")
    root.configure(bg="#eef4f2")
    root.resizable(False, False)
    w, h = 420, 190
    root.update_idletasks()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 3
    root.geometry(f"{w}x{h}+{x}+{y}")

    tk.Label(root, text="Setting up Auto-Keka", bg="#eef4f2", fg="#0f3a34",
             font=("Helvetica", 16, "bold")).pack(pady=(26, 4))
    tk.Label(root, text="Getting the app ready — this happens only once.",
             bg="#eef4f2", fg="#4b6b64", font=("Helvetica", 11)).pack()
    bar = ttk.Progressbar(root, mode="indeterminate", length=320)
    bar.pack(pady=16)
    bar.start(12)
    status = tk.Label(root, text="Starting…", bg="#eef4f2", fg="#77938c",
                      font=("Helvetica", 10), width=52, anchor="center")
    status.pack()

    def work():
        result["rc"] = run_light(lambda l: q.put(l))
        q.put(None)  # sentinel: done

    def poll():
        try:
            while True:
                line = q.get_nowait()
                if line is None:
                    bar.stop()
                    if result["rc"] == 0:
                        root.destroy()
                    else:
                        status.config(text="Setup didn't finish. Close and try again.",
                                      fg="#c0603a")
                        tk.Button(root, text="Close", command=root.destroy).pack()
                    return
                # keep only the human part of a log line
                status.config(text=line[-60:])
        except queue.Empty:
            pass
        root.after(120, poll)

    threading.Thread(target=work, daemon=True).start()
    root.after(120, poll)
    root.mainloop()

    if result["rc"] == 0:
        launch_app()


if __name__ == "__main__":
    bootstrap()
