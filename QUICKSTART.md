# Quick Start Guide - Lumiera WhatsApp Copilot

This guide will help you get the Lumiera WhatsApp Copilot up and running in minutes.

## Prerequisites Checklist

Before starting, ensure you have:

- [ ] Python 3.11+ installed
- [ ] Twilio account with WhatsApp Sandbox or approved number
- [ ] Anthropic API key (Claude)
- [ ] Supabase account (free tier is fine)
- [ ] PlanRadar API credentials
- [ ] OpenAI API key (for Whisper transcription)

## Step-by-Step Setup

### 1. Install Python Dependencies (5 minutes)

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables (10 minutes)

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your favorite editor
nano .env  # or vim, vscode, etc.
```

**Required Variables:**

```env
# Twilio (get from: https://console.twilio.com/)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# Anthropic (get from: https://console.anthropic.com/)
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx

# Supabase (get from: https://app.supabase.com/)
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# PlanRadar (get from your PlanRadar admin)
PLANRADAR_API_KEY=your_api_key
PLANRADAR_ACCOUNT_ID=your_account_id

# OpenAI (get from: https://platform.openai.com/)
OPENAI_API_KEY=sk-xxxxxxxxxxxxx

# Generate a secret key
SECRET_KEY=$(openssl rand -hex 32)
```

### 3. Set Up Supabase Database (15 minutes)

1. Go to your Supabase project dashboard
2. Navigate to "SQL Editor"
3. Run the SQL scripts from `README.md` section "Set Up Supabase Database"
4. Create storage bucket named `whatsapp-media`
5. Make bucket public (Settings > Storage > whatsapp-media > Make Public)

### 4. Start the Server (1 minute)

```bash
# Option 1: Using the run script
./run.sh

# Option 2: Using Python directly
python src/main.py

# Option 3: Using uvicorn for hot reload
uvicorn src.main:app --reload --port 8000
```

You should see:
```
============================================================
Starting Lumiera WhatsApp Copilot
Environment: development
Debug mode: False
Port: 8000
============================================================
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 5. Expose Your Local Server (5 minutes)

For local development, you need to expose your server to the internet so Twilio can reach it.

**Using ngrok (recommended):**

```bash
# Install ngrok: https://ngrok.com/download
# Or use: brew install ngrok (Mac) / choco install ngrok (Windows)

# Start ngrok
ngrok http 8000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok-free.app`)

### 6. Configure Twilio Webhook (5 minutes)

1. Go to [Twilio Console](https://console.twilio.com/)
2. Navigate to **Messaging > Try it out > Send a WhatsApp message**
3. Under "Sandbox settings", find "When a message comes in"
4. Set webhook URL to: `https://your-ngrok-url.ngrok-free.app/webhook/whatsapp`
5. Set HTTP method to `POST`
6. Save

### 7. Test It! (2 minutes)

1. Open WhatsApp on your phone
2. Send a message to your Twilio WhatsApp number with the join code
3. Try: "Hello" or "Bonjour"
4. Try: "List my projects" or "Quels sont mes projets?"

If everything works, you'll get a response!

## Quick Test Commands

Once connected via WhatsApp, try these:

### English
```
- "Hello"
- "List my projects"
- "Show me tasks for project [ID]"
- "Help"
```

### French
```
- "Bonjour"
- "Quels sont mes projets actifs?"
- "Montre-moi les tâches"
- "Aide"
```

### Spanish
```
- "Hola"
- "Lista mis proyectos"
- "Ayuda"
```

## Troubleshooting

### Server won't start

**Problem:** Import errors or module not found

**Solution:**
```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### No response from bot

**Problem:** Bot doesn't respond to WhatsApp messages

**Solutions:**

1. **Check server is running:**
   ```bash
   curl http://localhost:8000/health
   # Should return: {"status":"healthy"}
   ```

2. **Check ngrok is running:**
   - Visit the ngrok URL in browser
   - Should show: `{"message": "Lumiera WhatsApp Copilot API"}`

3. **Check Twilio webhook:**
   - Twilio Console > Messaging > WhatsApp Sandbox
   - Verify webhook URL is correct

4. **Check logs:**
   ```bash
   tail -f logs/lumiera_*.log
   ```

### Database errors

**Problem:** Can't connect to Supabase

**Solution:**
1. Verify `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in `.env`
2. Test connection in Supabase dashboard
3. Check tables are created (see README.md)

### API key errors

**Problem:** Invalid API key errors

**Solution:**
1. Verify all API keys in `.env` are correct
2. Check API keys haven't expired
3. Ensure no extra spaces in `.env` file

## Next Steps

Once everything is working:

1. **Add Test Data:**
   - Add some projects to your Supabase `projects` table
   - Configure PlanRadar with test projects

2. **Customize:**
   - Modify `src/agent/agent.py` to adjust bot behavior
   - Update supported languages in `.env`
   - Add custom actions in `src/actions/`

3. **Deploy to Production:**
   - See README.md "Production Deployment" section
   - Use a proper domain instead of ngrok
   - Set `ENVIRONMENT=production` in `.env`
   - Configure proper monitoring

4. **Read Documentation:**
   - `README.md` - Full documentation
   - `PROJECT_SPECS.md` - Detailed specifications
   - LangChain docs - https://docs.langchain.com/

## Getting Help

- Check logs: `logs/lumiera_*.log`
- Review `README.md` for detailed documentation
- Check `PROJECT_SPECS.md` for architecture details

## Common Use Cases

### Testing Translation
Send messages in different languages to test translation (24 languages supported):
- "Hello" (English)
- "Hola" (Spanish)
- "Bonjour" (French)
- "Cześć" (Polish)
- "Bună" (Romanian)
- "Привіт" (Ukrainian)
- "Здравей" (Bulgarian)
- "Dobar dan" (Croatian)

### Testing Audio Transcription
Send a voice message in WhatsApp - it will be automatically transcribed to French.

### Testing Incident Reporting
1. Send: "I want to report an incident"
2. Follow the prompts
3. Send a photo
4. Provide description

## Success Criteria

You know it's working when:
- ✓ Server starts without errors
- ✓ Health check returns `{"status":"healthy"}`
- ✓ Bot responds to WhatsApp messages
- ✓ Messages appear in Supabase `messages` table
- ✓ Actions appear in Supabase `action_logs` table

Congratulations! You now have a working WhatsApp AI assistant.
