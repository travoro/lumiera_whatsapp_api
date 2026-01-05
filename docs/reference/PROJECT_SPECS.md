# Lumiera - WhatsApp Agentic Copilot for Construction Subcontractors

## Overview
Lumiera is a WhatsApp-first agentic copilot designed for construction subcontractors (BTP - Bâtiment et Travaux Publics).

**User Interfaces:**
- **Subcontractors**: WhatsApp-only interface
- **Admins**: Supabase back office

## Key Principles

1. **WhatsApp-only interface for subcontractors**
   - All subcontractor interactions happen through WhatsApp
   - No additional apps or interfaces required

2. **Supabase and PlanRadar as source of truth**
   - Supabase: Database, storage, user management
   - PlanRadar: Projects, tasks, documents, and attachments

3. **User language preserved for UX**
   - Each subcontractor has a preferred language
   - Messages displayed in user's preferred language

4. **Strict action whitelist**
   - Only predefined actions are allowed
   - Security and control through explicit action list

5. **Human override always possible**
   - Escalation mechanism for complex situations
   - Admin can intervene at any time

## Language & Translation

### Translation Flow
- **Inbound**: Messages stored in original language + language metadata
- **Processing**: All internal logic and database data in French
- **Outbound**: Messages translated to user's preferred language

### Storage
- Original message language preserved
- Language metadata tracked per message
- User language preference stored in profile

## Core Features

### 1. Chantier Management
- List active chantiers (construction sites) from Supabase
- Filter and search capabilities
- Status tracking

### 2. Task Management (PlanRadar API)
- View tasks per chantier
- Get detailed task descriptions
- Update task progress
- Add photos to tasks to show progress
- Mark tasks as complete

### 3. Document Access (PlanRadar API)
- Access project documents
- View photos and attachments
- Retrieve task-specific files
- Access task plans

### 4. Incident Reporting (PlanRadar API)
- Report incidents with:
  - Text descriptions
  - Photos (required)
  - Audio messages (transcribed to text)
- Update existing incident reports
- Add additional information to incidents

### 5. Task Communication (PlanRadar API)
- Add comments to tasks
- Audio comments transcribed to French
- View task comment history

### 6. Multi-language Support
- Dynamic language switching
- Automatic language detection
- User preference management

## Integrations

### 1. Twilio WhatsApp
- **Purpose**: Inbound/outbound messaging
- **Functions**:
  - Receive messages from users
  - Send responses to users
  - Handle media (images, audio)

### 2. Supabase
- **Purpose**: Database, Storage, Back Office
- **Functions**:
  - User management
  - Chantier (project) data
  - Message history
  - Audit logs
  - Admin interface

### 3. PlanRadar API
- **Purpose**: Project and task management
- **Functions**:
  - Project/task data
  - Document management
  - Incident reporting
  - Progress tracking

### 4. LangChain + Claude Opus 4.5
- **Purpose**: AI agent orchestration
- **Functions**:
  - Natural language understanding
  - Intent classification
  - Action routing
  - Response generation

## Allowed Actions (Whitelist)

### Project Actions
- `list_projects` - List active chantiers from Supabase

### Task Actions (PlanRadar)
- `list_tasks` - List tasks for a specific chantier
- `get_task_description` - Get detailed task information
- `get_task_plans` - Retrieve task plans/blueprints
- `get_task_images` - Get images attached to a task
- `get_task_comments` - View all comments on a task
- `add_task_comment` - Add text comment to task (audio transcribed to French first)
- `update_task_progress` - Update task status and add progress photos
- `mark_task_complete` - Mark a task as done

### Document Actions (PlanRadar)
- `get_documents` - Retrieve project documents and attachments

### Incident Actions (PlanRadar)
- `submit_incident_report` - Create new incident (requires text/transcribed audio + at least one image)
- `update_incident_report` - Add additional text or images to existing incident

### System Actions
- `set_language` - Change user's preferred language
- `escalate_to_human` - Trigger human admin intervention

## Human Handoff Protocol

### Escalation Triggers
- Unsupported request types
- Low confidence in intent classification
- User explicitly requests human assistance
- Complex situations requiring judgment

### Escalation Process
1. Bot notifies admin immediately
2. User informed of escalation
3. Bot pauses interaction with user
4. Admin receives notification with context
5. Admin handles interaction or releases bot
6. Maximum escalation time: 24 hours

### Post-Escalation
- Conversation history preserved
- Admin actions logged
- User notified when bot resumes

## Acceptance Criteria

### 1. Language Consistency
- User always receives replies in their preferred language
- Language switching works seamlessly
- Original messages preserved for audit

### 2. Full Auditability
- All messages logged with timestamps
- All actions tracked with user attribution
- Language metadata captured
- Admin actions logged

### 3. Reliability
- Actions only succeed with valid permissions
- Error messages clear and actionable
- Graceful degradation when services unavailable

### 4. Security
- Strict action whitelist enforced
- User authentication via WhatsApp
- Data access controlled per user role
- PII handled according to regulations

## Technical Architecture

### Stack
- **Language**: Python 3.11+
- **Framework**: LangChain
- **LLM**: Claude Opus 4.5 (Anthropic)
- **Messaging**: Twilio WhatsApp API
- **Database**: Supabase (PostgreSQL)
- **Project Management**: PlanRadar API

### Key Components
1. **Message Handler**: Twilio webhook receiver
2. **Agent Orchestrator**: LangChain agent with tool calling
3. **Translation Service**: Bidirectional translation (user language ↔ French)
4. **Action Handlers**: Individual functions for each allowed action
5. **Escalation Manager**: Human handoff coordination
6. **Audit Logger**: Complete message and action tracking

## Data Flow

### Inbound Message Flow
1. User sends WhatsApp message → Twilio
2. Twilio webhook → Message Handler
3. Store original message (language + content)
4. Translate to French if needed
5. LangChain agent processes (in French)
6. Agent selects action(s)
7. Execute action(s)
8. Generate response (in French)
9. Translate to user language
10. Send via Twilio → User

### Outbound Message Flow
1. System generates message in French
2. Translate to user's preferred language
3. Send via Twilio WhatsApp API
4. Log message and delivery status

## Implementation Notes

### Translation Strategy
- Use Claude for high-quality contextual translation
- Cache common phrases per language
- Maintain parallel storage: original + French

### Error Handling
- API failures trigger graceful responses
- User informed in their language
- Admins notified of system errors
- Automatic retry with exponential backoff

### Media Handling
- Images: Store in Supabase, reference in PlanRadar
- Audio: Transcribe with Whisper API, store text
- Documents: Link from PlanRadar, proxy through bot

### Performance
- Async operations for all external APIs
- Response time target: < 3 seconds
- Media upload time: < 10 seconds
- Batch operations where possible
