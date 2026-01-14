#!/bin/bash
# Kill all WhatsApp API processes

echo "🔍 Looking for WhatsApp API processes..."

# Find processes
PROCESSES=$(ps aux | grep -E "uvicorn src.main:app" | grep -v grep | awk '{print $2}')

if [ -z "$PROCESSES" ]; then
    echo "✅ No processes found running"
    exit 0
fi

echo "📋 Found processes: $PROCESSES"

# Kill by port first
echo "🔫 Killing process on port 8000..."
lsof -ti:8000 | xargs kill -9 2>/dev/null

# Kill by process name
echo "🔫 Killing uvicorn processes..."
pkill -9 -f "uvicorn src.main:app" 2>/dev/null

# Wait a moment
sleep 1

# Verify
REMAINING=$(ps aux | grep -E "uvicorn src.main:app" | grep -v grep)

if [ -z "$REMAINING" ]; then
    echo "✅ All processes killed successfully"
else
    echo "⚠️  Some processes may still be running:"
    echo "$REMAINING"
fi
