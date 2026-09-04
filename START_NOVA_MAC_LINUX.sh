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

# Check PyTorch (needed for assisted learning / transformer fine-tuning)
if ! $PYTHON -c "import torch" 2>/dev/null; then
    echo ""
    echo "⚠️  PyTorch is not installed."
    echo "   Assisted learning ('deep learn') requires PyTorch for transformer fine-tuning."
    echo "   Install with: bash SETUP_INSTALL_DEPENDENCIES.sh"
    echo "   The chat and memory system still work without it."
    echo ""
fi

# Check numpy
if ! $PYTHON -c "import numpy" 2>/dev/null; then
    echo "   NumPy not found (optional, improves PyTorch speed)"
fi

# Add the small offline helpers for phone QR pairing, scene inspection, and
# encrypted portable backups. Nova still starts if they cannot be added.
if ! $PYTHON -c "import qrcode, qrcode.image.svg, cryptography, PIL" 2>/dev/null; then
    if [ -f requirements-runtime.txt ]; then
        echo "[INSTALL] Adding phone QR and encrypted backup support..."
        $PYTHON -m pip install -r requirements-runtime.txt || true
    fi
fi

echo ""
echo "[OK] Python environment checked."

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

$PYTHON nova_enhanced_server.py 3000
