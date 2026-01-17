# Lumiera - WhatsApp Agentic Copilot for Construction Subcontractors

![CI](https://github.com/travoro/lumiera_whatsapp_api/workflows/CI/badge.svg)
![CD](https://github.com/travoro/lumiera_whatsapp_api/workflows/CD%20-%20Deploy/badge.svg)
![Code Quality](https://github.com/travoro/lumiera_whatsapp_api/workflows/Code%20Quality/badge.svg)
[![codecov](https://codecov.io/gh/travoro/lumiera_whatsapp_api/branch/main/graph/badge.svg)](https://codecov.io/gh/travoro/lumiera_whatsapp_api)

A WhatsApp-first AI assistant built with Python, LangChain, and Claude Opus 4.5 for construction subcontractors (BTP).

## Overview

Lumiera enables construction subcontractors to manage their projects entirely through WhatsApp. The system integrates with Supabase for data management and PlanRadar for project/task management, providing a seamless conversational interface in multiple languages.

## Features

- **WhatsApp-Only Interface**: Subcontractors interact exclusively via WhatsApp
- **Multi-Language Support**: Automatic translation between user language and French (internal)
- **Project Management**: List projects, view tasks, access documents
- **Incident Reporting**: Submit and update incident reports with photos
- **Task Management**: Update progress, add comments, mark tasks complete
- **Audio Transcription**: Automatic transcription of voice messages
- **Human Handoff**: Escalation to admin when needed
- **Full Auditability**: All messages and actions logged

## Tech Stack

- **Python 3.11+**
- **FastAPI**: Web framework for webhooks
- **LangChain**: Agent orchestration
- **Claude Opus 4.5**: AI model (Anthropic)
- **Twilio**: WhatsApp messaging
- **Supabase**: Database and storage
- **PlanRadar API**: Project/task management
- **OpenAI Whisper**: Audio transcription

## Project Structure

```
whatsapp_api/
├── src/
│   ├── main.py                 # FastAPI application entry point
│   ├── config.py               # Configuration management
│   ├── agent/
│   │   ├── agent.py            # LangChain agent setup
│   │   └── tools.py            # LangChain tools
│   ├── handlers/
│   │   ├── webhook.py          # Twilio webhook endpoints
│   │   └── message.py          # Message processing logic
│   ├── services/
│   │   ├── translation.py      # Translation service
│   │   ├── transcription.py    # Audio transcription
│   │   └── escalation.py       # Human handoff
│   ├── integrations/
│   │   ├── supabase.py         # Supabase client
│   │   ├── planradar.py        # PlanRadar API client
│   │   └── twilio.py           # Twilio client
│   ├── actions/
│   │   ├── projects.py         # Project actions
│   │   ├── tasks.py            # Task actions
│   │   ├── incidents.py        # Incident reporting
│   │   └── documents.py        # Document access
│   └── utils/
│       └── logger.py           # Logging setup
├── tests/
├── .env                        # Environment variables
├── .env.example                # Example configuration
├── requirements.txt            # Python dependencies
├── PROJECT_SPECS.md            # Detailed specifications
└── README.md                   # This file
```

## Prerequisites

- Python 3.11 or higher
- Twilio account with WhatsApp enabled
- Anthropic API key (Claude)
- Supabase account
- PlanRadar API access
- OpenAI API key (for Whisper)

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd whatsapp_api
```

### 2. Create Virtual Environment

```bash
python -m venv venv

# On Linux/Mac
source venv/bin/activate

# On Windows
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` and add your credentials:

```env
# Required credentials
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

ANTHROPIC_API_KEY=your_anthropic_api_key

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key

PLANRADAR_API_KEY=your_planradar_api_key
PLANRADAR_ACCOUNT_ID=your_account_id

OPENAI_API_KEY=your_openai_api_key

SECRET_KEY=generate_with_openssl_rand_hex_32
```

### 5. Set Up Supabase Database

Create the following tables in your Supabase database:

#### Users Table

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    whatsapp_number TEXT UNIQUE NOT NULL,
    language TEXT DEFAULT 'fr',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### Messages Table

```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    message_text TEXT,
    original_language TEXT,
    direction TEXT, -- 'inbound' or 'outbound'
    message_sid TEXT,
    media_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### Action Logs Table

```sql
CREATE TABLE action_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    action_name TEXT NOT NULL,
    parameters JSONB,
    result JSONB,
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### Projects Table

```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    location TEXT,
    status TEXT,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### Escalations Table

```sql
CREATE TABLE escalations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    reason TEXT,
    context JSONB,
    status TEXT DEFAULT 'pending',
    resolution_note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 6. Create Storage Bucket

In Supabase, create a storage bucket named `whatsapp-media` for storing media files.

## Running the Application

### Development Mode

```bash
python src/main.py
```

Or using uvicorn directly:

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Production Mode

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Setting Up Twilio Webhook

1. Make your local server publicly accessible using ngrok or similar:

```bash
ngrok http 8000
```

2. Copy the HTTPS URL provided by ngrok (e.g., `https://abc123.ngrok.io`)

3. In Twilio Console:
   - Go to your WhatsApp Sandbox or WhatsApp number
   - Set the webhook URL to: `https://abc123.ngrok.io/webhook/whatsapp`
   - Set HTTP method to `POST`

4. Test by sending a message to your WhatsApp number

## Testing

### Health Check

```bash
curl http://localhost:8000/health
```

### Webhook Test

```bash
curl http://localhost:8000/webhook/whatsapp
```

### Run Tests

```bash
pytest tests/
```

## Usage

Once set up, users can interact with the bot via WhatsApp:

**Example Conversations:**

```
User: "Bonjour, quels sont mes projets actifs?"
Bot: "Vous avez 3 projets actifs:
1. Chantier Lyon - ID: abc123
2. Rénovation Paris - ID: def456
3. Construction Marseille - ID: ghi789"

User: "Montre-moi les tâches du projet abc123"
Bot: "5 tâches trouvées pour Chantier Lyon:
1. Installer l'électricité - Statut: en cours
2. Plomberie - Statut: à faire
..."
```

## Allowed Actions

The bot supports these actions:

- `list_projects` - List active construction sites
- `list_tasks` - List tasks for a project
- `get_task_description` - Get task details
- `get_task_plans` - Get blueprints/plans
- `get_task_images` - Get task images
- `get_documents` - Access project documents
- `add_task_comment` - Add comment to task
- `get_task_comments` - View task comments
- `submit_incident_report` - Report an incident (requires image + text)
- `update_incident_report` - Update existing incident
- `update_task_progress` - Update task status with photos
- `mark_task_complete` - Mark task as done
- `set_language` - Change user language
- `escalate_to_human` - Request human admin

## Language Support

Supported languages (24 total):

**Western European:**
- French (fr) - Default
- English (en)
- Spanish (es)
- Portuguese (pt)
- German (de)
- Italian (it)

**Eastern European:**
- Romanian (ro)
- Polish (pl)
- Czech (cs)
- Slovak (sk)
- Hungarian (hu)
- Bulgarian (bg)
- Serbian (sr)
- Croatian (hr)
- Slovenian (sl)
- Ukrainian (uk)
- Russian (ru)
- Lithuanian (lt)
- Latvian (lv)
- Estonian (et)
- Albanian (sq)
- Macedonian (mk)
- Bosnian (bs)

**Middle Eastern:**
- Arabic (ar)

All internal processing happens in French, with automatic translation for inbound/outbound messages.

## Monitoring

### Logs

Logs are stored in the `logs/` directory:
- `lumiera_YYYY-MM-DD.log` - General logs
- `errors_YYYY-MM-DD.log` - Error logs

### LangSmith (Optional)

Enable LangChain tracing in `.env`:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langchain_api_key
```

### Sentry (Optional)

Enable error tracking in `.env`:

```env
ENABLE_SENTRY=true
SENTRY_DSN=your_sentry_dsn
```

## Security

- All webhooks are validated with Twilio signatures
- Service role keys are never exposed to clients
- All actions are audited in the database
- User authentication via WhatsApp number
- Secret key for encryption/JWT

## Troubleshooting

### Bot not responding

1. Check logs: `tail -f logs/lumiera_*.log`
2. Verify webhook URL is correct in Twilio
3. Check ngrok is running (for local dev)
4. Verify all API keys in `.env`

### Translation issues

1. Check Anthropic API key is valid
2. Verify supported languages list
3. Check logs for translation errors

### Database connection issues

1. Verify Supabase credentials
2. Check database tables are created
3. Test connection from Supabase dashboard

## Contributing

1. Create a feature branch
2. Make your changes
3. Add tests
4. Submit a pull request

## License

[Your License Here]

## Support

For issues and questions:
- GitHub Issues: [repository-url]/issues
- Documentation: See `PROJECT_SPECS.md`

## Roadmap

- [ ] Add more integrations (Slack, Teams)
- [ ] Enhanced analytics dashboard
- [ ] Voice message responses
- [ ] Image recognition for incident reports
- [ ] Batch operations
- [ ] Mobile admin app

<!-- Deployment test: Sat Jan 17 20:06:45 CET 2026 -->
