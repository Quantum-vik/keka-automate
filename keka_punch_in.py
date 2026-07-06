"""
Keka Auto Punch-In — reuses the saved session (see keka_setup.py).
Scheduled at 9:00 AM Mon-Fri via cron.
"""

import os
import sys

# Ensure keka_common is importable when cron runs this by absolute path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import keka_common as kc

if __name__ == "__main__":
    kc.run_punch("in", kc.log_path("keka_punch_in.log"))
