#!/usr/bin/env bash
# Smart Speaker installer for Raspberry Pi 4 + Pirate Audio 3W Stereo Amp
set -euo pipefail

echo "=== Smart Speaker installer ==="

# 1. System packages
echo "[1/5] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y \
    python3-pip python3-venv \
    mpg123 \
    libportaudio2 portaudio19-dev \
    libatlas-base-dev \
    libblas-dev liblapack-dev \
    fonts-dejavu-core

# 2. Enable SPI (needed for ST7789 display)
echo "[2/5] Ensuring SPI is enabled..."
if ! grep -q "^dtparam=spi=on" /boot/firmware/config.txt 2>/dev/null && \
   ! grep -q "^dtparam=spi=on" /boot/config.txt 2>/dev/null; then
    CONFIG=/boot/firmware/config.txt
    [ -f "$CONFIG" ] || CONFIG=/boot/config.txt
    echo "dtparam=spi=on" | sudo tee -a "$CONFIG"
    echo "  SPI enabled — reboot required after install"
fi

# 3. Python virtual environment
echo "[3/5] Creating Python virtual environment..."
python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt

# 4. Pre-download Whisper model so first run is instant
echo "[4/5] Downloading Whisper tiny.en model (~75 MB)..."
python3 -c "
from faster_whisper import WhisperModel
WhisperModel('tiny.en', device='cpu', compute_type='int8')
print('  Whisper model ready')
"

# 5. systemd service
echo "[5/5] Installing systemd service..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE=/etc/systemd/system/smart-speaker.service

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Smart Speaker (Claude)
After=network-online.target sound.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
Environment="ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-REPLACE_ME}"
ExecStart=$SCRIPT_DIR/venv/bin/python $SCRIPT_DIR/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable smart-speaker.service

echo ""
echo "=== Install complete ==="
echo ""
echo "Next steps:"
echo "  1. Set your API key:"
echo "     sudo systemctl edit smart-speaker"
echo "     Add:  Environment=ANTHROPIC_API_KEY=sk-ant-..."
echo ""
echo "  2. Reboot (required if SPI was just enabled):"
echo "     sudo reboot"
echo ""
echo "  3. Start the service:"
echo "     sudo systemctl start smart-speaker"
echo ""
echo "  4. Check logs:"
echo "     journalctl -u smart-speaker -f"
