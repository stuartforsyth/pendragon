#!/usr/bin/env bash
# Launch the Pendragon GM web app: sets up the venv (first run only), starts the
# server detached on http://127.0.0.1:8020 and opens the GM console.
# Re-running it restarts the server (picking up code changes). Stop with ./stop.sh.  Foreground/dev mode: .venv/bin/python -m web --reload
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
PORT="${PENDRAGON_PORT:-8020}"
URL="http://127.0.0.1:$PORT"

if [ ! -d .venv ]; then
  echo "Setting up the virtual environment (first run only)..."
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

mkdir -p .run
PIDFILE=".run/server.pid"
# Always (re)start: stop every copy already running (so nothing old keeps
# serving open tabs), then start fresh on the current code.
RESTART=""
if "$DIR/stop.sh" >/dev/null 2>&1; then
  RESTART=1
  echo "Stopped the server that was already running."
fi
nohup .venv/bin/python -m web --port "$PORT" > .run/server.log 2>&1 &
echo $! > "$PIDFILE"
disown
echo "Started Pendragon server (PID $(cat "$PIDFILE"))."

echo -n "Waiting for the server"
for _ in $(seq 1 40); do
  if curl -s -o /dev/null "$URL/healthz"; then
    echo " — ready."
    break
  fi
  echo -n "."
  sleep 0.25
done
if ! curl -s -o /dev/null "$URL/healthz"; then
  echo
  echo "The server didn't come up. Last lines of .run/server.log:" >&2
  tail -20 .run/server.log >&2
  exit 1
fi

echo "GM console:   $URL/"
echo "Table screen: $URL/table   (open it from the console and share that window on Discord)"
# Launch means a browser session too — unless one is already open: after a restart the
# open tabs reload themselves and reconnect within a couple of seconds, so wait for them
# (set PENDRAGON_NO_BROWSER=1 to never open one).
if [ -n "$PENDRAGON_NO_BROWSER" ]; then
  echo "(PENDRAGON_NO_BROWSER is set; no window opened.)"
  exit 0
fi
if [ -n "$RESTART" ]; then
  echo -n "Looking for open tabs"
  for _ in $(seq 1 14); do
    if curl -s "$URL/healthz" | grep -Eq '"viewers": ?[1-9]'; then
      echo " — found; they reload themselves, no new window opened."
      exit 0
    fi
    echo -n "."
    sleep 0.5
  done
  echo " none."
fi
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL/" >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then
  open "$URL/"
fi
