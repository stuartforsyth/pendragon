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
# Always (re)start, so the server runs the current code after an update.
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Restarting the Pendragon server (was PID $(cat "$PIDFILE"))..."
  kill "$(cat "$PIDFILE")"
  for _ in $(seq 1 20); do kill -0 "$(cat "$PIDFILE")" 2>/dev/null || break; sleep 0.1; done
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
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL/" >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then
  open "$URL/"
fi
