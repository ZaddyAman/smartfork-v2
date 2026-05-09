"""Adapter registry for SmartFork v2."""

from __future__ import annotations

from loguru import logger

from smartfork.adapters.base import SessionAdapter

# Global registry of adapter instances, keyed by agent_id
_REGISTRY: dict[str, SessionAdapter] = {}


def register(cls: type) -> type:
    """Decorator that auto-registers an adapter class on definition.

    Instantiate the adapter class and store it in the registry
    keyed by its agent_id attribute.

    Args:
        cls: The adapter class to register.

    Returns:
        The same class (unmodified), for decorator chaining.

    Raises:
        ValueError: If the class has no agent_id or it's empty.
    """
    if not issubclass(cls, SessionAdapter):
        raise TypeError(
            f"@register can only be used on SessionAdapter subclasses, got {cls.__name__}"
        )

    instance = cls()
    agent_id = instance.agent_id

    if not agent_id:
        raise ValueError(
            f"Adapter class {cls.__name__} must define a non-empty agent_id "
            "class attribute."
        )

    if agent_id in _REGISTRY:
        existing = _REGISTRY[agent_id].__class__.__name__
        logger.warning(
            f"Adapter for '{agent_id}' is already registered ({existing}). "
            f"Overwriting with {cls.__name__}."
        )

    _REGISTRY[agent_id] = instance
    logger.debug(f"Registered adapter: {agent_id} ({cls.__name__})")
    return cls


def get_adapter(agent_id: str) -> SessionAdapter | None:
    """Get a registered adapter by agent ID.

    Args:
        agent_id: The agent identifier (e.g., "kilocode", "claudecode").

    Returns:
        The SessionAdapter instance, or None if not registered.
    """
    return _REGISTRY.get(agent_id)


def get_adapter_or_raise(agent_id: str) -> SessionAdapter:
    """Get a registered adapter, raising if not found.

    Args:
        agent_id: The agent identifier.

    Returns:
        The SessionAdapter instance.

    Raises:
        KeyError: If no adapter is registered for this agent_id.
    """
    if agent_id not in _REGISTRY:
        raise KeyError(
            f"No adapter registered for agent '{agent_id}'. "
            f"Available: {', '.join(sorted(_REGISTRY.keys())) or 'none'}"
        )
    return _REGISTRY[agent_id]


def list_adapters() -> list[SessionAdapter]:
    """Return all registered adapter instances.

    Returns:
        List of SessionAdapter instances.
    """
    return list(_REGISTRY.values())


def list_agent_ids() -> list[str]:
    """Return all registered agent IDs.

    Returns:
        Sorted list of agent ID strings.
    """
    return sorted(_REGISTRY.keys())


def is_registered(agent_id: str) -> bool:
    """Check if an adapter is registered for the given agent ID.

    Args:
        agent_id: The agent identifier to check.

    Returns:
        True if an adapter is registered, False otherwise.
    """
    return agent_id in _REGISTRY


def clear_registry() -> None:
    """Clear all registered adapters. Useful for testing."""
    _REGISTRY.clear()
