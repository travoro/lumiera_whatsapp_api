# Logging Best Practices

## Overview

This directory contains all application logs with automatic rotation and retention policies.

## Log Files

### Active Logs (Check these for debugging)

- **`app.log`** - Main application log
  - Contains: All INFO, WARNING, and ERROR messages
  - Rotation: Automatically rotates at 50 MB
  - Retention: 30 days
  - When rotated: Creates `app.log.2026-01-14_12-30-45.zip`

- **`errors.log`** - Error-only log
  - Contains: ERROR and CRITICAL messages only
  - Rotation: Automatically rotates at 10 MB
  - Retention: 90 days
  - Purpose: Quick error debugging without noise

### System Logs (Managed by Systemd)

- **`server.log`** - Systemd stdout redirect (⚠️ Can grow large)
- **`server.error.log`** - Systemd stderr redirect (⚠️ Can grow large)
  - These are created by systemd when running as a service
  - **Not automatically rotated** - Must be rotated manually or with logrotate
  - **Recommendation**: Use `app.log` instead for debugging (has better rotation)

#### Manual Rotation
```bash
# Rotate server logs manually
sudo ./rotate-server-logs.sh
```

#### Automatic Rotation (One-time setup)
```bash
# Install logrotate configuration
sudo cp logrotate.conf /etc/logrotate.d/lumiera-whatsapp
sudo logrotate -f /etc/logrotate.d/lumiera-whatsapp
```

### Archived Logs

- **`archive/`** - Old log files from previous configurations
  - Kept for historical reference
  - Can be deleted if space is needed

## Configuration

Logging is configured in `src/utils/logger.py` using [Loguru](https://github.com/Delgan/loguru).

### Key Features

1. **Size-based rotation**: Prevents files from growing too large
2. **Automatic compression**: Old logs are zipped to save space
3. **Time-based retention**: Auto-delete old logs
4. **Async logging**: Non-blocking for better performance
5. **Enhanced error info**: Full backtrace and diagnosis on errors

## Monitoring Logs

### View live logs
```bash
# All logs
tail -f logs/app.log

# Errors only
tail -f logs/errors.log

# Both simultaneously
tail -f logs/app.log logs/errors.log
```

### Search for specific issues
```bash
# Find all errors in last 24 hours
grep "ERROR" logs/app.log | tail -100

# Search for specific user
grep "user_id: abc123" logs/app.log

# Find slow requests
grep "took.*[5-9][0-9][0-9][0-9]ms" logs/app.log
```

### Check log size
```bash
du -h logs/app.log logs/errors.log
```

## Rotation Behavior

### When rotation happens
- **Size trigger**: File reaches 50 MB (app.log) or 10 MB (errors.log)
- **Time trigger**: 30 days old (app.log) or 90 days (errors.log)

### Example rotation cycle
```
app.log                          # Current log (45 MB)
  ↓ (reaches 50 MB)
app.log                          # New empty file
app.log.2026-01-14_12-30-45.zip  # Compressed old log
  ↓ (after 30 days)
[deleted]                        # Auto-deleted
```

## Troubleshooting

### Logs not appearing
1. Check file permissions: `ls -la logs/`
2. Verify logger config: `grep -A 10 "def setup_logger" src/utils/logger.py`
3. Check disk space: `df -h`

### Logs growing too fast
1. Check rotation settings in `src/utils/logger.py`
2. Consider reducing log level: Change `INFO` to `WARNING`
3. Add filters for noisy loggers

### Need more history
Edit `src/utils/logger.py` and change:
```python
retention="30 days"  # Increase to 60, 90, etc.
```

## Best Practices

### DO
- ✅ Check `app.log` for general debugging
- ✅ Check `errors.log` for quick error scanning
- ✅ Use `tail -f` for live monitoring
- ✅ Compress and archive logs before sharing
- ✅ Include log snippets in bug reports

### DON'T
- ❌ Manually delete active log files (rotation handles it)
- ❌ Store sensitive data in logs (passwords, tokens, etc.)
- ❌ Log inside tight loops (use sampling)
- ❌ Commit log files to git (they're ignored)

## Log Levels

- **DEBUG**: Detailed information for diagnosing problems
- **INFO**: General informational messages (default)
- **WARNING**: Warning messages for potentially harmful situations
- **ERROR**: Error messages when something goes wrong
- **CRITICAL**: Critical errors that might cause system failure

## Performance Impact

- **Async logging**: Logs are queued and written in background thread
- **Compression**: Uses minimal CPU, saves ~80% disk space
- **Rotation**: No performance impact, happens in milliseconds

## Storage Requirements

### Typical usage
- ~500 MB for 30 days of INFO logs
- ~50 MB for 90 days of ERROR logs
- Compressed logs use ~20% of original size

### Disk space check
```bash
# Total log usage
du -sh logs/

# Breakdown by file
du -h logs/* | sort -h
```

## Support

For logging issues or questions:
1. Check this README
2. Review `src/utils/logger.py` configuration
3. Check application documentation
4. Contact DevOps team
