#!/usr/bin/env bash
# Double-click (or run) to launch the Pendragon GM tools.
# Change into this script's own directory so it works from anywhere.
cd "$(dirname "$0")" || exit 1

# Prefer python3, fall back to python.
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "Python 3 is not installed or not on your PATH." >&2
    read -r -p "Press Enter to close..." _
    exit 1
fi

"$PY" pendragon.py
status=$?

# If something went wrong, keep the window open so the error is readable.
if [ $status -ne 0 ]; then
    echo
    echo "pendragon.py exited with status $status." >&2
    read -r -p "Press Enter to close..." _
fi
exit $status
