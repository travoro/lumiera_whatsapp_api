#!/bin/bash
# Quick deploy script: commit, push, test, and restart app
# Usage: ./deploy_local.sh "commit message"

set -e  # Exit on error

COMMIT_MSG="${1:-Update: Auto-deploy changes}"

echo "🚀 Starting local deployment..."
echo ""

# Check git configuration
if ! git config user.name &>/dev/null || ! git config user.email &>/dev/null; then
    echo "❌ Git is not configured!"
    echo "Please configure git first:"
    echo "  git config --global user.name 'Your Name'"
    echo "  git config --global user.email 'your.email@example.com'"
    exit 1
fi

echo "👤 Git user: $(git config user.name) <$(git config user.email)>"
echo ""

# 1. Git status check
echo "📋 Current git status:"
git status --short
echo ""

# 2. Add all changes
echo "➕ Adding changes to git..."
git add -A
echo ""

# 3. Commit
echo "💾 Committing changes..."
git commit -m "$COMMIT_MSG" || echo "No changes to commit"
echo ""

# 4. Push
echo "📤 Pushing to remote..."
git push origin main
echo ""

# 5. Run tests
echo "🧪 Running tests..."
./run_tests.sh
TEST_EXIT_CODE=$?
echo ""

if [ $TEST_EXIT_CODE -ne 0 ]; then
    echo "❌ Tests failed! Exit code: $TEST_EXIT_CODE"
    echo "Fix the issues and try again."
    exit $TEST_EXIT_CODE
fi

echo "✅ Tests passed!"
echo ""

# 6. Kill any manually running processes
echo "🔄 Stopping any running instances..."
MANUAL_PIDS=$(pgrep -f "python.*uvicorn.*src.main:app" 2>/dev/null || true)
if [ -n "$MANUAL_PIDS" ]; then
    echo "Found manually running processes: $MANUAL_PIDS"
    echo "Killing them..."
    kill $MANUAL_PIDS 2>/dev/null || true
    sleep 2
    # Force kill if still running
    kill -9 $MANUAL_PIDS 2>/dev/null || true
    echo "✓ Stopped manually running instances"
fi
echo ""

# 7. Restart app via systemd
echo "🔄 Starting application via systemd..."
sudo systemctl restart lumiera-whatsapp.service
sleep 3
sudo systemctl status lumiera-whatsapp.service --no-pager
echo ""

echo "✨ Deployment complete!"
echo ""
echo "📊 CI/CD will now run on GitHub:"
echo "   https://github.com/travoro/lumiera_whatsapp_api/actions"
