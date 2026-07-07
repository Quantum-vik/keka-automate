#!/usr/bin/env bash
# Run me to start Auto-Keka:  ./Auto-Keka.sh   (first run installs everything).
cd "$(dirname "$0")" || exit 1
exec python3 bootstrap.py
