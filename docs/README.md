# Lumiera WhatsApp API - Documentation Index

Welcome to the Lumiera WhatsApp API documentation! This guide will help you understand, develop, and maintain the system.

## 📚 Documentation Structure

### Getting Started
Start here if you're new to the project:
- **[Quick Start Guide](./getting-started/QUICKSTART.md)** - Get up and running in 10 minutes
- **[Installation Guide](../README.md)** - Detailed installation and setup instructions

### Architecture
Understand how the system works:
- **[Architecture Overview](./architecture/README.md)** - High-level system architecture
- **[Pipeline Architecture](./architecture/PIPELINE_ARCHITECTURE.md)** - Message processing pipeline (9 stages)
- **[Error Handling System](./architecture/ERROR_HANDLING.md)** - Structured error propagation
- **[Fast Path System](./architecture/FAST_PATH_SYSTEM.md)** - Performance optimization via confidence-based routing
- **[Agent System](./architecture/AGENT_SYSTEM.md)** - LangChain agent and tool architecture
- **[Data Flow](./architecture/DATA_FLOW.md)** - Message flow through the system

### Design Decisions
Learn why things are built the way they are:
- **[Design Decisions Overview](./design-decisions/README.md)** - Key architectural decisions
- **[Architectural Refactors](./design-decisions/ARCHITECTURAL_REFACTORS.md)** - History of major refactorings
- **[Fast Path Rationale](./design-decisions/FAST_PATH_RATIONALE.md)** - Why we built the fast path system
- **[Database Abstraction](./design-decisions/DATABASE_ABSTRACTION.md)** - Repository pattern adoption

### API & Integrations
Technical reference for APIs and integrations:
- **[API Overview](./api/README.md)** - All API integrations
- **[Webhook API](./api/WEBHOOKS.md)** - Twilio webhook endpoints
- **[Database API](./api/DATABASE_API.md)** - Supabase client methods
- **[PlanRadar API](./api/PLANRADAR_API.md)** - PlanRadar integration guide

### Database
Database schema and migrations:
- **[Database Overview](./database/README.md)** - Database architecture
- **[Schema Documentation](./database/SCHEMA.md)** - Complete schema reference
- **[Migration Guide](./database/MIGRATION_GUIDE.md)** - How to run database migrations

### Security
Security best practices and guidelines:
- **[Security Overview](./security/README.md)** - Security architecture
- **[Best Practices](./security/BEST_PRACTICES.md)** - AI agent security framework
- **[Input Validation](./security/INPUT_VALIDATION.md)** - Validation and sanitization

### Development
Guides for developers:
- **[Development Setup](./development/SETUP.md)** - Set up your dev environment
- **[Testing Guide](./development/TESTING.md)** - How to test the system
- **[Deployment Guide](./development/DEPLOYMENT.md)** - Deployment procedures
- **[Contributing](./development/CONTRIBUTING.md)** - How to contribute

### Reference
Additional reference materials:
- **[Project Specifications](./reference/PROJECT_SPECS.md)** - Original project specifications
- **[Changelog](./reference/CHANGELOG.md)** - Version history and changes
- **[Implementation Progress](./reference/IMPLEMENTATION_PROGRESS.md)** - Current implementation status

---

## 🎯 Quick Links

### For New Developers
1. Read [Architecture Overview](./architecture/README.md)
2. Follow [Quick Start Guide](./getting-started/QUICKSTART.md)
3. Review [Design Decisions](./design-decisions/README.md)
4. Check [Security Best Practices](./security/BEST_PRACTICES.md)

### For Contributors
1. Read [Contributing Guide](./development/CONTRIBUTING.md)
2. Review [Development Setup](./development/SETUP.md)
3. Understand [Pipeline Architecture](./architecture/PIPELINE_ARCHITECTURE.md)
4. Check [Testing Guide](./development/TESTING.md)

### For Architects
1. Review [Architecture Overview](./architecture/README.md)
2. Study [Design Decisions](./design-decisions/README.md)
3. Examine [Architectural Refactors](./design-decisions/ARCHITECTURAL_REFACTORS.md)
4. Understand [Error Handling System](./architecture/ERROR_HANDLING.md)

### For Operations/DevOps
1. Check [Deployment Guide](./development/DEPLOYMENT.md)
2. Review [Database Schema](./database/SCHEMA.md)
3. Study [Security Best Practices](./security/BEST_PRACTICES.md)
4. Monitor [Changelog](./reference/CHANGELOG.md)

---

## 🏗️ System Overview

**Lumiera** is a WhatsApp-first AI copilot for construction subcontractors built with:
- **Python 3.11+** & **FastAPI**
- **LangChain** for agent orchestration
- **Claude Opus 4.5** for AI capabilities
- **Twilio** for WhatsApp messaging
- **Supabase** for database and storage
- **PlanRadar API** for project management

### Key Features
- ✅ WhatsApp-only interface for subcontractors
- ✅ Multi-language support (9 languages)
- ✅ Audio transcription and translation
- ✅ Project and task management
- ✅ Incident reporting with photos
- ✅ Fast path optimization (50% faster, 50% cheaper)
- ✅ Structured error handling and logging
- ✅ Human escalation when needed

---

## 📊 Architecture Highlights

### Message Processing Pipeline
Messages flow through a 9-stage pipeline:
1. **Authenticate** - User lookup and validation
2. **Session** - Get or create conversation session
3. **Language** - Detect and confirm language
4. **Audio** - Transcribe audio messages
5. **Translate** - Convert to French (internal language)
6. **Intent** - Classify user intent with confidence
7. **Route** - Fast path or full agent
8. **Response** - Translate back to user language
9. **Persist** - Save messages to database

[Learn more →](./architecture/PIPELINE_ARCHITECTURE.md)

### Fast Path System
High-confidence intents (≥90%) bypass the full agent for 3-5x faster responses:
- **Greetings**: Direct welcome message + menu
- **List Projects**: Direct database query
- **List Tasks**: Context-aware task listing
- **Update Progress**: Interactive progress update flow
- **Escalation**: Direct human handoff

[Learn more →](./architecture/FAST_PATH_SYSTEM.md)

### Error Handling
Structured error propagation with custom exceptions and Result wrapper:
- **ErrorCode enum**: 20+ standardized error codes
- **Custom exceptions**: User-friendly error messages
- **Result wrapper**: Success/failure without throwing exceptions
- **Graceful degradation**: Fallbacks for all error scenarios

[Learn more →](./architecture/ERROR_HANDLING.md)

---

## 🔄 Recent Major Changes

### 2026-01-05: Pipeline Refactor + Error Propagation
- Refactored 439-line god function into 9-stage pipeline (63% reduction)
- Implemented structured error handling with custom exceptions
- Added Result wrapper for consistent error propagation
- Created comprehensive documentation structure

### 2026-01-04: Fast Path Handlers
- Added context-aware fast path handlers for common intents
- Implemented centralized translations for 9 languages
- Enhanced report_incident and update_progress handlers
- Lowered confidence threshold to 90% for better fast path usage

### 2026-01-03: Database Abstraction
- Eliminated database abstraction leakage (17 violations fixed)
- Added 16 new repository methods to SupabaseClient
- Fixed handler layering violations with IntentRouter
- Implemented thread-safe execution context

[View full changelog →](./reference/CHANGELOG.md)

---

## 🎓 Learning Path

### Week 1: Foundations
- Day 1-2: Read architecture overview and pipeline docs
- Day 3-4: Set up development environment
- Day 5: Review design decisions and security practices

### Week 2: Development
- Day 1-2: Understand agent system and tools
- Day 3-4: Study database schema and API integrations
- Day 5: Review error handling and testing

### Week 3: Advanced
- Day 1-2: Deep dive into fast path system
- Day 3-4: Explore monitoring and observability
- Day 5: Contribute your first improvement

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/travoro/lumiera_whatsapp_api/issues)
- **Documentation Questions**: Check this docs index first
- **Security Issues**: Follow security disclosure policy
- **General Questions**: Review [Project Specs](./reference/PROJECT_SPECS.md)

---

## 🤝 Contributing

We welcome contributions! Please read:
1. [Contributing Guidelines](./development/CONTRIBUTING.md)
2. [Development Setup](./development/SETUP.md)
3. [Testing Guide](./development/TESTING.md)
4. [Code Review Process](./development/CODE_REVIEW.md)

---

**Last Updated**: 2026-01-05
**Version**: 2.0.0
**Status**: Production Ready
