#!/usr/bin/env bash
# Stop every Pendragon GM web server for this folder: the one ./launch.sh
# recorded, any other copy started here, and anything else on the port.
# Asks politely first, then forces any that hang on (open tabs keep a live
# connection, which can stop a server from exiting).
# Exit status: 0 if something was stopped, 1 if nothing was running.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PENDRAGON_PORT:-8020}"
PIDFILE="$DIR/.run/server.pid"

pids=""
[ -f "$PIDFILE" ] && pids="$(cat "$PIDFILE")"
for p in $(pgrep -f '^[^ ]*python[0-9.]* -m web( |$)' 2>/dev/null); do
  # only servers started from this folder
  [ "$(readlink "/proc/$p/cwd" 2>/dev/null)" = "$DIR" ] && pids="$pids $p"
done
if command -v ss >/dev/null 2>&1; then
  pids="$pids $(ss -ltnpH "sport = :$PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2)"
elif command -v lsof >/dev/null 2>&1; then
  pids="$pids $(lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null)"
fi
pids="$(for p in $pids; do kill -0 "$p" 2>/dev/null && echo "$p"; done | sort -u | tr '\n' ' ')"
rm -f "$PIDFILE"

if [ -z "${pids// /}" ]; then
  echo "Pendragon server isn't running."
  exit 1
fi
kill $pids 2>/dev/null
for _ in $(seq 1 30); do
  alive=""; for p in $pids; do kill -0 "$p" 2>/dev/null && alive="$alive $p"; done
  [ -z "$alive" ] && break
  sleep 0.1
done
[ -n "$alive" ] && kill -9 $alive 2>/dev/null
echo "Stopped Pendragon server (PID ${pids% })."
exit 0
