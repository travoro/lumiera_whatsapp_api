# Lumiera WhatsApp API - Documentation Index

Welcome to the Lumiera WhatsApp API documentation! This guide will help you understand, develop, and maintain the system.

## 📚 Documentation Structure

### Getting Started
Start here if you're new to the project:
- **[Quick Start Guide](./getting-started/QUICKSTART.md)** - Get up and running in 10 minutes
- **[Installation Guide](../README.md)** - Detailed installation and setup instructions
- **[Development Workflow](./getting-started/WORKFLOW.md)** - "Ship it" workflow for rapid development
- **[Development Tools](./getting-started/DEVELOPMENT.md)** - Auto-reload, auto-test, pre-commit hooks
- **[Git Setup](./getting-started/GIT-SETUP.md)** - Git configuration guide

### Architecture
Understand how the system works:
- **[Architecture Overview](./architecture/README.md)** - High-level system architecture
- **[Pipeline Architecture](./architecture/PIPELINE_ARCHITECTURE.md)** - Message processing pipeline (9 stages)
- **[Error Handling System](./architecture/ERROR_HANDLING.md)** - Structured error propagation
- **[Fast Path System](./architecture/FAST_PATH_SYSTEM.md)** - Performance optimization via confidence-based routing
- **[Task Update Audit](./architecture/TASK_UPDATE_AUDIT_COMPREHENSIVE.md)** - Comprehensive task update flow analysis

### FSM System
Finite State Machine for conversation flow:
- **[FSM Implementation Summary](./fsm/FSM_IMPLEMENTATION_SUMMARY.md)** - Complete FSM implementation overview
- **[FSM Activation Guide](./fsm/FSM_ACTIVATION_GUIDE.md)** - How to enable and configure FSM
- **[FSM Verification Report](./fsm/FSM_VERIFICATION_REPORT.md)** - Test results and validation
- **[Agent State Implementation](./fsm/AGENT_STATE_IMPLEMENTATION.md)** - State management architecture

### Testing
Test suite documentation and guides:
- **[Test Suite Summary](./testing/TEST_SUITE_SUMMARY.md)** - Overview of 170+ tests
- **[How Tests Work](./testing/HOW_TESTS_WORK.md)** - Test architecture and patterns
- **Running Tests**: `./run_tests.sh` or `./run_tests.sh -v` for verbose output

### Design Decisions
Learn why things are built the way they are:
- **[Design Decisions Overview](./design-decisions/README.md)** - Key architectural decisions
- **[Architectural Refactors](./design-decisions/ARCHITECTURAL_REFACTORS.md)** - History of major refactorings
- **[Intent-Driven Formatting](./design-decisions/INTENT_DRIVEN_FORMATTING.md)** - Why only certain intents use interactive lists
- **[Fast Path Rationale](./design-decisions/FAST_PATH_RATIONALE.md)** - Why we built the fast path system
- **[Database Abstraction](./design-decisions/DATABASE_ABSTRACTION.md)** - Repository pattern adoption

### API & Integrations
Technical reference for APIs and integrations:
- **[PlanRadar API Reference](./reference/planradar_api.md)** - PlanRadar integration guide
- **[Twilio List Picker Guide](./reference/GUIDE_TWILIO_LIST_PICKER.md)** - WhatsApp interactive lists
- **[PlanRadar UUID Implementation](./reference/PLANRADAR_UUID_IMPLEMENTATION.md)** - UUID handling for PlanRadar
- **[PlanRadar Rate Limit Monitoring](./reference/PLANRADAR_RATE_LIMIT_MONITORING.md)** - API rate limit strategies

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

### Deployment & CI/CD
Automated testing and deployment:
- **[CI/CD Pipeline Guide](./deployment/CI-CD.md)** - Complete CI/CD setup with GitHub Actions
- **[CI/CD Setup Checklist](./deployment/CICD-SETUP-CHECKLIST.md)** - Quick start checklist
- **GitHub Actions**: Automated testing, code quality, security scanning, deployment
- **Docker Support**: Multi-stage builds, docker-compose for local development

### Development
Guides for developers:
- **[Test Suite Summary](./testing/TEST_SUITE_SUMMARY.md)** - 170 tests covering security, FSM, pipeline, templates
- **[How Tests Work](./testing/HOW_TESTS_WORK.md)** - Test architecture and patterns
- **Running Tests**: Execute `./run_tests.sh` from project root

### Reference
Additional reference materials:
- **[Project Specifications](./reference/PROJECT_SPECS.md)** - Original project specifications
- **[Changelog](./reference/CHANGELOG.md)** - Version history and changes (latest: 2026-01-17)
- **[Implementation Progress](./reference/IMPLEMENTATION_PROGRESS.md)** - Current implementation status
- **[Active Project Context](./reference/active_project_context.md)** - Current project context
- **[Language Handling Audit](./reference/language_handling_audit.md)** - Multi-language support
- **[Translation Architecture](./reference/backoffice_translation_architecture.md)** - Translation system design

### Investigations
Historical bug fixes and performance improvements:
- **[All Investigations](./investigations/)** - 22 documented fixes and analyses (2026-01-14 to 2026-01-17)

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
1. Check [CI/CD Pipeline Guide](./deployment/CI-CD.md)
2. Review [CI/CD Setup Checklist](./deployment/CICD-SETUP-CHECKLIST.md)
3. Study [Database Schema](./database/SCHEMA.md)
4. Review [Security Best Practices](./security/BEST_PRACTICES.md)
5. Monitor [Changelog](./reference/CHANGELOG.md)

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

### 2026-01-17: Documentation Organization & Test Suite Optimization
- **Test Suite**: 170/170 tests passing (100% pass rate, 3.78s execution)
- **Documentation**: Organized 40+ markdown files into logical subfolders
- **Logs**: Reduced logs folder size by 50% (30M → 16M)
- **Infrastructure**: Added `.env.test` and `run_tests.sh` for easy testing
- **Security**: 37 security tests (prompt injection, XSS, SQL injection, path traversal)

### 2026-01-16: FSM Implementation & PlanRadar Optimization
- **FSM System**: Complete finite state machine for conversation flow
  - 8 conversation states with 20+ validated transitions
  - Idempotency handling and session management
  - Graceful server restart recovery
- **PlanRadar**: 50% reduction in API calls through caching and optimization
- **Bug Fixes**: Resolved task filtering, option selection, app restart recovery

### 2026-01-14: Bug Fixes & Performance Improvements
- Fixed 42 WhatsApp template length violations
- Improved intent classification accuracy
- Enhanced error logging and validation
- Fixed task selection regex patterns

### 2026-01-05: Pipeline Refactor + Error Propagation
- Refactored 439-line god function into 9-stage pipeline (63% reduction)
- Implemented structured error handling with custom exceptions
- Added Result wrapper for consistent error propagation
- Created comprehensive documentation structure

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

**Last Updated**: 2026-01-17
**Version**: 2.1.0
**Status**: Production Ready ✅

### What's New in 2.1.0
- ✅ FSM conversation flow management
- ✅ 170 comprehensive tests (100% passing)
- ✅ 50% reduction in PlanRadar API calls
- ✅ Complete documentation reorganization
- ✅ Improved security testing coverage
