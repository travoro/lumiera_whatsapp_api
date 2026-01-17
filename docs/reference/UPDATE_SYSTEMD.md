# Update Systemd Service - Simplified Logging

## What Changed

We simplified logging to use only **loguru** (app.log + errors.log) and removed duplicate systemd file logs (server.log + server.error.log).

**Before:**
- ❌ app.log (loguru) + server.log (systemd) = DUPLICATE
- ❌ errors.log (loguru) + server.error.log (systemd) = DUPLICATE
- ❌ 26 MB of duplicate data
- ❌ No rotation on server.log files

**After:**
- ✅ app.log only (with automatic rotation)
- ✅ errors.log only (for quick debugging)
- ✅ Single source of truth
- ✅ Automatic cleanup

---

## How to Update

### Step 1: Copy Updated Service File

```bash
cd /home/ceeai/whatsapp_api
sudo cp lumiera-whatsapp.service /etc/systemd/system/
```

### Step 2: Reload Systemd

```bash
sudo systemctl daemon-reload
```

### Step 3: Restart Service

```bash
sudo systemctl restart lumiera-whatsapp
```

### Step 4: Verify

```bash
# Check service is running
sudo systemctl status lumiera-whatsapp

# Check logs are working
tail -f logs/app.log
```

---

## Where to Check Logs Now

### Primary Log (Check this first)
```bash
tail -f logs/app.log
```

### Errors Only
```bash
tail -f logs/errors.log
```

### Systemd Journal (Optional)
```bash
journalctl -u lumiera-whatsapp -f
```

**Recommendation:** Just use `logs/app.log` - it has everything with better formatting!

---

## Cleanup (Optional)

The old `server.log` and `server.error.log` files have been archived. You can delete the archives if needed:

```bash
rm logs/archive/server.log.*.gz logs/archive/server.error.log.*.gz
```

---

## Benefits

✅ No more duplicate logs
✅ Saves disk space (was wasting 26+ MB)
✅ Clear single source of truth
✅ Automatic rotation and cleanup
✅ Better log management

---

## Troubleshooting

**Service won't start?**
```bash
sudo journalctl -u lumiera-whatsapp -n 50
```

**Logs not appearing in app.log?**
- Check file permissions: `ls -la logs/`
- Check logger config: `grep -A 20 "def setup_logger" src/utils/logger.py`

**Need to see systemd output?**
```bash
journalctl -u lumiera-whatsapp --since "5 minutes ago"
```
