#!/bin/bash
# Run linters before committing
# Usage: ./lint.sh

set -e

echo "🔍 Running code quality checks..."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo ""
echo "📝 Running flake8..."
flake8 src/ --max-line-length=120 --extend-ignore=E203,W503,E501,F841 --exclude=venv,__pycache__,.git

echo ""
echo "🎨 Checking black formatting..."
black --check src/ tests/

echo ""
echo "📦 Checking isort..."
isort --check-only --profile black src/ tests/

echo ""
echo "🔍 Running mypy type checker..."
mypy src/ --ignore-missing-imports --no-strict-optional

echo ""
echo "✅ All checks passed! Ready to commit."
