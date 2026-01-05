# Hybrid Intent System - Performance Optimization

## Overview

The hybrid intent system uses confidence-based routing to optimize response speed and reduce API costs while maintaining quality.

## Architecture

```
User Message
     ↓
[Intent Classification (Haiku)]
     ↓
Confidence >= 95%?
     ↓
    YES ─────→ [FAST PATH]
     │         Direct Handler
     │         (No Opus call)
     │              ↓
     │         Quick Response
     │
    NO  ─────→ [COMPLEX PATH]
              Full Agent (Opus)
              + Tools + Context
                   ↓
              Comprehensive Response
```

## Confidence Levels

### High Confidence (95-100%) → FAST PATH ✅
- **Exact keyword matches**: "bonjour", "hello", "hi"
- **Short clear messages**: 1-3 words matching keywords
- **Haiku returns high confidence**: Intent:95+
- **Direct execution**: No Opus call needed
- **Response time**: ~500ms (vs ~3-5s for Opus)
- **Cost**: ~$0.0001 per request (vs ~$0.015 for Opus)

### Medium Confidence (75-94%) → COMPLEX PATH ⚙️
- **Partial matches**: Keyword present but message is longer
- **Ambiguous intent**: Could mean multiple things
- **Context-dependent**: Needs conversation history
- **Full agent**: Uses Opus with tools and context

### Low Confidence (<75%) → COMPLEX PATH ⚙️
- **Complex questions**: Multi-part requests
- **Unknown patterns**: No keyword match
- **General conversation**: Open-ended queries
- **Full agent**: Required for quality

## Intents with Fast Path

### 1. Greeting ✅
**Triggers:** "bonjour", "hello", "hi", "salut", "hola", "hey", "bom dia"

**Fast Path Response:**
- Personalized greeting with user name
- Interactive menu with 5 options
- Multi-language support

**Confidence:** 98% (exact match)

**Example:**
```
Input: "bonjour"
Confidence: 98%
Path: FAST ✅
Response Time: 500ms
Cost: $0.0001

Output:
Bonjour, Albin! 👋

Comment puis-je vous aider aujourd'hui?

1. 🏗️ Voir mes chantiers actifs
2. 📋 Consulter mes tâches
...
```

### 2. List Projects ✅
**Triggers:** "projects", "chantiers", "list", "voir"

**Fast Path Response:**
- Direct database query
- Formatted list of active projects
- Location and status info

**Confidence:** 90-98% (depending on clarity)

**Example:**
```
Input: "mes chantiers"
Confidence: 98%
Path: FAST ✅
Response Time: 600ms
Cost: $0.0001

Output:
Vous avez 3 chantier(s) actif(s):

1. 🏗️ Rénovation Bureau
   📍 Paris 15ème
   Statut: En cours
...
```

### 3. Escalation ✅
**Triggers:** "human", "admin", "help", "parler", "équipe"

**Fast Path Response:**
- Direct escalation creation
- Admin notification
- Confirmation message

**Confidence:** 95-98%

**Example:**
```
Input: "parler avec l'équipe"
Confidence: 97%
Path: FAST ✅
Response Time: 700ms
Cost: $0.0001

Output:
✅ Votre demande a été transmise à l'équipe administrative.
Un membre de l'équipe vous contactera sous peu.
```

## Intents WITHOUT Fast Path (Complex Path Only)

### list_tasks
- Requires project_id parameter
- Needs conversation context
- Full agent handles parameter extraction

### report_incident
- Requires multiple inputs (photo, description)
- Multi-turn conversation
- Full agent manages flow

### update_progress
- Complex task identification
- State management needed
- Full agent required

### general
- Open-ended questions
- Conversational AI needed
- Always uses full agent

## Performance Metrics

### Expected Fast Path Usage
- **Greetings**: 80-90% of greeting messages
- **List Projects**: 70-80% of simple requests
- **Escalation**: 85-95% of clear requests

### Overall Impact
Assuming distribution:
- 30% greetings
- 20% list projects
- 10% escalations
- 40% complex queries

**Fast path coverage:** ~45-50% of all messages

### Cost Savings
- **Opus call**: ~$0.015 per request
- **Haiku classification**: ~$0.0001 per request
- **Savings per fast path request**: ~$0.0148

**Monthly savings** (1000 messages/month):
- Without fast path: 1000 * $0.015 = $15
- With fast path: (500 * $0.015) + (1000 * $0.0001) = $7.6
- **Savings: ~50% ($7.4/month)**

### Speed Improvement
- **Opus response**: 3-5 seconds
- **Fast path response**: 0.5-1 second
- **Improvement: 3-5x faster**

## Implementation Details

### Confidence Scoring

```python
# Exact keyword match
"bonjour" → confidence = 0.98

# Partial match (short message)
"hello team" → confidence = 0.90

# Haiku classification
"can you help me?" → Haiku analyzes → confidence = 0.75-0.85

# Ambiguous/complex
"I need to check the status of my project and update the progress"
→ confidence = 0.60-0.70 → Full agent
```

### Fallback Mechanism

If fast path fails (handler returns None):
1. Log warning
2. Automatically fall back to full agent
3. No impact on user experience
4. Error tracked for monitoring

### Feature Flag

```python
USE_FAST_PATH = True  # In message.py line 335

# Can be disabled for:
# - Testing
# - Debugging
# - Gradual rollout
```

### Confidence Threshold

```python
CONFIDENCE_THRESHOLD = 0.95  # In message.py line 334

# Can be adjusted:
# - 0.90: More aggressive (more fast path)
# - 0.95: Balanced (recommended)
# - 0.98: Conservative (fewer fast path)
```

## Monitoring & Analytics

### Logs to Monitor

```
🎯 Exact keyword match: 'bonjour' → greeting (confidence: 0.98)
🚀 HIGH CONFIDENCE (98%) - Attempting fast path for: greeting
✅ FAST PATH SUCCESS: greeting executed directly (saved Opus call)
```

```
⚙️ LOW CONFIDENCE (72%) - Using full agent (Opus)
```

```
⚠️ FAST PATH FAILED: Falling back to full agent for list_projects
```

### Database Analytics

Query `intent_classifications` table:
```sql
-- Fast path success rate
SELECT
    classified_intent,
    COUNT(*) as total,
    AVG(confidence) as avg_confidence,
    COUNT(CASE WHEN confidence >= 0.95 THEN 1 END) as fast_path_eligible
FROM intent_classifications
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY classified_intent
ORDER BY total DESC;
```

### Performance Metrics

- **Fast path usage rate**: % of requests using fast path
- **Fallback rate**: % of fast path attempts that fall back
- **Average response time**: By path type
- **Cost per request**: By path type
- **User satisfaction**: Same for both paths

## Extending Fast Path

### Adding New Intent Handler

1. **Define handler** in `src/services/direct_handlers.py`:
```python
async def handle_new_intent(user_id, user_name, language, **kwargs):
    # Direct execution logic
    return {
        "message": "...",
        "escalation": False,
        "tools_called": ["..."],
        "fast_path": True
    }
```

2. **Add to handler mapping**:
```python
INTENT_HANDLERS = {
    ...
    "new_intent": handle_new_intent,
}
```

3. **Update intent classifier** keywords in `src/services/intent.py`

4. **Test confidence scoring**

### Guidelines for Fast Path

✅ **Good candidates:**
- Single-turn interactions
- Simple database queries
- Deterministic responses
- No complex context needed

❌ **Bad candidates:**
- Multi-turn conversations
- Complex parameter extraction
- State management required
- Needs tool calling flexibility

## Testing

### Manual Testing

```bash
# Test greeting
curl -X POST http://localhost:8000/webhook/whatsapp \
  -d "Body=bonjour"

# Check logs for:
# "🚀 HIGH CONFIDENCE" ← Should use fast path
# "✅ FAST PATH SUCCESS" ← Should succeed
```

### Confidence Threshold Testing

Temporarily adjust `CONFIDENCE_THRESHOLD` to test behavior:
- 0.80: Very aggressive fast path
- 0.95: Production setting
- 0.99: Very conservative

## Rollout Strategy

### Phase 1: Monitor Only ✅
- Log fast path decisions
- Don't actually use fast path
- Collect confidence data

### Phase 2: Gradual Rollout (Current)
- Enable fast path for 95%+ confidence
- Monitor fallback rate
- Track user satisfaction

### Phase 3: Optimization
- Adjust confidence threshold based on data
- Add more intent handlers
- Fine-tune confidence scoring

## Troubleshooting

### High Fallback Rate
**Problem:** Fast path attempts frequently failing

**Solutions:**
- Check handler error logs
- Verify database connectivity
- Review handler logic
- Lower confidence threshold

### Low Fast Path Usage
**Problem:** Not many requests using fast path

**Solutions:**
- Review confidence scoring
- Add more keywords
- Lower confidence threshold
- Improve Haiku prompt

### Quality Issues
**Problem:** Fast path responses not good enough

**Solutions:**
- Raise confidence threshold
- Improve handler responses
- Add more context to handlers
- Fall back to full agent for specific cases

## Future Improvements

1. **Adaptive thresholds**: Adjust confidence based on success rate
2. **More handlers**: Add fast path for more intents
3. **Context-aware fast path**: Use recent conversation for better decisions
4. **A/B testing**: Compare fast path vs full agent satisfaction
5. **Caching**: Cache common responses for even faster delivery
