"""MCP server for SmartFork v2 — Claude Code integration."""

from loguru import logger


class SmartForkMCPServer:
    """Model Context Protocol server for SmartFork v2.

    Exposes session intelligence tools to Claude Code and other
    MCP-compatible AI coding agents.

    Tools exposed:
    - detect_fork: Find the best session to fork from
    - fork_session: Generate fork context from a session
    - index_status: Get indexing statistics
    - search_sessions: Search indexed sessions
    - get_session: Get full session details
    - list_projects: List all indexed projects
    - config_get: Read configuration values (read-only)
    - vault_export: Export session data as Obsidian vault
    """

    def __init__(self) -> None:
        self._running = False

    def start(self) -> None:
        """Start the MCP server on stdio transport."""
        self._running = True
        logger.info("MCP server started on stdio")

    def stop(self) -> None:
        """Stop the MCP server."""
        self._running = False
        logger.info("MCP server stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def detect_fork(self, query: str) -> dict[str, object]:
        """Detect the best session to fork from.

        Args:
            query: What the user wants to do next.

        Returns:
            Dict with session_id, title, match_score, and fork_command.
        """
        return {
            "session_id": "example-123",
            "title": "Fix authentication bug",
            "match_score": 0.95,
            "fork_command": "smartfork fork example-123",
        }

    def fork_session(self, session_id: str, intent: str = "continue") -> str:
        """Generate fork context from a session.

        Args:
            session_id: The session to fork from.
            intent: Fork intent (continue, reference, debug, synthesize).

        Returns:
            Markdown handoff document.
        """
        return f"# Handoff: {session_id}\n\nFork intent: {intent}\n"

    def index_status(self) -> dict[str, object]:
        """Get indexing statistics.

        Returns:
            Dict with total_sessions, indexed_chunks, by_project, by_agent.
        """
        return {
            "total_sessions": 0,
            "indexed_chunks": 0,
            "by_project": {},
            "by_agent": {},
        }

    def search_sessions(self, query: str, top_k: int = 5) -> list[dict[str, object]]:
        """Search indexed sessions.

        Args:
            query: Search query.
            top_k: Number of results.

        Returns:
            List of search result dicts.
        """
        return []

    def get_session(self, session_id: str) -> dict[str, object] | None:
        """Get full session details.

        Args:
            session_id: Session identifier.

        Returns:
            Session data dict or None.
        """
        return None

    def list_projects(self) -> list[str]:
        """List all indexed projects.

        Returns:
            List of project names.
        """
        return []

    def config_get(self, key: str) -> str | None:
        """Read a configuration value (read-only).

        Args:
            key: Configuration key.

        Returns:
            Config value or None.
        """
        return None

    def vault_export(self, output_dir: str = "./smartfork_vault") -> str:
        """Export session data as an Obsidian vault.

        Args:
            output_dir: Output directory.

        Returns:
            Path to the generated vault.
        """
        return output_dir
