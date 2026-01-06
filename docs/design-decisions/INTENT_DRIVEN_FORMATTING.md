# Intent-Driven Response Formatting

**Status:** ✅ Implemented
**Date:** January 6, 2026
**Component:** Message Handler (src/handlers/message.py)

## Context

The WhatsApp API supports both plain text messages and interactive list messages with clickable items. Initially, the system attempted to format **all** agent responses as interactive lists by searching for numbered patterns, regardless of the intent or expected response type.

This created two problems:
1. **Conversational responses** with suggestions were being incorrectly parsed as interactive lists
2. **Large datasets** (e.g., 20+ documents) exceeded WhatsApp's 10-item interactive list limit

## Decision

Implement **intent-driven formatting** where only specific intents with known structured outputs are formatted as interactive lists.

### Interactive List Intents

Only these three intents use interactive list formatting:

```python
INTERACTIVE_LIST_INTENTS = {"greeting", "list_projects", "list_tasks"}
```

**Rationale:**
- **greeting**: Fixed menu with 6 options
- **list_projects**: Typically 1-5 projects per subcontractor
- **list_tasks**: Usually 5-10 tasks per project
- All stay within WhatsApp's 10-item limit
- All represent **structured data selection** use cases

### Plain Text Intents

All other intents send responses as plain text:

- **list_documents**: Can have 20-50 documents → Exceeds WhatsApp limit, needs scrollable text
- **escalate**: Simple confirmation message
- **report_incident**: Conversational guidance flow
- **update_progress**: Conversational feedback
- **general**: AI conversational response (may include suggestions, but not structured selection)

## Implementation

### Location
`src/handlers/message.py`, lines 353-385

### Code Logic

```python
if intent in INTERACTIVE_LIST_INTENTS:
    # Format as clickable interactive list
    log.info(f"📱 Intent '{intent}' expects structured data → Formatting as interactive list")
    message_text, interactive_data = format_for_interactive(response_text, user_language)
else:
    # Send as plain text
    log.info(f"📱 Intent '{intent}' is conversational → Sending as plain text")

    # Type safety: Handle LangChain agent returning list instead of string
    if isinstance(response_text, list):
        log.info(f"📝 Agent returned list type, joining into string")
        message_text = '\n'.join(str(item) for item in response_text)
    else:
        message_text = response_text

    interactive_data = None
```

## Consequences

### Positive

1. **Semantic Correctness**: Only structured data intents trigger interactive formatting
2. **No Forced Parsing**: Conversational responses remain natural
3. **Handles Large Datasets**: Documents and other large lists sent as scrollable text
4. **Type Safety**: Handles LangChain returning list types without breaking
5. **Performance**: No unnecessary parsing for non-interactive intents

### Negative

1. **Hardcoded Intent List**: Adding new interactive intents requires code change
2. **Must Remember**: Developers must know which intents use interactive vs text

### Mitigations

- **Documentation**: This document + inline comments explain the design
- **Logging**: Clear log messages indicate which path was taken
- **Convention**: Intent names make it obvious (list_* intents are structured)

## Examples

### Example 1: List Projects (Interactive)

**Input:**
```
Intent: list_projects
Response: "You have 3 projects:\n1. 🏗️ Building A\n2. 🏗️ Building B\n3. 🏗️ Building C"
```

**Output:**
- Formatted as interactive list picker
- User taps to select a project
- Dynamic template created and sent

### Example 2: General Query (Plain Text)

**Input:**
```
Intent: general
Message: "je souhaite aller a la mer et boire une biere"
Response: [
    "Bonjour Albin ! 👋",
    "Ah, la mer et une bière, ça fait rêver ! ☀️🍺",
    "Je suis Lumiera, votre assistante pour la gestion de vos chantiers.",
    "Voici ce que je peux faire pour vous :",
    "1. 🏗️ Voir mes chantiers actifs",
    "2. 📋 Consulter mes tâches",
    "..."
]
```

**Output:**
- List joined into string with newlines
- Sent as plain text message
- User sees suggestions but isn't forced to select

### Example 3: List Documents (Plain Text)

**Input:**
```
Intent: list_documents
Response: "You have 25 documents:\n1. Blueprint A\n2. Blueprint B\n...\n25. Contract Z"
```

**Output:**
- Sent as plain text (exceeds 10-item limit)
- User can scroll through all 25 documents
- Better UX than truncating to 10 items

## Related Components

- **Response Parser** (`src/utils/response_parser.py`): Contains `format_for_interactive()` logic
- **WhatsApp Formatter** (`src/utils/whatsapp_formatter.py`): Handles sending via dynamic templates
- **Intent Classification** (`src/services/intent.py`): Defines all available intents

## Testing Considerations

When testing, verify:

1. **Interactive intents** (greeting, list_projects, list_tasks) create clickable lists
2. **Conversational intents** (general, escalate) send as plain text
3. **Large datasets** (list_documents with 20+ items) send as scrollable text
4. **Type safety** works when agent returns list type
5. **Logging** clearly indicates which path was taken

## Future Considerations

### If Adding New Interactive Intent

1. Verify expected output is ≤10 items
2. Add to `INTERACTIVE_LIST_INTENTS` set
3. Ensure fast-path handler or agent returns structured data
4. Update this documentation

### If Needing Dynamic Selection

Some intents may need conditional formatting:
```python
if intent == "list_documents" and document_count <= 10:
    # Can use interactive for small document lists
    format_as_interactive = True
```

This would require refactoring to a more sophisticated decision system.

## References

- WhatsApp Business API: [Interactive Messages Limits](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages#interactive-messages)
- Design Discussion: GitHub Issue [link if applicable]
- Related Refactor: `GUIDE_TWILIO_LIST_PICKER.md`

## Changelog

- **2026-01-06**: Initial implementation of intent-driven formatting
