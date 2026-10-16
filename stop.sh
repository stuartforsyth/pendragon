#!/usr/bin/env bash
# Stop the Pendragon GM web app started by ./launch.sh.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="$DIR/.run/server.pid"
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  kill "$(cat "$PIDFILE")" && echo "Stopped Pendragon server (PID $(cat "$PIDFILE"))."
else
  echo "Pendragon server isn't running."
fi
rm -f "$PIDFILE"
