# External App Specifications - Human Agent Dashboard

## Overview

This document specifies the requirements for building an external web application that allows human agents to take over WhatsApp conversations from the bot.

## System Architecture

```
┌──────────────────────────────────────────────────────────┐
│ External App (Human Agent Dashboard)                     │
│ - View conversation history                              │
│ - Send messages as agent                                 │
│ - Take over / Release conversations                      │
└──────────────────────────────────────────────────────────┘
                    ↓ ↑
        Direct database access + Twilio API
                    ↓ ↑
┌──────────────────────────────────────────────────────────┐
│ PostgreSQL Database (Supabase)                           │
│ - subcontractors table (handoff flags)                   │
│ - messages table (conversation history)                  │
└──────────────────────────────────────────────────────────┘
                    ↓ ↑
┌──────────────────────────────────────────────────────────┐
│ WhatsApp API (Existing)                                  │
│ - Checks handoff status on every message                 │
│ - If active: Saves message only, no bot response         │
│ - If expired: Resumes normal bot operation               │
└──────────────────────────────────────────────────────────┘
```

## Database Schema

### Required Tables (Already exist in Supabase)

#### 1. `subcontractors` table

**New columns added by migration 015:**
```sql
human_agent_active BOOLEAN DEFAULT false
human_agent_since TIMESTAMP WITH TIME ZONE
human_agent_expires_at TIMESTAMP WITH TIME ZONE
```

**Existing columns you'll need:**
```sql
id UUID PRIMARY KEY
whatsapp_number TEXT  -- Format: +33123456789
contact_name TEXT
contact_prenom TEXT
language TEXT  -- 'fr', 'en', 'es', etc.
```

#### 2. `messages` table

**Columns:**
```sql
id UUID PRIMARY KEY
subcontractor_id UUID REFERENCES subcontractors(id)
direction TEXT  -- 'inbound' or 'outbound'
content TEXT
media_url TEXT
metadata JSONB  -- Store sent_by_human, agent_name, etc.
session_id UUID
created_at TIMESTAMP WITH TIME ZONE
```

## Core Functionality

### 1. View Active Conversations

**Query to get users with recent messages:**
```sql
SELECT DISTINCT ON (s.id)
    s.id,
    s.whatsapp_number,
    s.contact_name,
    s.contact_prenom,
    s.language,
    s.human_agent_active,
    s.human_agent_since,
    s.human_agent_expires_at,
    m.created_at as last_message_at,
    m.content as last_message,
    m.direction as last_message_direction
FROM subcontractors s
LEFT JOIN messages m ON m.subcontractor_id = s.id
WHERE m.created_at > NOW() - INTERVAL '24 hours'
ORDER BY s.id, m.created_at DESC;
```

**UI Display:**
- List of conversations sorted by most recent activity
- Show user name, last message preview
- Badge/indicator if human agent is currently active
- Timestamp of last message
- Unread count (messages since agent last responded)

### 2. View Conversation History

**Query for specific conversation:**
```sql
SELECT
    id,
    direction,
    content,
    media_url,
    metadata,
    created_at
FROM messages
WHERE subcontractor_id = $user_id
ORDER BY created_at DESC
LIMIT 50;
```

**UI Display:**
- Chat interface with messages in chronological order
- Inbound messages on left, outbound on right
- Show timestamp for each message
- Display images/media if media_url present
- Badge on messages sent by human (check metadata.sent_by_human)
- Badge on messages sent by bot

### 3. Take Over Conversation

**SQL to activate handoff:**
```sql
UPDATE subcontractors
SET
    human_agent_active = true,
    human_agent_since = NOW(),
    human_agent_expires_at = NOW() + INTERVAL '7 hours'
WHERE id = $user_id;
```

**What happens:**
1. Agent clicks "Take Over" button on a conversation
2. Execute above SQL to set handoff flags
3. UI shows "You are now handling this conversation"
4. Timer shows when handoff expires (7 hours from now)
5. All future user messages will be saved without bot responses

**UI Considerations:**
- Disable "Take Over" button when already active
- Show expiry countdown timer
- Auto-refresh to show new user messages in real-time

### 4. Send Message as Agent

**Steps:**
1. Insert message into database
2. Update handoff timestamp (extends expiration)
3. Send message via Twilio API

**SQL to insert message:**
```sql
INSERT INTO messages (
    subcontractor_id,
    direction,
    content,
    metadata,
    created_at
) VALUES (
    $user_id,
    'outbound',
    $message_text,
    jsonb_build_object(
        'sent_by_human', true,
        'agent_name', $agent_name
    ),
    NOW()
);
```

**SQL to update handoff timestamp:**
```sql
UPDATE subcontractors
SET
    human_agent_active = true,
    human_agent_since = NOW(),
    human_agent_expires_at = NOW() + INTERVAL '7 hours'
WHERE id = $user_id;
```

**Twilio API call:**
```javascript
// Using Twilio Node.js SDK
const client = require('twilio')(accountSid, authToken);

await client.messages.create({
    from: 'whatsapp:+14155238886',  // Your Twilio WhatsApp number
    to: `whatsapp:${userPhoneNumber}`,  // User's WhatsApp (from subcontractors.whatsapp_number)
    body: messageText
});
```

**Environment variables needed:**
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_WHATSAPP_NUMBER` (e.g., whatsapp:+14155238886)

### 5. Release Conversation

**SQL to deactivate handoff:**
```sql
UPDATE subcontractors
SET
    human_agent_active = false,
    human_agent_since = NULL,
    human_agent_expires_at = NULL
WHERE id = $user_id;
```

**What happens:**
1. Agent clicks "Release" or "Mark as Resolved" button
2. Execute above SQL to clear handoff flags
3. UI shows "Bot has resumed handling this conversation"
4. Next user message will trigger normal bot processing

### 6. Auto-Expiration Handling

**No action required in external app!**

The WhatsApp API automatically checks expiration on every user message:
- If `NOW() >= human_agent_expires_at`, flags are auto-cleared
- Bot resumes normal operation

**UI Considerations:**
- Show countdown timer: "Expires in 6h 23m"
- Visual warning when < 1 hour remaining
- Show "Expired" badge if past expiration time
- Optional: Button to "Extend for 7 more hours" (re-execute take over SQL)

## API Integration

### Twilio Configuration

**Required credentials (get from Twilio Console):**
1. Account SID (starts with AC...)
2. Auth Token (secret key)
3. WhatsApp-enabled phone number (e.g., +14155238886)

**Message format:**
```javascript
{
    from: 'whatsapp:+14155238886',  // Your Twilio number
    to: 'whatsapp:+33123456789',    // User's number
    body: 'Hello, this is Sophie from support...'
}
```

### Database Connection

**Connection details:**
- Use Supabase connection string from environment
- Format: `postgresql://user:pass@host:port/database`
- Enable SSL mode for production

**Connection pooling recommended:**
- Use pg-pool or Prisma for connection management
- Maximum 10 connections per instance

## User Interface Requirements

### Dashboard Layout

```
┌─────────────────────────────────────────────────────────────┐
│ Header: Lumiera Agent Dashboard                            │
│ [Agent Name] [Status: Online]                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────┬──────────────────────────────────────────┐
│ Conversations   │ Chat Window                               │
│                 │                                           │
│ 🟢 Jean Dupont  │ Jean Dupont                              │
│    Il y a un... │ ┌──────────────────────────────────────┐ │
│    2 min ago    │ │ 🤖 Bonjour! Comment puis-je vous... │ │
│                 │ │ 10:32 AM                             │ │
│ 🔴 Marie Martin │ ├──────────────────────────────────────┤ │
│    Je souhaite..│ │         Il y a un problème urgent 👤 │ │
│    5 min ago    │ │                             10:35 AM │ │
│    [ACTIVE]     │ └──────────────────────────────────────┘ │
│                 │                                           │
│ Sophie Bernard  │ [Type message...]                         │
│    Merci...     │ [Send] [Release]                          │
│    1 hour ago   │                                           │
│                 │ ⏱️ Active handoff: Expires in 6h 45m     │
└─────────────────┴──────────────────────────────────────────┘

Legend:
🟢 = New unread messages
🔴 = Human agent active
👤 = User message
🤖 = Bot message
```

### Conversation List (Left Panel)

**Features:**
- Real-time updates (poll every 5 seconds or use websockets)
- Search/filter by name or phone number
- Sort by: Most recent, Active handoffs, Unread only
- Show badge for active handoffs
- Click to open conversation in right panel

**Each conversation item shows:**
- User name (contact_prenom + contact_name)
- Last message preview (truncated to 50 chars)
- Timestamp (relative: "2 min ago", "1 hour ago")
- Badge if human agent active
- Unread count badge

### Chat Window (Right Panel)

**Features:**
- Scrollable message history (load more on scroll up)
- Autoscroll to bottom on new message
- Message input textarea with send button
- "Take Over" button (disabled when already active)
- "Release" button (enabled only when active)
- Expiry countdown timer when active

**Message display:**
- User messages aligned right, blue background
- Bot messages aligned left, gray background
- Human agent messages aligned left, green background with badge
- Show timestamp under each message
- Show "Seen" indicator if available

**Actions bar:**
```
┌─────────────────────────────────────────────────┐
│ [Take Over] [Release] [Refresh]                 │
│ Status: ⏱️ Active - Expires in 6h 23m          │
└─────────────────────────────────────────────────┘
```

## Technical Stack Recommendations

### Frontend
- **React** with TypeScript
- **TailwindCSS** for styling
- **React Query** for data fetching and caching
- **Socket.io** or polling for real-time updates
- **date-fns** for timestamp formatting

### Backend/Database
- **Supabase JS Client** for database queries
- **Twilio Node.js SDK** for sending messages
- **Next.js API Routes** (optional) if you want a backend layer

### State Management
- React Query for server state
- React Context or Zustand for UI state
- Local storage for agent name/preferences

## Implementation Steps

### Phase 1: Basic UI (1-2 days)
1. Setup project with React + Tailwind
2. Create conversation list component
3. Create chat window component
4. Mock data for development

### Phase 2: Database Integration (1 day)
1. Connect to Supabase
2. Query conversations and messages
3. Display real data in UI
4. Implement refresh/polling

### Phase 3: Twilio Integration (1 day)
1. Setup Twilio credentials
2. Implement send message function
3. Insert messages to database
4. Test end-to-end message flow

### Phase 4: Handoff Logic (1 day)
1. Implement "Take Over" button
2. Implement "Release" button
3. Update handoff flags in database
4. Show expiry countdown

### Phase 5: Polish (1 day)
1. Real-time updates
2. Error handling
3. Loading states
4. Responsive design

## Environment Variables

```env
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJxxx...
SUPABASE_SERVICE_ROLE_KEY=eyJxxx...  # For server-side operations

# Twilio
TWILIO_ACCOUNT_SID=ACxxxxx
TWILIO_AUTH_TOKEN=xxxxx
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# App Config
AGENT_NAME=Sophie  # Default agent name
POLLING_INTERVAL_MS=5000  # 5 seconds
```

## Example Code Snippets

### Connect to Supabase
```typescript
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
)
```

### Fetch Conversations
```typescript
async function getConversations() {
  const { data, error } = await supabase
    .from('subcontractors')
    .select(`
      id,
      whatsapp_number,
      contact_name,
      contact_prenom,
      human_agent_active,
      human_agent_expires_at,
      messages (
        created_at,
        content,
        direction
      )
    `)
    .order('messages.created_at', { ascending: false })
    .limit(1, { foreignTable: 'messages' })

  return data
}
```

### Take Over Conversation
```typescript
async function takeOverConversation(userId: string) {
  const expiresAt = new Date()
  expiresAt.setHours(expiresAt.getHours() + 7)

  const { error } = await supabase
    .from('subcontractors')
    .update({
      human_agent_active: true,
      human_agent_since: new Date().toISOString(),
      human_agent_expires_at: expiresAt.toISOString()
    })
    .eq('id', userId)

  if (error) throw error
}
```

### Send Message via Twilio
```typescript
import twilio from 'twilio'

const client = twilio(
  process.env.TWILIO_ACCOUNT_SID,
  process.env.TWILIO_AUTH_TOKEN
)

async function sendMessage(userPhone: string, messageText: string, agentName: string) {
  // 1. Send via Twilio
  await client.messages.create({
    from: process.env.TWILIO_WHATSAPP_NUMBER,
    to: `whatsapp:${userPhone}`,
    body: messageText
  })

  // 2. Save to database
  await supabase.from('messages').insert({
    subcontractor_id: userId,
    direction: 'outbound',
    content: messageText,
    metadata: { sent_by_human: true, agent_name: agentName }
  })

  // 3. Update handoff timestamp
  await supabase.from('subcontractors')
    .update({
      human_agent_active: true,
      human_agent_since: new Date().toISOString(),
      human_agent_expires_at: new Date(Date.now() + 7 * 60 * 60 * 1000).toISOString()
    })
    .eq('id', userId)
}
```

### Release Conversation
```typescript
async function releaseConversation(userId: string) {
  const { error } = await supabase
    .from('subcontractors')
    .update({
      human_agent_active: false,
      human_agent_since: null,
      human_agent_expires_at: null
    })
    .eq('id', userId)

  if (error) throw error
}
```

## Security Considerations

1. **Use Supabase RLS (Row Level Security)**
   - Ensure agents can only see conversations
   - Prevent unauthorized database modifications

2. **Protect Twilio Credentials**
   - Never expose in frontend code
   - Use server-side API routes for Twilio calls

3. **Agent Authentication**
   - Implement login system for agents
   - Track which agent handled which conversation

4. **Rate Limiting**
   - Limit message sending (e.g., 10 per minute)
   - Prevent abuse or accidental spam

## Testing Checklist

- [ ] View conversation list
- [ ] Click conversation to open chat window
- [ ] View message history (bot + user messages)
- [ ] Take over conversation (flags set in DB)
- [ ] Send message as agent (appears in WhatsApp)
- [ ] Message saved to database correctly
- [ ] Handoff timestamp extended on send
- [ ] User replies saved without bot response
- [ ] Release conversation (flags cleared)
- [ ] Bot resumes responding after release
- [ ] Auto-expiration after 7 hours
- [ ] Countdown timer updates correctly
- [ ] Real-time updates work
- [ ] Error handling (network failures)
- [ ] Mobile responsive design

## Support

For questions about the WhatsApp API or database schema, contact the backend team.

For Twilio issues, refer to: https://www.twilio.com/docs/whatsapp
For Supabase issues, refer to: https://supabase.com/docs
