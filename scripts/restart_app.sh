#!/bin/bash
# Restart WhatsApp API application

APP_DIR="/home/ceeai/whatsapp_api"
VENV_PYTHON="$APP_DIR/venv/bin/python"

echo "🔄 Restarting WhatsApp API..."

# Kill existing processes
echo "🔫 Stopping existing processes..."
lsof -ti:8000 | xargs kill -9 2>/dev/null
pkill -9 -f "uvicorn src.main:app" 2>/dev/null
sleep 2

# Verify stopped
REMAINING=$(ps aux | grep -E "uvicorn src.main:app" | grep -v grep)
if [ ! -z "$REMAINING" ]; then
    echo "⚠️  Warning: Some processes still running"
    echo "$REMAINING"
    exit 1
fi

echo "✅ Old processes stopped"

# Start new process
echo "🚀 Starting application..."
cd "$APP_DIR"
nohup "$VENV_PYTHON" -m uvicorn src.main:app --host 0.0.0.0 --port 8000 > /dev/null 2>&1 &

# Wait and verify
sleep 3

NEW_PROCESS=$(ps aux | grep -E "uvicorn src.main:app" | grep -v grep)
if [ -z "$NEW_PROCESS" ]; then
    echo "❌ Failed to start application"
    exit 1
fi

echo "✅ Application started successfully"
echo "📋 Process info:"
ps aux | grep -E "uvicorn src.main:app" | grep -v grep

# Check logs
echo ""
echo "📝 Recent logs:"
tail -n 10 "$APP_DIR/logs/app.log"
