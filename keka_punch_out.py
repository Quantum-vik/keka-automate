"""
Keka Auto Punch-Out — reuses the saved session (see keka_setup.py).
Run Mon-Fri by the OS scheduler with --scheduled (catch-up window applies);
the app's manual button runs it without the flag.
"""

import os
import sys

# Ensure keka_common is importable when the scheduler runs this by absolute path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import keka_common as kc

if __name__ == "__main__":
    kc.run_punch("out", kc.log_path("keka_punch_out.log"),
                 scheduled="--scheduled" in sys.argv[1:])
