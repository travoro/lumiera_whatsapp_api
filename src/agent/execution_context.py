"""Thread-safe execution context for agent tool execution tracking.

This module provides a thread-safe way to track escalations and tool calls
during agent execution, replacing the global mutable state pattern.
"""
from contextvars import ContextVar
from typing import Dict, List, Any
from dataclasses import dataclass, field
from contextlib import contextmanager


@dataclass
class ExecutionContext:
    """Execution context for tracking agent tool usage."""

    escalation_occurred: bool = False
    tools_called: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def reset(self) -> None:
        """Reset context for new execution."""
        self.escalation_occurred = False
        self.tools_called = []
        self.metadata = {}

    def record_tool_call(self, tool_name: str) -> None:
        """Record that a tool was called."""
        if tool_name not in self.tools_called:
            self.tools_called.append(tool_name)

    def record_escalation(self) -> None:
        """Record that escalation occurred."""
        self.escalation_occurred = True
        self.record_tool_call("escalate_to_human_tool")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "escalation_occurred": self.escalation_occurred,
            "tools_called": self.tools_called,
            "metadata": self.metadata
        }


# Thread-local context variable
_execution_context: ContextVar[ExecutionContext] = ContextVar(
    'execution_context',
    default=ExecutionContext()
)


def get_execution_context() -> ExecutionContext:
    """Get the current execution context (thread-safe)."""
    return _execution_context.get()


def set_execution_context(context: ExecutionContext) -> None:
    """Set the execution context for current thread."""
    _execution_context.set(context)


@contextmanager
def execution_context_scope():
    """Context manager for agent execution with automatic cleanup.

    Usage:
        with execution_context_scope() as ctx:
            # Execute agent
            result = await agent.invoke(...)
            # Check ctx for escalations, tools_called
    """
    ctx = ExecutionContext()
    token = _execution_context.set(ctx)
    try:
        yield ctx
    finally:
        _execution_context.reset(token)


# Backward compatibility: global dict that proxies to context
class _ExecutionContextProxy:
    """Backward compatibility proxy for global execution_context dict."""

    def __getitem__(self, key: str) -> Any:
        ctx = get_execution_context()
        if key == "escalation_occurred":
            return ctx.escalation_occurred
        elif key == "tools_called":
            return ctx.tools_called
        else:
            return ctx.metadata.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        ctx = get_execution_context()
        if key == "escalation_occurred":
            ctx.escalation_occurred = value
        elif key == "tools_called":
            ctx.tools_called = value
        else:
            ctx.metadata[key] = value

    def get(self, key: str, default=None) -> Any:
        try:
            return self[key]
        except (KeyError, AttributeError):
            return default


# Global proxy for backward compatibility
execution_context = _ExecutionContextProxy()
