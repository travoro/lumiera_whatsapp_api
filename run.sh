#!/bin/bash

# Lumiera WhatsApp Copilot - Run Script

echo "Starting Lumiera WhatsApp Copilot..."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Error: .env file not found!"
    echo "Please copy .env.example to .env and configure your credentials."
    exit 1
fi

# Create logs directory if it doesn't exist
mkdir -p logs

# Run the application
echo "Starting server on port ${PORT:-8000}..."
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
python -m uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}
