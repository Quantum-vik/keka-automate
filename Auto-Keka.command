#!/bin/bash
# Double-click me in Finder to start Auto-Keka. First run installs everything.
cd "$(dirname "$0")" || exit 1
exec python3 bootstrap.py
