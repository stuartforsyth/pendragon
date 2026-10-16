@echo off
rem Launch the Pendragon GM web app on Windows: sets up the venv (first run
rem only), opens the GM console, and runs the server in this window.
rem Close the window (or press Ctrl+C) to stop it.
cd /d "%~dp0"
if not exist .venv (
    echo Setting up the virtual environment (first run only^)...
    py -3 -m venv .venv 2>nul || python -m venv .venv
)
.venv\Scripts\python -m pip install -q -r requirements.txt
start "" http://127.0.0.1:8020/
.venv\Scripts\python -m web --port 8020
if errorlevel 1 pause
