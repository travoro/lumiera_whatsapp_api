# Development Workflow

This document describes the automated development tools for testing and restarting the application.

## Quick Setup

Run the setup script to install all development tools:

```bash
./setup_dev_tools.sh
```

## Auto-Restart App on Changes

The application will automatically restart when you modify any Python files:

```bash
./run.sh
```

This uses `uvicorn --reload` which watches for file changes in your source code.

## Auto-Run Tests on Changes

Watch for file changes and automatically run tests:

```bash
./watch_tests.sh
```

This will:
- Monitor `src/` and `tests/` directories
- Automatically run tests when files change
- Clear the screen before each test run
- Show verbose output

### Watch Specific Tests

Watch and run only specific tests:

```bash
source venv/bin/activate
set -a && source .env.test && set +a
ptw tests/test_specific_file.py -- -v
```

## Run Tests Manually

Run all tests once:

```bash
./run_tests.sh
```

Run with coverage report:

```bash
./run_tests.sh --cov=src --cov-report=html
```

## Pre-Commit Hooks

Pre-commit hooks automatically run before each git commit to ensure code quality:

### What Runs Automatically
1. **Black** - Code formatting
2. **Flake8** - Linting
3. **isort** - Import sorting
4. **pytest** - All unit tests

### Setup
```bash
# Already done by setup_dev_tools.sh
pre-commit install
```

### Run Manually
```bash
# Run all hooks on all files
pre-commit run --all-files

# Run specific hook
pre-commit run black --all-files
pre-commit run pytest --all-files
```

### Skip Hooks (Use Sparingly)
```bash
# Skip all hooks for a commit
git commit -m "message" --no-verify

# Skip specific hook
SKIP=pytest git commit -m "message"
```

## Development Workflow Example

### Terminal 1: App with Auto-Restart
```bash
./run.sh
```

### Terminal 2: Tests with Auto-Run
```bash
./watch_tests.sh
```

Now when you make changes:
- The app automatically restarts (Terminal 1)
- Tests automatically run (Terminal 2)
- Pre-commit hooks run when you commit

## Pytest-Watch Options

Customize `watch_tests.sh` with these options:

```bash
ptw tests/ src/ \
  --clear           # Clear screen before each run
  --onpass "echo OK"  # Run command after tests pass
  --onfail "echo FAIL"  # Run command after tests fail
  --ignore=venv/    # Ignore directories
  --spool 200       # Delay in ms before running tests
  -- -v -x          # pytest args: verbose, stop on first failure
```

## CI/CD Integration

For CI/CD pipelines, use the standard test command:

```bash
./run_tests.sh --cov=src --cov-report=xml
```

This ensures consistency between local development and CI environments.

## Troubleshooting

### Tests not running automatically
- Check that `pytest-watch` is installed: `pip list | grep pytest-watch`
- Verify you're in the correct directory
- Check file permissions: `chmod +x watch_tests.sh`

### Pre-commit hooks failing
- Run manually to see errors: `pre-commit run --all-files`
- Update hooks: `pre-commit autoupdate`
- Re-install: `pre-commit uninstall && pre-commit install`

### App not restarting
- Check that uvicorn is running with `--reload` flag
- Verify you're saving files in watched directories
- Check uvicorn logs for errors
