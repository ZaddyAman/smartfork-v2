"""Cline session adapter (placeholder)."""

from pathlib import Path

from smartfork.adapters.base import SessionAdapter
from smartfork.adapters.registry import register
from smartfork.models.session import RawSessionData


@register
class ClineAdapter(SessionAdapter):
    """Placeholder adapter for Cline sessions.

    Cline is not yet supported. This adapter exists as a
    registration target for future implementation.
    """

    agent_id = "cline"
    display_name = "Cline"
    session_type = "dir"

    def is_valid_session(self, session_path: Path) -> bool:
        return False

    def get_session_files(self, session_path: Path) -> list[str]:
        return []

    def parse_raw(self, session_path: Path) -> RawSessionData | None:
        return None
