#!/bin/bash
# Auto-run tests when files change

set -a  # Export all variables
source .env.test
set +a

source venv/bin/activate

# Run pytest-watch
# --clear: Clear screen before each run
# --onpass: Run command after tests pass
# --ignore: Ignore these directories
ptw tests/ src/ \
  --clear \
  --ignore=venv/ \
  --ignore=logs/ \
  --ignore=.git/ \
  --ignore=__pycache__/ \
  -- -v
