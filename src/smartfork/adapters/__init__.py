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
    "claudecode",
    "kilocode",
    "opencode",
]

# Auto-register all adapters on import
from smartfork.adapters import (
    claudecode,  # noqa: F401
    kilocode,  # noqa: F401
    opencode,  # noqa: F401
)
