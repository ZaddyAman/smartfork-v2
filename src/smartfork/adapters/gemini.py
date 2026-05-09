"""Gemini session adapter (placeholder)."""

from pathlib import Path

from smartfork.adapters.base import SessionAdapter
from smartfork.adapters.registry import register
from smartfork.models.session import RawSessionData


@register
class GeminiAdapter(SessionAdapter):
    """Placeholder adapter for Gemini CLI sessions.

    Gemini CLI is not yet supported. This adapter exists as a
    registration target for future implementation.
    """

    agent_id = "gemini"
    display_name = "Gemini"
    session_type = "dir"

    def is_valid_session(self, session_path: Path) -> bool:
        return False

    def get_session_files(self, session_path: Path) -> list[str]:
        return []

    def parse_raw(self, session_path: Path) -> RawSessionData | None:
        return None
