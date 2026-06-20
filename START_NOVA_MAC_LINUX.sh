#!/usr/bin/env bash
# Nova Creature — Laptop Full Version
set -e

echo "============================================================"
echo "  NOVA CREATURE — Laptop Full Version"
echo "  Starting Nova Server..."
echo "============================================================"
echo ""

# Check for Python 3
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "[ERROR] Python 3 is not installed."
    echo "Please install Python 3.10+ from https://python.org"
    exit 1
fi

echo "[OK] Found Python: $PYTHON"
$PYTHON --version

# Check for required packages
echo "[CHECK] Verifying required packages..."
$PYTHON -c "import json, http.server, socketserver, uuid" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "[INSTALL] Installing required packages..."
    pip3 install --upgrade pip 2>/dev/null || true
    if [ -f requirements-codex.txt ]; then
        pip3 install -r requirements-codex.txt 2>/dev/null || true
    fi
fi

echo ""
echo "[START] Launching Nova Server on http://127.0.0.1:3000"
echo ""

# Try to open browser
case "$(uname -s)" in
    Darwin)
        open http://127.0.0.1:3000 2>/dev/null &
        ;;
    Linux)
        xdg-open http://127.0.0.1:3000 2>/dev/null &
        ;;
esac

$PYTHON nova_web_server.py 3000
