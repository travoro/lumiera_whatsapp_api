# PlanRadar API Rate Limit Monitoring

**Date**: 2026-01-16
**Rate Limit**: 30 requests per minute

---

## 🎯 What Changed

All PlanRadar API calls are now logged with a special marker `🔵 PLANRADAR_API_CALL` for easy tracking and analysis.

### New Log Format

Each API call logs:
- **Request ID**: Sequential counter (#1, #2, #3...)
- **Timestamp**: Exact time of the call
- **Method & Endpoint**: What was called
- **Duration**: How long it took (in milliseconds)
- **Status**: COMPLETE, RATE_LIMIT, or ERROR

---

## 📊 Example Logs

```
🔵 PLANRADAR_API_CALL #1 | START | GET 1484013/projects/abc123/tickets
   ⏰ Timestamp: 2026-01-16T07:57:12.123456
   🌐 URL: https://www.planradar.com/api/v2/1484013/projects/abc123/tickets
🔵 PLANRADAR_API_CALL #1 | COMPLETE | Status: 200 | Duration: 234ms
   📊 Response data: 15 item(s)

🔵 PLANRADAR_API_CALL #2 | START | POST 1484013/projects/abc123/tickets/xyz/comment
   ⏰ Timestamp: 2026-01-16T07:57:13.456789
🔵 PLANRADAR_API_CALL #2 | COMPLETE | Status: 201 | Duration: 187ms

🔵 PLANRADAR_API_CALL #30 | RATE_LIMIT | 429 Too Many Requests | Duration: 156ms
   ⚠️ PlanRadar API rate limit exceeded (30 requests/minute)
```

---

## 🔍 Monitoring Commands

### 1. Watch Live API Calls
```bash
tail -f logs/app.log | grep PLANRADAR_API_CALL
```

### 2. Count Calls in Last Minute
```bash
# Get calls from last minute
grep "PLANRADAR_API_CALL.*START" logs/app.log | \
  tail -100 | \
  grep "$(date -u +%Y-%m-%d\ %H:%M)" | \
  wc -l
```

### 3. Run Full Analysis
```bash
./scripts/analyze_planradar_rate_limit.sh
```

This shows:
- Total API calls
- Rate limit errors
- Calls per minute (last hour)
- Average response time
- Most called endpoints

### 4. Check for Rate Limit Errors
```bash
grep "RATE_LIMIT" logs/app.log
```

### 5. Find Slow Calls (> 1 second)
```bash
grep "PLANRADAR_API_CALL.*COMPLETE" logs/app.log | \
  grep -E "Duration: [0-9]{4,}ms"
```

---

## 📈 Understanding the Output

### Analysis Script Output

```
================================================
🔵 PlanRadar API Rate Limit Analysis
================================================

📄 Analyzing: logs/app.log

📊 Total API calls: 145

✅ No rate limit errors

📝 Last 10 API calls:
[Recent calls listed here]

📈 API calls per minute (last hour):
2026-01-16 07:55: 12 requests
2026-01-16 07:56: 28 requests ⚡ CLOSE TO LIMIT
2026-01-16 07:57: 31 requests ⚠️  AT LIMIT!

⏱️  Average API response time:
   Average: 234ms (last 50 calls)

🎯 Most called endpoints (top 10):
  45 GET 1484013/projects/abc/tickets
  23 GET 1484013/projects/abc/components/xyz/plans
  ...
```

### What to Look For

1. **⚠️  AT LIMIT!** - You hit exactly 30 requests in one minute
2. **⚡ CLOSE TO LIMIT** - 25-29 requests in one minute (warning zone)
3. **Slow responses** - Average > 1000ms might indicate server load
4. **Repeated endpoints** - Same endpoint called many times = caching opportunity

---

## 🚨 If You Hit Rate Limits

### Immediate Actions

1. **Check the analysis**:
   ```bash
   ./scripts/analyze_planradar_rate_limit.sh
   ```

2. **Identify the pattern** - Which endpoints are called most?

3. **Wait 60 seconds** - Rate limit resets every minute

### Long-term Solutions

1. **Add Caching**
   - Cache `list_tasks` results for 30 seconds
   - Cache `get_task` results for 1 minute
   - Cache project components for 5 minutes

2. **Batch Requests**
   - Fetch all tasks once instead of individual task lookups
   - Use project-level endpoints when possible

3. **Reduce Redundant Calls**
   - Check if you're calling same endpoint multiple times
   - Store results in memory during a conversation

4. **Optimize Workflows**
   - Combine multiple operations
   - Delay non-critical fetches

---

## 💡 Tips

### Good Practices

- **Cache frequently accessed data** (task lists, projects)
- **Use batch endpoints** when available
- **Avoid polling** - don't repeatedly call same endpoint
- **Spread requests** - don't burst all calls at once

### Warning Signs

- Seeing RATE_LIMIT logs frequently
- Same endpoint called 10+ times per minute
- Average response time increasing
- Users seeing "API temporarily overloaded" messages

---

## 🔧 Example: Adding Caching

```python
from datetime import datetime, timedelta
import asyncio

class CachedPlanRadarClient(PlanRadarClient):
    def __init__(self):
        super().__init__()
        self._cache = {}
        self._cache_ttl = {}

    async def list_tasks(self, project_id: str, status: Optional[str] = None):
        cache_key = f"tasks:{project_id}:{status}"
        now = datetime.now()

        # Check cache
        if cache_key in self._cache:
            if self._cache_ttl[cache_key] > now:
                log.info(f"📦 Cache hit: {cache_key}")
                return self._cache[cache_key]

        # Fetch from API
        tasks = await super().list_tasks(project_id, status)

        # Store in cache for 30 seconds
        self._cache[cache_key] = tasks
        self._cache_ttl[cache_key] = now + timedelta(seconds=30)

        return tasks
```

---

## 📞 Quick Commands Summary

```bash
# Watch live
tail -f logs/app.log | grep PLANRADAR_API_CALL

# Full analysis
./scripts/analyze_planradar_rate_limit.sh

# Count recent calls
grep "PLANRADAR_API_CALL.*START" logs/app.log | tail -50 | wc -l

# Check for rate limits
grep "RATE_LIMIT" logs/app.log

# Most called endpoints
grep "PLANRADAR_API_CALL.*START" logs/app.log | \
  awk -F'| START | ' '{print $2}' | sort | uniq -c | sort -rn | head -10
```

---

## 🎯 Integration with FSM

The PlanRadar tracking works alongside the FSM integration:

- FSM prevents duplicate message processing
- PlanRadar tracking monitors API usage
- Together they ensure optimal performance

Both use structured logging for easy filtering:
- `grep "FSM"` for state machine logs
- `grep "PLANRADAR_API_CALL"` for API logs

---

**Status**: ✅ Active
**Location**: `src/integrations/planradar.py`
**Analysis Tool**: `scripts/analyze_planradar_rate_limit.sh`
