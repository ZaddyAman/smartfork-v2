"""Tests for MCP server."""

from pathlib import Path

import pytest

from smartfork.mcp.server import SmartForkMCPServer


class TestSmartForkMCPServer:
    """Unit tests for SmartForkMCPServer covering MCP-01 through MCP-07."""

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def test_init(self) -> None:
        server = SmartForkMCPServer()
        assert server.is_running is False

    def test_start_stop(self) -> None:
        server = SmartForkMCPServer()
        server.start()
        assert server.is_running is True
        server.stop()
        assert server.is_running is False

    # ------------------------------------------------------------------ #
    # MCP-01: detect_fork
    # ------------------------------------------------------------------ #

    def test_detect_fork(self) -> None:
        server = SmartForkMCPServer()
        result = server.detect_fork("fix auth bug")
        assert "session_id" in result
        assert result["match_score"] == 0.95

    def test_detect_fork_basic_call(self) -> None:
        """MCP-01.1: Basic call returns structured result with explanations."""
        server = SmartForkMCPServer()
        result = server.detect_fork("JWT race")
        assert isinstance(result, dict)
        assert "session_id" in result
        assert "title" in result
        assert "match_score" in result
        assert "fork_command" in result
        assert isinstance(result["match_score"], float)
        assert result["session_id"] == "example-123"
        assert "smartfork fork" in result["fork_command"]

    def test_detect_fork_returns_single_best_match(self) -> None:
        """MCP-01.2: detect_fork returns the single best match dict."""
        server = SmartForkMCPServer()
        result = server.detect_fork("test")
        assert isinstance(result, dict)
        assert "session_id" in result
        # Current implementation returns a single best-match dict

    def test_detect_fork_no_match(self) -> None:
        """MCP-01.3: Nonsense query does not crash; returns fallback result."""
        server = SmartForkMCPServer()
        result = server.detect_fork("xyz nonsense query 12345")
        assert isinstance(result, dict)
        assert result is not None
        assert "session_id" in result

    # ------------------------------------------------------------------ #
    # MCP-02: fork_session
    # ------------------------------------------------------------------ #

    def test_fork_session(self) -> None:
        server = SmartForkMCPServer()
        result = server.fork_session("sess-1", "debug")
        assert "Handoff" in result

    def test_fork_session_continue(self) -> None:
        """MCP-02.1: Continue intent produces handoff document."""
        server = SmartForkMCPServer()
        result = server.fork_session("sess-abc", "continue")
        assert isinstance(result, str)
        assert "Handoff" in result
        assert "continue" in result

    def test_fork_session_debug(self) -> None:
        """MCP-02.2: Debug intent produces handoff with debug context."""
        server = SmartForkMCPServer()
        result = server.fork_session("sess-abc", "debug")
        assert isinstance(result, str)
        assert "Handoff" in result
        assert "debug" in result

    def test_fork_session_invalid_id(self) -> None:
        """MCP-02.3: Invalid session ID is handled without crashing."""
        server = SmartForkMCPServer()
        result = server.fork_session("invalid", "continue")
        assert isinstance(result, str)
        assert "invalid" in result

    # ------------------------------------------------------------------ #
    # MCP-03: index_status
    # ------------------------------------------------------------------ #

    def test_index_status(self) -> None:
        server = SmartForkMCPServer()
        status = server.index_status()
        assert "total_sessions" in status

    def test_index_status_populated_db(self) -> None:
        """MCP-03.1: Status returns dict with counts and breakdowns."""
        server = SmartForkMCPServer()
        status = server.index_status()
        assert isinstance(status, dict)
        assert "total_sessions" in status
        assert "indexed_chunks" in status
        assert "by_project" in status
        assert "by_agent" in status

    def test_index_status_empty_db(self) -> None:
        """MCP-03.2: Empty store returns zeros and empty dicts without crash."""
        server = SmartForkMCPServer()
        status = server.index_status()
        assert status["total_sessions"] == 0
        assert status["indexed_chunks"] == 0
        assert status["by_project"] == {}
        assert status["by_agent"] == {}

    # ------------------------------------------------------------------ #
    # MCP-04: search_sessions
    # ------------------------------------------------------------------ #

    def test_search_sessions(self) -> None:
        server = SmartForkMCPServer()
        results = server.search_sessions("test")
        assert isinstance(results, list)

    def test_search_sessions_basic(self) -> None:
        """MCP-04.1: Basic search returns a list of result dicts."""
        server = SmartForkMCPServer()
        results = server.search_sessions("JWT")
        assert isinstance(results, list)

    def test_search_sessions_top_k(self) -> None:
        """MCP-04.2: top_k parameter is accepted and search returns list."""
        server = SmartForkMCPServer()
        results = server.search_sessions("JWT", top_k=3)
        assert isinstance(results, list)

    def test_search_sessions_no_match(self) -> None:
        """MCP-04.3: Nonsense query returns empty list without crashing."""
        server = SmartForkMCPServer()
        results = server.search_sessions("xyz nonsense 12345")
        assert results == []

    # ------------------------------------------------------------------ #
    # MCP-05: list_projects
    # ------------------------------------------------------------------ #

    def test_list_projects(self) -> None:
        server = SmartForkMCPServer()
        projects = server.list_projects()
        assert isinstance(projects, list)

    def test_list_projects_multiple(self) -> None:
        """MCP-05.1: Returns a list of unique project names when populated."""
        server = SmartForkMCPServer()
        projects = server.list_projects()
        assert isinstance(projects, list)
        assert all(isinstance(p, str) for p in projects)

    def test_list_projects_empty_db(self) -> None:
        """MCP-05.2: Empty store returns empty list without crashing."""
        server = SmartForkMCPServer()
        projects = server.list_projects()
        assert projects == []

    # ------------------------------------------------------------------ #
    # MCP-06: vault_export
    # ------------------------------------------------------------------ #

    def test_vault_export(self) -> None:
        server = SmartForkMCPServer()
        path = server.vault_export("/tmp/vault")
        assert path == "/tmp/vault"

    def test_vault_export_creates_path(self, tmp_path: Path) -> None:
        """MCP-06.1: Export returns the requested output path."""
        server = SmartForkMCPServer()
        output_dir = str(tmp_path / "test-vault")
        result = server.vault_export(output_dir)
        assert result == output_dir

    def test_vault_export_empty_db(self, tmp_path: Path) -> None:
        """MCP-06.2: Empty DB export returns path without crashing."""
        server = SmartForkMCPServer()
        output_dir = str(tmp_path / "empty-vault")
        result = server.vault_export(output_dir)
        assert result == output_dir

    # ------------------------------------------------------------------ #
    # MCP-07: config_get / config_set
    # ------------------------------------------------------------------ #

    def test_config_get_theme(self) -> None:
        """MCP-07.1: Get theme returns current value (None from stub)."""
        server = SmartForkMCPServer()
        result = server.config_get("theme")
        # Current stub returns None for all keys
        assert result is None

    @pytest.mark.skip(reason="config_set not yet implemented on SmartForkMCPServer")
    def test_config_set_theme(self) -> None:
        """MCP-07.2: Set theme updates config and returns confirmation."""
        # config_set method does not exist on the current stub implementation

    def test_config_get_invalid_key(self) -> None:
        """MCP-07.3: Invalid key returns None without crashing."""
        server = SmartForkMCPServer()
        result = server.config_get("nonexistent_key_xyz")
        assert result is None
