#!/bin/bash
cd "$(dirname "$0")"
PIDFILE="/tmp/nova_server.pid"
LOGFILE="/tmp/nova_server.log"
PORT=3000

echo "=== Nova Creature Live Server ==="
echo "Starting on port $PORT..."
echo "PID file: $PIDFILE"
echo "Log file: $LOGFILE"
echo ""

# Kill any existing instance
[ -f "$PIDFILE" ] && kill $(cat "$PIDFILE") 2>/dev/null && sleep 1

# Start server with auto-restart
while true; do
  echo "[$(date)] Starting nova_live_server.py on port $PORT..."
  python3 -u nova_live_server.py $PORT >> "$LOGFILE" 2>&1
  EXIT_CODE=$?
  echo "[$(date)] Server exited with code $EXIT_CODE. Restarting in 3s..."
  sleep 3
done
