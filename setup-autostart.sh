#!/bin/bash

# Setup script for Lumiera WhatsApp Copilot auto-start service

set -e

echo "================================================"
echo "Lumiera WhatsApp Copilot - Auto-Start Setup"
echo "================================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root or with sudo"
    echo "   Run: sudo ./setup-autostart.sh"
    exit 1
fi

echo "✅ Running as root"
echo ""

# Stop any manually running instances
echo "🛑 Stopping any manually running instances..."
pkill -f "uvicorn src.main:app" || true
sleep 2

# Copy service file
echo "📋 Installing systemd service..."
cp /home/ceeai/whatsapp_api/lumiera-whatsapp.service /etc/systemd/system/
chmod 644 /etc/systemd/system/lumiera-whatsapp.service

# Reload systemd
echo "🔄 Reloading systemd daemon..."
systemctl daemon-reload

# Enable service
echo "✅ Enabling service to start on boot..."
systemctl enable lumiera-whatsapp

# Start service
echo "🚀 Starting service..."
systemctl start lumiera-whatsapp

# Wait a moment
sleep 3

# Check status
echo ""
echo "================================================"
echo "Service Status:"
echo "================================================"
systemctl status lumiera-whatsapp --no-pager

echo ""
echo "================================================"
echo "✅ Setup Complete!"
echo "================================================"
echo ""
echo "The service is now installed and running."
echo ""
echo "Useful commands:"
echo "  sudo systemctl status lumiera-whatsapp   # Check status"
echo "  sudo systemctl restart lumiera-whatsapp  # Restart"
echo "  sudo systemctl stop lumiera-whatsapp     # Stop"
echo "  sudo journalctl -u lumiera-whatsapp -f   # View logs"
echo ""
echo "The server will now automatically start on VPS reboot!"
echo ""
