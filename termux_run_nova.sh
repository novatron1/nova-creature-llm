#!/data/data/com.termux/files/usr/bin/bash
# Nova Creature — Quick Start for Termux
cd "$(dirname "$0")"
PORT=3000
IP=$(ip -4 addr show wlan0 2>/dev/null | grep -oP 'inet \K[\d.]+' || echo "127.0.0.1")

echo "Starting Nova Creature on port $PORT..."
python3 nova_server_android.py $PORT
