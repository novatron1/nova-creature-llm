#!/data/data/com.termux/files/usr/bin/bash
# Nova Creature — Termux Android Setup
echo "========================================"
echo "  NOVA CREATURE — Termux Android Setup"
echo "========================================"
echo ""

# Update packages
echo "[1/4] Updating Termux packages..."
pkg update -y && pkg upgrade -y

# Install Python
echo "[2/4] Installing Python..."
pkg install -y python

# Navigate to Nova directory
echo "[3/4] Setting up Nova..."
NOVA_DIR="$HOME/nova_creature"
mkdir -p "$NOVA_DIR"

# Check if running from extracted ZIP
if [ -f "./nova_server_android.py" ]; then
  echo "  Found Nova files in current directory."
  cp -r ./* "$NOVA_DIR/" 2>/dev/null
elif [ -f "$NOVA_DIR/nova_server_android.py" ]; then
  echo "  Nova files already in $NOVA_DIR"
else
  echo "  Please extract the Nova ZIP into: $NOVA_DIR"
  echo "  Or run this script from the extracted folder."
  exit 1
fi

# Create run script
cat > "$HOME/nova_run.sh" << 'RUNEOF'
#!/data/data/com.termux/files/usr/bin/bash
cd ~/nova_creature
echo "========================================"
echo "  NOVA CREATURE — Starting Server"
echo "========================================"
echo ""
# Get local IP
IP=$(ip -4 addr show wlan0 2>/dev/null | grep -oP 'inet \K[\d.]+' || echo "127.0.0.1")
PORT=3000

python3 nova_server_android.py $PORT &
SERVER_PID=$!
sleep 2

echo ""
echo "  ✅ Server running!"
echo "  📱 Open on THIS phone:  http://127.0.0.1:$PORT"
echo "  🌐 Open from ANY device: http://$IP:$PORT"
echo "  🛑 Stop:  kill $SERVER_PID"
echo ""

# Auto-open in browser
am start -a android.intent.action.VIEW -d "http://127.0.0.1:$PORT" 2>/dev/null

wait $SERVER_PID
RUNEOF
chmod +x "$HOME/nova_run.sh"

echo "[4/4] Setup complete!"
echo ""
echo "========================================"
echo "  TO START NOVA:"
echo "    bash ~/nova_run.sh"
echo ""
echo "  Access from any device on same WiFi:"
echo "    http://YOUR_ANDROID_IP:3000"
echo "========================================"
