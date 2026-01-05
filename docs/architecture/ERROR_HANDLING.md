# Error Handling System

Lumiera uses a structured error handling system with custom exceptions and a Result wrapper for consistent error propagation throughout the application.

## Overview

### Why Structured Error Handling?

**Before:**
- Generic Python exceptions
- Inconsistent error messages
- No error codes for categorization
- Difficult to trace error context
- No user-friendly messages

**After:**
- Custom exception hierarchy
- Standardized error codes
- User-friendly and technical messages
- Structured error context
- Result wrapper for clean propagation

---

## Error Code System

### ErrorCode Enum

All errors are categorized with standardized codes:

```python
class ErrorCode(str, Enum):
    """Standard error codes for categorizing failures."""

    # User/Authentication errors (1xxx)
    USER_NOT_FOUND = "USER_1001"
    USER_UNAUTHORIZED = "USER_1002"
    INVALID_PHONE_NUMBER = "USER_1003"

    # Project/Resource errors (2xxx)
    PROJECT_NOT_FOUND = "PROJECT_2001"
    NO_PROJECTS = "PROJECT_2002"
    PROJECT_ACCESS_DENIED = "PROJECT_2003"
    TASK_NOT_FOUND = "PROJECT_2004"
    DOCUMENT_NOT_FOUND = "PROJECT_2005"

    # Integration errors (3xxx)
    DATABASE_ERROR = "INTEGRATION_3001"
    PLANRADAR_API_ERROR = "INTEGRATION_3002"
    TWILIO_ERROR = "INTEGRATION_3003"
    TRANSLATION_ERROR = "INTEGRATION_3004"
    TRANSCRIPTION_ERROR = "INTEGRATION_3005"

    # Business logic errors (4xxx)
    INVALID_INTENT = "LOGIC_4001"
    HANDLER_NOT_FOUND = "LOGIC_4002"
    VALIDATION_ERROR = "LOGIC_4003"
    SESSION_ERROR = "LOGIC_4004"

    # System errors (5xxx)
    INTERNAL_ERROR = "SYSTEM_5001"
    TIMEOUT_ERROR = "SYSTEM_5002"
    CONFIGURATION_ERROR = "SYSTEM_5003"
    AGENT_ERROR = "SYSTEM_5004"
```

### Error Code Categories

| Range | Category | Purpose |
|-------|----------|---------|
| 1xxx | User/Auth | User-related errors |
| 2xxx | Resources | Project/task/document not found |
| 3xxx | Integrations | External API failures |
| 4xxx | Business Logic | Validation and logic errors |
| 5xxx | System | Internal system errors |

---

## Custom Exceptions

### Base Exception

All custom exceptions inherit from `LumieraException`:

```python
class LumieraException(Exception):
    """Base exception for all Lumiera application errors."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode,
        user_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        super().__init__(message)
        self.error_code = error_code
        self.user_message = user_message or "Une erreur s'est produite"
        self.details = details or {}
        self.original_exception = original_exception

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/API responses."""
        return {
            "success": False,
            "error_code": self.error_code.value,
            "message": str(self),
            "user_message": self.user_message,
            "details": self.details
        }
```

**Fields:**
- `message`: Technical error message (for logging)
- `error_code`: Standardized error code
- `user_message`: User-friendly message (translated to French by default)
- `details`: Additional error context (dict)
- `original_exception`: Wrapped exception if applicable

### Specific Exceptions

#### UserNotFoundException

```python
class UserNotFoundException(LumieraException):
    """Raised when user is not found in database."""

    def __init__(self, user_id: str, **kwargs):
        super().__init__(
            message=f"User not found: {user_id}",
            error_code=ErrorCode.USER_NOT_FOUND,
            user_message="Utilisateur non trouvé",
            details={"user_id": user_id},
            **kwargs
        )
```

**Usage:**
```python
user = await supabase_client.get_user_by_phone(phone_number)
if not user:
    raise UserNotFoundException(user_id=phone_number)
```

#### ProjectNotFoundException

```python
class ProjectNotFoundException(LumieraException):
    """Raised when project is not found or user has no access."""

    def __init__(self, project_id: Optional[str] = None, user_id: Optional[str] = None, **kwargs):
        super().__init__(
            message=f"Project not found: {project_id}" if project_id else "No projects found",
            error_code=ErrorCode.PROJECT_NOT_FOUND if project_id else ErrorCode.NO_PROJECTS,
            user_message="Projet non trouvé" if project_id else "Aucun projet trouvé",
            details={"project_id": project_id, "user_id": user_id},
            **kwargs
        )
```

**Usage:**
```python
projects = await get_user_projects(user_id)
if not projects:
    raise ProjectNotFoundException(user_id=user_id)
```

#### IntegrationException

```python
class IntegrationException(LumieraException):
    """Raised when external integration fails."""

    def __init__(self, service: str, operation: str, **kwargs):
        super().__init__(
            message=f"{service} integration error during {operation}",
            error_code=ErrorCode.DATABASE_ERROR,
            user_message=f"Erreur de connexion avec {service}",
            details={"service": service, "operation": operation},
            **kwargs
        )
```

**Subclasses:**
- `DatabaseException` - Database operation failure
- `PlanRadarException` - PlanRadar API failure

**Usage:**
```python
try:
    result = await planradar_api.create_ticket(...)
except Exception as e:
    raise PlanRadarException(
        operation="create_ticket",
        original_exception=e
    )
```

#### HandlerNotFoundException

```python
class HandlerNotFoundException(LumieraException):
    """Raised when no handler is found for intent."""

    def __init__(self, intent: str, **kwargs):
        super().__init__(
            message=f"No handler found for intent: {intent}",
            error_code=ErrorCode.HANDLER_NOT_FOUND,
            user_message="Action non reconnue",
            details={"intent": intent},
            **kwargs
        )
```

#### ValidationException

```python
class ValidationException(LumieraException):
    """Raised when input validation fails."""

    def __init__(self, field: str, reason: str, **kwargs):
        super().__init__(
            message=f"Validation error for {field}: {reason}",
            error_code=ErrorCode.VALIDATION_ERROR,
            user_message=f"Données invalides: {field}",
            details={"field": field, "reason": reason},
            **kwargs
        )
```

#### AgentExecutionException

```python
class AgentExecutionException(LumieraException):
    """Raised when agent execution fails."""

    def __init__(self, stage: str, **kwargs):
        super().__init__(
            message=f"Agent execution failed at stage: {stage}",
            error_code=ErrorCode.AGENT_ERROR,
            user_message="Erreur de traitement du message",
            details={"stage": stage},
            **kwargs
        )
```

---

## Result Wrapper

The `Result[T]` generic wrapper enables clean error propagation without throwing exceptions.

### Result Class

```python
@dataclass
class Result(Generic[T]):
    """Result wrapper for operations that can succeed or fail."""

    success: bool
    data: Optional[T] = None
    error_code: Optional[ErrorCode] = None
    error_message: Optional[str] = None
    user_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
```

### Creating Results

#### Success

```python
@staticmethod
def ok(data: T) -> 'Result[T]':
    """Create a successful result."""
    return Result(success=True, data=data)
```

**Usage:**
```python
user = await get_user_by_phone(phone)
return Result.ok(user)
```

#### Failure

```python
@staticmethod
def fail(
    error_code: ErrorCode,
    error_message: str,
    user_message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> 'Result[T]':
    """Create a failed result."""
    return Result(
        success=False,
        data=None,
        error_code=error_code,
        error_message=error_message,
        user_message=user_message or "Une erreur s'est produite",
        details=details or {}
    )
```

**Usage:**
```python
if not valid:
    return Result.fail(
        error_code=ErrorCode.VALIDATION_ERROR,
        error_message="Invalid phone number format",
        user_message="Numéro de téléphone invalide"
    )
```

#### From Exception

```python
@staticmethod
def from_exception(exc: Union[LumieraException, Exception]) -> 'Result[T]':
    """Create a failed result from an exception."""

    if isinstance(exc, LumieraException):
        return Result(
            success=False,
            data=None,
            error_code=exc.error_code,
            error_message=str(exc),
            user_message=exc.user_message,
            details=exc.details
        )
    else:
        return Result(
            success=False,
            data=None,
            error_code=ErrorCode.INTERNAL_ERROR,
            error_message=str(exc),
            user_message="Une erreur interne s'est produite",
            details={"exception_type": type(exc).__name__}
        )
```

**Usage:**
```python
try:
    user = await get_user_by_phone(phone)
    return Result.ok(user)
except LumieraException as e:
    return Result.from_exception(e)
except Exception as e:
    return Result.from_exception(e)
```

### Using Results

#### Unwrap (Unsafe)

```python
def unwrap(self) -> T:
    """Get data or raise exception if failed."""
    if not self.success:
        raise ValueError(f"Cannot unwrap failed result: {self.error_message}")
    return self.data
```

**Usage:**
```python
result = await get_user(user_id)
user = result.unwrap()  # Raises ValueError if failed
```

#### Unwrap Or (Safe)

```python
def unwrap_or(self, default: T) -> T:
    """Get data or return default if failed."""
    return self.data if self.success else default
```

**Usage:**
```python
result = await get_user(user_id)
user = result.unwrap_or(None)  # Returns None if failed
```

#### To Dict

```python
def to_dict(self) -> Dict[str, Any]:
    """Convert to dictionary for API responses."""
    if self.success:
        return {
            "success": True,
            "data": self.data
        }
    else:
        return {
            "success": False,
            "error_code": self.error_code.value if self.error_code else None,
            "error_message": self.error_message,
            "user_message": self.user_message,
            "details": self.details
        }
```

---

## Error Propagation Patterns

### Pipeline Stages

Each pipeline stage returns `Result[None]`:

```python
async def _authenticate_user(self, ctx: MessageContext) -> Result[None]:
    """Stage 1: Authenticate user by phone number."""

    try:
        user = await supabase_client.get_user_by_phone(ctx.from_number)
        if not user:
            raise UserNotFoundException(user_id=ctx.from_number)

        ctx.user_id = user['id']
        return Result.ok(None)

    except Exception as e:
        return Result.from_exception(e)
```

**Early Exit:**
```python
result = await self._authenticate_user(ctx)
if not result.success:
    return result  # Exit pipeline immediately
```

### Service Layer

Services return `Result[T]` with typed data:

```python
async def get_user_by_phone(self, phone: str) -> Result[Dict]:
    """Get user by phone number."""

    try:
        response = self.client.table("subcontractors")\
            .select("*")\
            .eq("contact_telephone", phone)\
            .single()\
            .execute()

        if not response.data:
            raise UserNotFoundException(user_id=phone)

        return Result.ok(response.data)

    except Exception as e:
        return Result.from_exception(e)
```

### Handler Layer

Handlers return `Optional[Dict]` for compatibility:

```python
async def handle_list_tasks(user_id, language, **kwargs) -> Optional[Dict]:
    """Handle list tasks intent."""

    try:
        projects_result = await get_projects_with_context(user_id, language)

        if not projects_result.success:
            return build_error_response(language, "no_projects")

        return {
            "message": format_tasks(...),
            "escalation": False,
            "tools_called": [],
            "fast_path": True
        }

    except Exception as e:
        log.error(f"Error in fast path list_tasks: {e}")
        return None  # Trigger fallback to full agent
```

---

## Error Handling Best Practices

### 1. Always Use Custom Exceptions

**❌ Bad:**
```python
if not user:
    raise Exception("User not found")
```

**✅ Good:**
```python
if not user:
    raise UserNotFoundException(user_id=phone_number)
```

### 2. Provide Context

**❌ Bad:**
```python
raise ValidationException("Invalid input", "Bad format")
```

**✅ Good:**
```python
raise ValidationException(
    field="phone_number",
    reason="Must start with +33",
    details={"provided": phone_number}
)
```

### 3. Use Result Wrapper

**❌ Bad:**
```python
async def get_user(user_id):
    user = await db.get(user_id)
    return user  # What if None? Exception?
```

**✅ Good:**
```python
async def get_user(user_id) -> Result[Dict]:
    try:
        user = await db.get(user_id)
        if not user:
            raise UserNotFoundException(user_id=user_id)
        return Result.ok(user)
    except Exception as e:
        return Result.from_exception(e)
```

### 4. Early Exit on Failures

**❌ Bad:**
```python
result = await operation()
# Continue processing even if failed
data = result.data  # Might be None!
```

**✅ Good:**
```python
result = await operation()
if not result.success:
    return result  # Exit early

# Safe to use result.data here
data = result.data
```

### 5. Log with Context

**❌ Bad:**
```python
except Exception as e:
    log.error(str(e))
```

**✅ Good:**
```python
except Exception as e:
    log.error(
        f"Failed to process message for user {user_id}",
        extra={
            "user_id": user_id,
            "message_sid": message_sid,
            "error_type": type(e).__name__,
            "error": str(e)
        }
    )
```

---

## Error Response Flow

### User-Facing Errors

1. **Error Occurs**:
```python
raise UserNotFoundException(user_id=phone_number)
```

2. **Converted to Result**:
```python
result = Result.from_exception(exc)
# success=False, error_code=USER_1001, user_message="Utilisateur non trouvé"
```

3. **Translated to User Language**:
```python
if user_language != "fr":
    error_msg = await translation_service.translate_from_french(
        result.user_message,
        user_language
    )
```

4. **Sent to User**:
```python
twilio_client.send_message(from_number, error_msg)
```

### Internal Errors

1. **Error Occurs**:
```python
try:
    result = await external_api.call()
except Exception as e:
    raise IntegrationException(
        service="ExternalAPI",
        operation="call",
        original_exception=e
    )
```

2. **Logged with Context**:
```python
log.error(
    f"Integration error: {exc.error_code.value}",
    extra={
        "error_code": exc.error_code.value,
        "service": exc.details.get("service"),
        "operation": exc.details.get("operation"),
        "original_error": str(exc.original_exception)
    }
)
```

3. **Generic Message to User**:
```python
result = Result.from_exception(exc)
# user_message = "Une erreur s'est produite" (generic)
```

---

## Testing Error Handling

### Test Custom Exceptions

```python
def test_user_not_found_exception():
    """Test UserNotFoundException structure."""
    exc = UserNotFoundException(user_id="123")

    assert exc.error_code == ErrorCode.USER_NOT_FOUND
    assert "123" in str(exc)
    assert exc.user_message == "Utilisateur non trouvé"
    assert exc.details["user_id"] == "123"
```

### Test Result Wrapper

```python
def test_result_ok():
    """Test successful result."""
    result = Result.ok({"id": "123", "name": "John"})

    assert result.success
    assert result.data["id"] == "123"
    assert result.error_code is None
```

```python
def test_result_fail():
    """Test failed result."""
    result = Result.fail(
        error_code=ErrorCode.USER_NOT_FOUND,
        error_message="User not found",
        user_message="Utilisateur non trouvé"
    )

    assert not result.success
    assert result.error_code == ErrorCode.USER_NOT_FOUND
    assert result.data is None
```

### Test Error Propagation

```python
async def test_pipeline_error_propagation():
    """Test error propagates through pipeline."""
    pipeline = MessagePipeline()

    result = await pipeline.process(
        from_number="+33999999999",  # Unknown user
        message_body="hello",
        message_sid="SM123"
    )

    assert not result.success
    assert result.error_code == ErrorCode.USER_NOT_FOUND
    assert "non trouvé" in result.user_message.lower()
```

---

## Monitoring & Alerting

### Error Metrics

Track error rates by code:

```sql
SELECT
    error_code,
    COUNT(*) as error_count,
    COUNT(DISTINCT user_id) as affected_users,
    DATE(created_at) as date
FROM error_logs
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY error_code, DATE(created_at)
ORDER BY error_count DESC;
```

### Alert Thresholds

- **USER_1001**: Alert if > 10/hour (possible phone number issue)
- **INTEGRATION_3xxx**: Alert immediately (external dependency)
- **SYSTEM_5xxx**: Alert immediately (critical system error)
- **Any error**: Alert if > 100/hour (possible incident)

### Error Dashboard

Monitor:
- Error rate by category (1xxx, 2xxx, etc.)
- Most common errors
- Error rate trend over time
- Affected users count
- Mean time to resolution

---

## Related Documentation

- [Pipeline Architecture](./PIPELINE_ARCHITECTURE.md) - How errors propagate through pipeline
- [Architecture Overview](./README.md) - System architecture
- [Design Decisions](../design-decisions/ARCHITECTURAL_REFACTORS.md) - Why we built this system
- [Security Best Practices](../security/BEST_PRACTICES.md) - Security error handling

---

**Last Updated**: 2026-01-05
**Version**: 2.0.0
