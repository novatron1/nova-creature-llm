#!/bin/bash
# Nova Creature — Install Dependencies
# Run this before starting Nova for the first time

echo "=== Nova Creature — Installing Dependencies ==="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found. Install Python 3.10+ first."
    exit 1
fi
echo "✅ Python: $(python3 --version)"

# Create venv if needed
if [ ! -d "nova_creature_llm_lab/.venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv nova_creature_llm_lab/.venv
fi

# Activate venv
source nova_creature_llm_lab/.venv/bin/activate

# Ensure pip is up to date
echo "Upgrading pip..."
python3 -m pip install --upgrade pip --quiet

# Install PyTorch (CPU version — works on any laptop)
echo ""
echo "Installing PyTorch (CPU)..."
echo "(This downloads ~120MB — may take a minute)"
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Install other dependencies
echo ""
echo "Installing numpy..."
pip install numpy --quiet

# Verify
echo ""
echo "=== Verification ==="
python3 -c "
import torch
print(f'✅ PyTorch {torch.__version__}')
import numpy
print(f'✅ NumPy {numpy.__version__}')
try:
    import torchvision
    print(f'✅ torchvision {torchvision.__version__}')
except:
    print('⚠️ torchvision not installed (optional)')
print()
print('CUDA available:', torch.cuda.is_available())
if torch.cuda.is_available():
    print('GPU:', torch.cuda.get_device_name(0))
"

echo ""
echo "=== DONE ==="
echo "Run Nova: python3 nova_web_server.py"
echo "Open: http://127.0.0.1:3000"
