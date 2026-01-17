#!/bin/bash
# Setup development tools for auto-testing and auto-restart

echo "Setting up development tools..."

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Error: Virtual environment not found!"
    exit 1
fi

# Install/update requirements
echo "Installing dependencies..."
pip install -r requirements.txt

# Setup pre-commit hooks
echo "Setting up pre-commit hooks..."
pre-commit install

echo ""
echo "✓ Development tools setup complete!"
echo ""
echo "Available commands:"
echo "  ./run.sh              - Run app with auto-restart on changes"
echo "  ./watch_tests.sh      - Auto-run tests on file changes"
echo "  ./run_tests.sh        - Run tests once"
echo "  pre-commit run --all-files  - Run all pre-commit hooks manually"
echo ""
echo "Pre-commit hooks will automatically run tests before each commit."
