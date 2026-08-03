@echo off
rem Double-click to launch the Pendragon GM tools on Windows.
rem Run from this script's own folder so it works from anywhere.
cd /d "%~dp0"

rem Prefer the py launcher, then python on PATH.
where py >nul 2>nul
if %errorlevel%==0 (
    py pendragon.py
    goto :done
)
where python >nul 2>nul
if %errorlevel%==0 (
    python pendragon.py
    goto :done
)

echo Python 3 is not installed or not on your PATH.
pause
exit /b 1

:done
rem If the app errored, keep the window open so the message is readable.
if errorlevel 1 (
    echo.
    echo pendragon.py exited with an error.
    pause
)
