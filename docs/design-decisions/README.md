# Design Decisions

This document explains key architectural and design decisions made in the Lumiera WhatsApp API.

## Table of Contents
- [Core Principles](#core-principles)
- [Major Decisions](#major-decisions)
- [Technology Choices](#technology-choices)
- [Trade-offs](#trade-offs)

---

## Core Principles

### 1. WhatsApp-Only for Subcontractors
**Decision**: Subcontractors interact exclusively via WhatsApp. No additional apps or web interfaces.

**Rationale**:
- ✅ Zero learning curve - everyone uses WhatsApp
- ✅ No app installation required
- ✅ Works on any phone (even older models)
- ✅ Familiar interface reduces friction
- ✅ High adoption rate in construction industry

**Trade-offs**:
- ❌ Limited by WhatsApp capabilities (no custom UI)
- ❌ Dependent on Twilio for WhatsApp Business API
- ❌ Message rate limits (Twilio)

### 2. French as Internal Language
**Decision**: All internal processing, database content, and agent reasoning happens in French.

**Rationale**:
- ✅ Consistent data format
- ✅ Simpler database queries (one language)
- ✅ Better agent performance (trained on French corpus)
- ✅ Easier debugging and maintenance
- ✅ French is primary language for construction in France

**Implementation**:
- Translate inbound messages to French
- Process everything in French
- Translate outbound responses to user language

### 3. Supabase as Source of Truth
**Decision**: Supabase (PostgreSQL) is the single source of truth for all data.

**Rationale**:
- ✅ Relational database for complex queries
- ✅ Built-in auth and storage
- ✅ Real-time capabilities
- ✅ Row-level security (RLS)
- ✅ Great developer experience
- ✅ Cost-effective

**Trade-offs**:
- ❌ Vendor lock-in to some extent
- ❌ Need to manage migrations carefully

### 4. Claude Opus 4.5 for Agent
**Decision**: Use Claude Opus 4.5 as the AI model for the full agent.

**Rationale**:
- ✅ Best-in-class reasoning capabilities
- ✅ Excellent tool use (function calling)
- ✅ Long context window (200k tokens)
- ✅ Multilingual support
- ✅ High quality output
- ✅ Good at following complex instructions

**Trade-offs**:
- ❌ Higher cost ($15/1M input tokens, $75/1M output)
- ❌ Slower than smaller models (3-5s response)
- ❌ Solution: Hybrid system with fast path

### 5. Hybrid Fast Path System
**Decision**: Route high-confidence intents to fast path handlers, use full agent for complex cases.

**Rationale**:
- ✅ 50% cost reduction
- ✅ 3-5x faster for common intents
- ✅ Same quality user experience
- ✅ Scalable to high volumes

**Details**: See [Fast Path System](../architecture/FAST_PATH_SYSTEM.md)

---

## Major Decisions

### Pipeline Architecture

**Decision**: Refactor message processing into a 9-stage pipeline.

**Rationale**:
- ✅ **Testability**: Test each stage independently
- ✅ **Maintainability**: Clear separation of concerns
- ✅ **Error Handling**: Structured error propagation
- ✅ **Observability**: Log progress at each stage
- ✅ **Extensibility**: Easy to add new stages

**Before**: 439-line god function
**After**: 9 discrete stages (< 50 lines each)

**Impact**: 63% code reduction, 100% better maintainability

**Details**: See [Architectural Refactors](./ARCHITECTURAL_REFACTORS.md)

### Structured Error Handling

**Decision**: Implement custom exception hierarchy and Result wrapper.

**Rationale**:
- ✅ **Consistent errors**: Standardized error codes
- ✅ **User-friendly messages**: Separate technical and user messages
- ✅ **Context preservation**: Error details for debugging
- ✅ **Clean propagation**: Result wrapper avoids exception throwing
- ✅ **Better UX**: Users get helpful error messages

**Components**:
- `ErrorCode` enum (20+ codes)
- `LumieraException` base class
- 8 specific exception types
- `Result[T]` wrapper

**Details**: See [Error Handling](../architecture/ERROR_HANDLING.md)

### Database Abstraction

**Decision**: Encapsulate all database operations in SupabaseClient with repository methods.

**Rationale**:
- ✅ **Separation of concerns**: Handlers don't touch database directly
- ✅ **Testability**: Easy to mock database
- ✅ **Consistency**: Standardized database access patterns
- ✅ **Error handling**: Centralized error handling
- ✅ **Type safety**: Clear return types

**Before**: 17 violations (direct database access in handlers)
**After**: 0 violations (16 new repository methods)

**Details**: See [Database Abstraction](./DATABASE_ABSTRACTION.md)

### Intent Router

**Decision**: Centralize intent routing to avoid handler-to-handler calls.

**Rationale**:
- ✅ **Proper layering**: Handlers don't call other handlers
- ✅ **Single routing point**: Easy to modify routing logic
- ✅ **Lazy loading**: Avoid circular imports
- ✅ **Middleware potential**: Can add logging, metrics, etc.

**Before**: Handlers directly called other handlers
**After**: IntentRouter as central orchestrator

### Thread-Safe Execution Context

**Decision**: Replace global mutable dict with ContextVar for execution tracking.

**Rationale**:
- ✅ **Thread safety**: Safe for concurrent requests
- ✅ **Isolation**: Each request has its own context
- ✅ **Clean up**: Automatic cleanup via context manager
- ✅ **No race conditions**: No shared mutable state

**Before**: `execution_context = {"escalation_occurred": False, ...}`
**After**: `execution_context: ContextVar[ExecutionContext]`

---

## Technology Choices

### FastAPI

**Why FastAPI?**
- ✅ Modern async support
- ✅ Automatic API documentation
- ✅ Pydantic validation
- ✅ High performance
- ✅ Easy to deploy
- ✅ Great developer experience

**Alternatives Considered**:
- Flask: Too synchronous, less modern
- Django: Too heavyweight for our use case
- Sanic: Less mature ecosystem

### LangChain

**Why LangChain?**
- ✅ Built-in agent framework
- ✅ Tool calling abstraction
- ✅ Memory management
- ✅ LangSmith integration
- ✅ Large community
- ✅ Well-documented

**Alternatives Considered**:
- Raw Claude API: Too much boilerplate
- LlamaIndex: More focused on RAG
- Custom solution: Reinventing the wheel

### Twilio

**Why Twilio?**
- ✅ Official WhatsApp Business API partner
- ✅ Reliable delivery
- ✅ Good documentation
- ✅ Webhook support
- ✅ Interactive messages (list pickers, buttons)
- ✅ Media handling

**Alternatives Considered**:
- Direct WhatsApp Business API: More complex, less reliable
- Other providers: Less mature, fewer features

### Supabase

**Why Supabase?**
- ✅ PostgreSQL (battle-tested)
- ✅ Built-in storage
- ✅ Real-time subscriptions
- ✅ Row-level security
- ✅ Great dashboard
- ✅ Cost-effective
- ✅ Easy to scale

**Alternatives Considered**:
- Raw PostgreSQL: Need to manage storage separately
- MongoDB: Relational data fits better in SQL
- Firebase: More expensive, less flexible

### OpenAI Whisper

**Why Whisper?**
- ✅ State-of-the-art transcription
- ✅ Multilingual support
- ✅ Robust to accents and noise
- ✅ Fast enough (2-5s for typical audio)
- ✅ Affordable

**Alternatives Considered**:
- Google Speech-to-Text: More expensive
- AssemblyAI: Less accurate for French
- AWS Transcribe: More complex setup

---

## Trade-offs

### Fast Path vs Quality

**Trade-off**: Fast path may miss nuances that full agent would catch.

**Decision**: Use high confidence threshold (90%) to minimize risk.

**Mitigation**:
- Automatic fallback to full agent if fast path fails
- Monitor fast path success rate
- Continuously improve handlers based on feedback

### Cost vs Speed

**Trade-off**: Opus is expensive but provides best quality.

**Decision**: Hybrid system - use Haiku for classification, Opus only when needed.

**Impact**:
- 50% of requests use fast path (Haiku only)
- 50% cost reduction
- 3-5x faster for common intents
- Same quality for complex queries

### Flexibility vs Simplicity

**Trade-off**: More features = more complexity.

**Decision**: Focus on core use cases, add features incrementally.

**Principle**: Start simple, add complexity only when needed.

### Consistency vs Performance

**Trade-off**: More validation = slower responses.

**Decision**: Validate at boundaries, trust internal code.

**Implementation**:
- Validate user input (security)
- Trust database responses (consistency)
- Validate tool inputs (safety)
- Skip validation for internal operations

---

## Lessons Learned

### From God Function to Pipeline

**Problem**: 439-line function was unmaintainable.

**Solution**: Break into discrete stages with clear interfaces.

**Lesson**: Single Responsibility Principle is crucial for maintainability.

### From Generic Errors to Structured Errors

**Problem**: Hard to debug errors, poor user experience.

**Solution**: Custom exception hierarchy with error codes and user messages.

**Lesson**: Invest in error handling early - it pays off quickly.

### From Direct DB Access to Repository

**Problem**: Tight coupling between handlers and database.

**Solution**: Centralize database access in SupabaseClient.

**Lesson**: Abstraction layers make code testable and maintainable.

### From Global State to ContextVar

**Problem**: Global mutable state caused race conditions.

**Solution**: Thread-local context with automatic cleanup.

**Lesson**: Avoid global state in concurrent applications.

---

## Future Considerations

### Caching Layer

**Consideration**: Add Redis for caching common queries.

**Benefits**:
- Faster responses for repeated queries
- Reduced database load
- Lower costs

**Complexity**:
- Cache invalidation logic
- Another dependency to manage

**Decision**: Not yet needed, revisit at scale.

### Event Sourcing

**Consideration**: Store all events for complete audit trail.

**Benefits**:
- Complete history of all changes
- Easy to replay events
- Better analytics

**Complexity**:
- More complex data model
- Storage overhead

**Decision**: Current audit logging is sufficient for now.

### Microservices

**Consideration**: Split into separate services (translation, agent, database).

**Benefits**:
- Independent scaling
- Language diversity (not just Python)
- Fault isolation

**Complexity**:
- Network overhead
- More moving parts
- Distributed debugging

**Decision**: Monolith is fine for current scale (< 10k users).

---

## Related Documentation

- [Architectural Refactors](./ARCHITECTURAL_REFACTORS.md) - History of major refactorings
- [Intent-Driven Formatting](./INTENT_DRIVEN_FORMATTING.md) - Why only certain intents use interactive lists
- [Fast Path Rationale](../architecture/FAST_PATH_SYSTEM.md) - Why we built fast path
- [Architecture Overview](../architecture/README.md) - System architecture
- [Pipeline Architecture](../architecture/PIPELINE_ARCHITECTURE.md) - Pipeline design
- [Error Handling](../architecture/ERROR_HANDLING.md) - Error system design

---

**Last Updated**: 2026-01-06
**Version**: 2.1.0
