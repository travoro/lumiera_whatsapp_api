#!/bin/bash
# Manual log rotation script for server.log and server.error.log
# Run with: sudo ./rotate-server-logs.sh

set -e

LOG_DIR="/home/ceeai/whatsapp_api/logs"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

cd "$LOG_DIR"

echo "🔄 Rotating server logs..."

# Rotate server.log
if [ -f "server.log" ] && [ -s "server.log" ]; then
    echo "📦 Archiving server.log ($(du -h server.log | cut -f1))"
    gzip -c server.log > "archive/server.log.$TIMESTAMP.gz"
    > server.log  # Truncate file
    echo "✅ server.log rotated"
else
    echo "⏭️  server.log doesn't exist or is empty"
fi

# Rotate server.error.log
if [ -f "server.error.log" ] && [ -s "server.error.log" ]; then
    echo "📦 Archiving server.error.log ($(du -h server.error.log | cut -f1))"
    gzip -c server.error.log > "archive/server.error.log.$TIMESTAMP.gz"
    > server.error.log  # Truncate file
    echo "✅ server.error.log rotated"
else
    echo "⏭️  server.error.log doesn't exist or is empty"
fi

echo ""
echo "✅ Rotation complete!"
echo "📁 Archived logs in: $LOG_DIR/archive/"
echo "📊 Current log sizes:"
ls -lh server.log server.error.log 2>/dev/null || echo "   No active server logs"
