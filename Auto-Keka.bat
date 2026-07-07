@echo off
rem Double-click me to start Auto-Keka. First run installs everything.
cd /d "%~dp0"
powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1"
