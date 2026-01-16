#!/bin/bash
# PlanRadar API Rate Limit Analysis Script
# Helps monitor if you're hitting the 30 requests/minute limit

LOG_FILE="${1:-logs/app.log}"

echo "=================================================="
echo "🔵 PlanRadar API Rate Limit Analysis"
echo "=================================================="
echo ""

# Check if log file exists
if [ ! -f "$LOG_FILE" ]; then
    echo "❌ Log file not found: $LOG_FILE"
    exit 1
fi

echo "📄 Analyzing: $LOG_FILE"
echo ""

# Total API calls
total_calls=$(grep -c "PLANRADAR_API_CALL.*START" "$LOG_FILE")
echo "📊 Total API calls: $total_calls"
echo ""

# Rate limit errors
rate_limit_errors=$(grep -c "PLANRADAR_API_CALL.*RATE_LIMIT" "$LOG_FILE")
if [ "$rate_limit_errors" -gt 0 ]; then
    echo "⚠️  Rate limit errors detected: $rate_limit_errors"
    echo ""
    echo "Recent rate limit errors:"
    grep "PLANRADAR_API_CALL.*RATE_LIMIT" "$LOG_FILE" | tail -5
    echo ""
else
    echo "✅ No rate limit errors"
    echo ""
fi

# Recent API calls (last 10)
echo "📝 Last 10 API calls:"
grep "PLANRADAR_API_CALL.*COMPLETE\|PLANRADAR_API_CALL.*ERROR\|PLANRADAR_API_CALL.*RATE_LIMIT" "$LOG_FILE" | tail -10
echo ""

# Calls per minute analysis (last hour)
echo "📈 API calls per minute (last hour):"
grep "PLANRADAR_API_CALL.*START" "$LOG_FILE" | tail -100 | awk '{
    # Extract timestamp (format: 2026-01-16 07:57:12)
    timestamp = $1 " " $2
    # Extract minute (format: 2026-01-16 07:57)
    minute = substr($1 " " $2, 1, 16)
    minutes[minute]++
}
END {
    for (minute in minutes) {
        count = minutes[minute]
        warning = ""
        if (count >= 30) {
            warning = " ⚠️  AT LIMIT!"
        } else if (count >= 25) {
            warning = " ⚡ CLOSE TO LIMIT"
        }
        print minute ": " count " requests" warning
    }
}' | sort | tail -20
echo ""

# Average response time
echo "⏱️  Average API response time:"
grep "PLANRADAR_API_CALL.*COMPLETE" "$LOG_FILE" | tail -50 | awk -F'Duration: |ms' '{
    if (NF >= 2) {
        duration = $(NF-1)
        sum += duration
        count++
    }
}
END {
    if (count > 0) {
        avg = sum / count
        print "   Average: " avg "ms (last 50 calls)"
        if (avg > 1000) {
            print "   ⚠️  Slow responses detected"
        }
    } else {
        print "   No data"
    }
}'
echo ""

# Most called endpoints
echo "🎯 Most called endpoints (top 10):"
grep "PLANRADAR_API_CALL.*START" "$LOG_FILE" | awk -F'\\| START \\| ' '{print $2}' | sort | uniq -c | sort -rn | head -10
echo ""

echo "=================================================="
echo "💡 Tips:"
echo "   - PlanRadar limit: 30 requests/minute"
echo "   - If you see consistent limits, add caching"
echo "   - Use batch endpoints when available"
echo ""
echo "🔍 To see live PlanRadar calls:"
echo "   tail -f $LOG_FILE | grep PLANRADAR_API_CALL"
echo "=================================================="
