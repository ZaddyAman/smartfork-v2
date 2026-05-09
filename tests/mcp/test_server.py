"""Tests for MCP server."""

from smartfork.mcp.server import SmartForkMCPServer


class TestSmartForkMCPServer:
    def test_init(self) -> None:
        server = SmartForkMCPServer()
        assert server.is_running is False

    def test_start_stop(self) -> None:
        server = SmartForkMCPServer()
        server.start()
        assert server.is_running is True
        server.stop()
        assert server.is_running is False

    def test_detect_fork(self) -> None:
        server = SmartForkMCPServer()
        result = server.detect_fork("fix auth bug")
        assert "session_id" in result
        assert result["match_score"] == 0.95

    def test_fork_session(self) -> None:
        server = SmartForkMCPServer()
        result = server.fork_session("sess-1", "debug")
        assert "Handoff" in result

    def test_index_status(self) -> None:
        server = SmartForkMCPServer()
        status = server.index_status()
        assert "total_sessions" in status

    def test_search_sessions(self) -> None:
        server = SmartForkMCPServer()
        results = server.search_sessions("test")
        assert isinstance(results, list)

    def test_list_projects(self) -> None:
        server = SmartForkMCPServer()
        projects = server.list_projects()
        assert isinstance(projects, list)

    def test_vault_export(self) -> None:
        server = SmartForkMCPServer()
        path = server.vault_export("/tmp/vault")
        assert path == "/tmp/vault"
