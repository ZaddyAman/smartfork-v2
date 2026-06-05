"""Base adapter classes for SmartFork v2."""

from abc import ABC, abstractmethod
from pathlib import Path

from smartfork.models.session import RawSessionData


class SessionAdapter(ABC):
    """Abstract base class for agent-specific session parsers.

    Each coding agent (Kilo Code, Claude Code, OpenCode, etc.) has
    its own adapter that knows how to find and parse its session files.
    Subclasses must implement is_valid_session(), get_session_files(),
    and parse_raw().
    """

    agent_id: str = ""
    display_name: str = ""
    session_type: str = ""  # "dir" | "file" | "sqlite"

    @abstractmethod
    def is_valid_session(self, session_path: Path) -> bool:
        """Check if a path contains a valid session of this agent's format.

        Args:
            session_path: Path to a potential session directory or file.

        Returns:
            True if this path contains a valid session for this agent.
        """
        ...

    @abstractmethod
    def get_session_files(self, session_path: Path) -> list[str]:
        """Get the list of files belonging to this session.

        Args:
            session_path: Path to the session.

        Returns:
            List of file paths relative to the session path.
        """
        ...

    @abstractmethod
    def parse_raw(self, session_path: Path) -> RawSessionData | None:
        """Parse a session into agent-agnostic RawSessionData.

        Args:
            session_path: Path to the session directory or file.

        Returns:
            RawSessionData if parsing succeeded, None otherwise.
        """
        ...

    def get_default_sessions_paths(self) -> list[Path]:
        """Return the default search paths where this agent stores sessions.

        Returns:
            List of directory or file paths where sessions may be found.
        """
        return []

    def get_ide_choices(self) -> list[str]:
        """Return the list of IDE names this agent can identify.

        Returns:
            List of IDE name strings.
        """
        return []

    def get_default_path_for_ide(self, ide: str) -> Path | None:
        """Get the default session path for a specific IDE.

        Args:
            ide: The IDE name.

        Returns:
            Path to sessions directory for this IDE, or None.
        """
        return None
