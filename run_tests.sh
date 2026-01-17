#!/bin/bash
# Helper script to run tests with proper environment setup

set -a  # Export all variables
source .env.test
set +a

source venv/bin/activate
pytest tests/ "$@"
