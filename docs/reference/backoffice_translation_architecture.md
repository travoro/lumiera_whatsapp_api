# 🌍 Backoffice Multi-Language Architecture Proposal

## Current State

### Database Structure
```
messages table:
├── id (uuid)
├── subcontractor_id (uuid)
├── content (text) ← Original message in original language
├── language (varchar) ← Language code (fr, ar, ro, en, etc.)
├── direction (varchar) ← inbound/outbound
├── created_at, updated_at
└── metadata (jsonb)
```

### Existing Translation Service
- `translate_to_french(text, source_lang)` ✅
- `translate_from_french(text, target_lang)` ✅
- Uses Claude Haiku (~$0.00008 per translation)
- No caching currently

---

## Problem Statement

**Backoffice Requirements:**
1. 👀 **Read:** Admin sees ALL messages in French (regardless of original language)
2. ✍️ **Write:** Admin types in French → Auto-translate to user's language before sending
3. 📊 **Preserve:** Keep original messages for audit trail
4. ⚡ **Performance:** Fast loading (thousands of messages)
5. 💰 **Cost:** Minimize translation API calls

---

## 🏗️ Proposed Architecture

### **Option 1: Real-time Translation API Layer (Simple, Immediate)**

```
┌─────────────┐                    ┌──────────────┐
│  Backoffice │◄───REST API────────│   Backend    │
│   (React)   │                    │   (FastAPI)  │
└─────────────┘                    └──────┬───────┘
                                          │
                                          ▼
                                    ┌──────────────┐
                                    │  Translation │
                                    │   Service    │
                                    └──────┬───────┘
                                          │
                                          ▼
                                    ┌──────────────┐
                                    │   Messages   │
                                    │   Database   │
                                    └──────────────┘
```

**Implementation:**
```python
# New endpoint: GET /api/backoffice/messages/{user_id}
@app.get("/api/backoffice/messages/{user_id}")
async def get_user_messages_translated(
    user_id: str,
    admin_language: str = "fr"  # Backoffice user's language
):
    # 1. Fetch messages from database
    messages = await db.get_messages(user_id)
    
    # 2. Translate on-the-fly
    translated = []
    for msg in messages:
        if msg.language != admin_language:
            translated_content = await translation_service.translate_to_french(
                msg.content, 
                source_language=msg.language
            )
        else:
            translated_content = msg.content
            
        translated.append({
            **msg,
            "content_translated": translated_content,
            "content_original": msg.content
        })
    
    return translated

# New endpoint: POST /api/backoffice/messages/send
@app.post("/api/backoffice/messages/send")
async def send_message_from_backoffice(
    user_id: str,
    message_text: str,  # In French (admin's language)
    admin_language: str = "fr"
):
    # 1. Get user's language
    user = await db.get_user(user_id)
    user_language = user.language
    
    # 2. Translate message to user's language
    if user_language != admin_language:
        translated_message = await translation_service.translate_from_french(
            message_text,
            target_language=user_language
        )
    else:
        translated_message = message_text
    
    # 3. Send via Twilio
    await twilio_client.send_message(user.phone, translated_message)
    
    # 4. Save both versions
    await db.save_message(
        user_id=user_id,
        content=translated_message,  # User's language
        language=user_language,
        direction="outbound",
        source="bo",  # Backoffice
        metadata={
            "original_bo_text": message_text,  # Admin's French text
            "translated": user_language != admin_language
        }
    )
```

**Pros:**
✅ Simple to implement (new API endpoints only)
✅ No database schema changes
✅ Always fresh translations
✅ Works immediately

**Cons:**
❌ High API cost (translate every page load)
❌ Slow performance (API latency per message)
❌ No offline support

**Best for:** MVP, low traffic backoffice

---

### **Option 2: Translation Cache Table (Recommended)**

```
┌─────────────┐                    ┌──────────────┐
│  Backoffice │◄───REST API────────│   Backend    │
│   (React)   │                    │   (FastAPI)  │
└─────────────┘                    └──────┬───────┘
                                          │
                    ┌─────────────────────┴────────────┐
                    ▼                                  ▼
            ┌──────────────┐                   ┌──────────────┐
            │ Translation  │                   │   Messages   │
            │    Cache     │                   │   Database   │
            └──────────────┘                   └──────────────┘
            
New Table:
message_translations
├── id (uuid)
├── message_id (uuid FK) ← References messages.id
├── target_language (varchar) ← "fr", "en", etc.
├── translated_content (text)
├── created_at
└── expires_at (optional TTL)
```

**Database Migration:**
```sql
CREATE TABLE message_translations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    target_language VARCHAR(10) NOT NULL,
    translated_content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP, -- Optional: auto-expire after 30 days
    
    UNIQUE(message_id, target_language)  -- One translation per language
);

CREATE INDEX idx_msg_trans_lookup ON message_translations(message_id, target_language);
```

**Implementation:**
```python
# New service: TranslationCacheService
class TranslationCacheService:
    
    async def get_or_translate(
        self, 
        message_id: str, 
        original_content: str,
        source_language: str,
        target_language: str
    ) -> str:
        """Get cached translation or translate and cache."""
        
        # Same language? Return original
        if source_language == target_language:
            return original_content
        
        # 1. Check cache
        cached = await self.db.table('message_translations').select('translated_content').eq(
            'message_id', message_id
        ).eq('target_language', target_language).single()
        
        if cached:
            return cached['translated_content']
        
        # 2. Not cached - translate
        if target_language == 'fr':
            translated = await translation_service.translate_to_french(
                original_content, source_language
            )
        else:
            translated = await translation_service.translate_from_french(
                original_content, target_language
            )
        
        # 3. Cache it
        await self.db.table('message_translations').insert({
            'message_id': message_id,
            'target_language': target_language,
            'translated_content': translated
        })
        
        return translated

# Updated endpoint
@app.get("/api/backoffice/messages/{user_id}")
async def get_user_messages_translated(user_id: str, admin_language: str = "fr"):
    messages = await db.get_messages(user_id)
    
    # Bulk translate with caching
    translated = await asyncio.gather(*[
        translation_cache_service.get_or_translate(
            message_id=msg.id,
            original_content=msg.content,
            source_language=msg.language,
            target_language=admin_language
        )
        for msg in messages
    ])
    
    return [
        {
            **msg,
            "content_translated": translated_content,
            "content_original": msg.content
        }
        for msg, translated_content in zip(messages, translated)
    ]
```

**Pros:**
✅ Fast after first load (cached)
✅ Low API cost (translate once)
✅ Scalable to many admins
✅ Supports multiple backoffice languages
✅ Can pre-cache common languages

**Cons:**
⚠️ Requires database migration
⚠️ Cache invalidation complexity
⚠️ Storage cost (but minimal)

**Best for:** Production system with multiple admins

---

### **Option 3: Dual-Column Storage (Fastest Reads)**

```
messages table (updated):
├── id (uuid)
├── subcontractor_id (uuid)
├── content (text) ← Original language
├── content_fr (text) ← French translation (auto-filled)
├── language (varchar)
├── direction
└── ...
```

**Trigger-based Translation:**
```sql
CREATE OR REPLACE FUNCTION translate_message_to_french()
RETURNS TRIGGER AS $$
BEGIN
    -- Only if not already French
    IF NEW.language != 'fr' THEN
        -- Call translation API via background worker
        -- (PostgreSQL can't call external APIs directly)
        -- Use pg_notify to trigger worker
        PERFORM pg_notify('translate_message', json_build_object(
            'message_id', NEW.id,
            'content', NEW.content,
            'language', NEW.language
        )::text);
    ELSE
        NEW.content_fr := NEW.content;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER translate_on_insert
    BEFORE INSERT ON messages
    FOR EACH ROW
    EXECUTE FUNCTION translate_message_to_french();
```

**Worker (Python):**
```python
# Background worker listening for pg_notify
async def translation_worker():
    async with db.listen('translate_message') as listener:
        async for notification in listener:
            data = json.loads(notification.payload)
            
            # Translate
            translated = await translation_service.translate_to_french(
                data['content'], data['language']
            )
            
            # Update
            await db.update_message_translation(
                data['message_id'], translated
            )
```

**Pros:**
✅ Instant reads (no API calls)
✅ Simple backoffice queries
✅ No caching complexity

**Cons:**
❌ Higher storage (2x content)
❌ Complex write path (triggers + workers)
❌ Only supports one target language (French)
❌ Hard to add more languages later

**Best for:** Single-language backoffice only

---

### **Option 4: Hybrid (Smart Balance)** ⭐ **RECOMMENDED**

Combine Options 1 + 2:
- **Cache frequently accessed** (recent messages, escalations)
- **Real-time for rest** (old messages, edge cases)

```python
class SmartTranslationService:
    
    async def get_messages_translated(
        self, 
        user_id: str, 
        admin_language: str = "fr",
        limit: int = 50
    ):
        messages = await db.get_messages(user_id, limit=limit)
        
        # Strategy: Cache recent 50 messages, real-time for rest
        results = []
        
        for msg in messages:
            # Recent messages (cached)
            if self._is_recent(msg, days=7):
                translated = await translation_cache_service.get_or_translate(
                    msg.id, msg.content, msg.language, admin_language
                )
            # Old messages (real-time, don't cache)
            else:
                if msg.language != admin_language:
                    translated = await translation_service.translate_to_french(
                        msg.content, msg.language
                    )
                else:
                    translated = msg.content
            
            results.append({**msg, "content_translated": translated})
        
        return results
```

**Pros:**
✅ Best performance for common cases
✅ Low storage (only recent cached)
✅ Cost-effective
✅ Flexible strategy

**Cons:**
⚠️ Complex logic
⚠️ Requires monitoring

---

## 📊 Cost Comparison

**Scenario:** 1000 messages, 10 admin views per day

| Option | Initial Cost | Daily Cost | Monthly Cost |
|--------|-------------|------------|--------------|
| **Option 1** (Real-time) | $0 | $0.80 | $24 |
| **Option 2** (Cache) | $0.08 | $0.008 | $0.32 |
| **Option 3** (Dual-column) | $0.08 | $0.001 | $0.11 |
| **Option 4** (Hybrid) | $0.04 | $0.02 | $0.64 |

---

## 🎯 Recommendation

**For Production: Option 2 (Translation Cache Table)**

**Why:**
1. ✅ Best balance of performance, cost, and simplicity
2. ✅ Scales to multiple backoffice languages
3. ✅ Simple to maintain
4. ✅ Pre-cache strategy available
5. ✅ Works with existing architecture

**Implementation Phases:**
1. **Phase 1:** Add translation_cache table + migration
2. **Phase 2:** Create TranslationCacheService
3. **Phase 3:** Add backoffice API endpoints
4. **Phase 4:** Optional: Pre-cache escalations

---

## 🚀 Quick Start (Option 2)

**1. Database Migration:**
```sql
CREATE TABLE message_translations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    target_language VARCHAR(10) NOT NULL,
    translated_content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(message_id, target_language)
);
```

**2. API Endpoints:**
- `GET /api/backoffice/conversations/{user_id}` - Get translated messages
- `POST /api/backoffice/messages/send` - Send translated message

**3. Frontend:**
- Display `content_translated` to admin
- Show `content_original` on hover/tooltip
- Send admin's French text → API translates → WhatsApp

Done! 🎉
