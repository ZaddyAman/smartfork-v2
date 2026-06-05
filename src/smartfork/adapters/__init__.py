"""SmartFork v2 — Multi-agent session format adapters."""

from smartfork.adapters.base import SessionAdapter
from smartfork.adapters.registry import (
    clear_registry,
    get_adapter,
    get_adapter_or_raise,
    is_registered,
    list_adapters,
    list_agent_ids,
    register,
)

__all__ = [
    # Base
    "SessionAdapter",
    # Registry
    "register",
    "get_adapter",
    "get_adapter_or_raise",
    "list_adapters",
    "list_agent_ids",
    "is_registered",
    "clear_registry",
    # Adapters
    "antigravity",
    "claudecode",
    "cline",
    "cursor_agent",
    "gemini",
    "kilocode",
    "opencode",
]

# Auto-register all adapters on import
from smartfork.adapters import (
    antigravity,  # noqa: F401
    claudecode,  # noqa: F401
    cline,  # noqa: F401
    cursor_agent,  # noqa: F401
    gemini,  # noqa: F401
    kilocode,  # noqa: F401
    opencode,  # noqa: F401
)
