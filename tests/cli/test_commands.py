"""Tests for SmartFork v2 CLI commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from smartfork.cli.commands import app


@pytest.fixture
def runner() -> CliRunner:
    """Provide a CliRunner instance for CLI tests."""
    return CliRunner()


class TestSetupCommand:
    def test_full_wizard(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["setup"])
        assert result.exit_code == 0
        assert "Detecting installed coding agents" in result.output
        assert "Setup complete!" in result.output


class TestIndexCommand:
    @patch("smartfork.indexer.indexer.FullIndexer")
    @patch("smartfork.cli.display.IndexDisplay")
    def test_full_index(self, mock_display, mock_indexer_cls, runner: CliRunner) -> None:
        mock_indexer = mock_indexer_cls.return_value
        mock_indexer.index_all.return_value = {"scanned": 1, "parsed": 1, "chunked": 10, "stored": 10, "errors": 0}
        
        result = runner.invoke(app, ["index", "--full"])
        assert result.exit_code == 0
        assert "Indexing Summary" in result.output
        assert "Indexing complete" in result.output

    @patch("smartfork.indexer.indexer.FullIndexer")
    @patch("smartfork.cli.display.IndexDisplay")
    def test_incremental_index(self, mock_display, mock_indexer_cls, runner: CliRunner) -> None:
        mock_indexer = mock_indexer_cls.return_value
        mock_indexer.index_incremental.return_value = {"scanned": 1, "parsed": 1, "chunked": 10, "stored": 10, "errors": 0}
        
        result = runner.invoke(app, ["index"])
        assert result.exit_code == 0
        assert "Indexing Summary" in result.output
        assert "Indexing complete" in result.output

    @patch("smartfork.indexer.indexer.FullIndexer")
    @patch("smartfork.cli.display.IndexDisplay")
    def test_no_embeddings_stored(self, mock_display, mock_indexer_cls, runner: CliRunner) -> None:
        mock_indexer = mock_indexer_cls.return_value
        mock_indexer.index_all.return_value = {"scanned": 1, "parsed": 1, "chunked": 10, "stored": 0, "errors": 0}
        
        result = runner.invoke(app, ["index", "--full"])
        assert result.exit_code == 0
        assert "0 stored as embeddings" in result.output


class TestSearchCommand:
    @patch("smartfork.search.deterministic.DeterministicSearchEngine")
    def test_basic_search(self, mock_engine_cls, runner: CliRunner) -> None:
        from smartfork.models.search import ResultCard
        mock_engine = mock_engine_cls.return_value
        mock_engine.search.return_value = [
            ResultCard(
                rank=1, session_id="sess-123", title="Fix auth bug", project_name="auth-service",
                match_score=0.95, time_ago="2 days ago", excerpt="Fixed the login flow."
            )
        ]
        result = runner.invoke(app, ["search", "auth bug"])
        assert result.exit_code == 0
        assert "Fix auth bug" in result.output
        assert "auth-service" in result.output

    @patch("smartfork.search.deterministic.DeterministicSearchEngine")
    def test_no_results(self, mock_engine_cls, runner: CliRunner) -> None:
        mock_engine = mock_engine_cls.return_value
        mock_engine.search.return_value = []
        result = runner.invoke(app, ["search", "auth bug"])
        assert result.exit_code == 0
        assert "No results found" in result.output


class TestForkCommand:
    @patch("smartfork.indexer.metadata_store.MetadataStore")
    @patch("smartfork.fork.assembler.ForkAssembler")
    @patch("smartfork.fork.assembler.ForkExporter")
    def test_fork_continue(self, mock_exporter, mock_assembler_cls, mock_store_cls, runner: CliRunner) -> None:
        mock_store = mock_store_cls.return_value
        mock_store.get_session.return_value = {"session_id": "sess-123", "agent": "claudecode", "project_name": "test"}
        
        mock_assembler = mock_assembler_cls.return_value
        mock_assembler.assemble.return_value = "Handoff content"
        
        result = runner.invoke(app, ["fork", "sess-123"])
        assert result.exit_code == 0
        assert "Generating" in result.output

    @patch("smartfork.indexer.metadata_store.MetadataStore")
    def test_fork_invalid_session(self, mock_store_cls, runner: CliRunner) -> None:
        mock_store = mock_store_cls.return_value
        mock_store.get_session.return_value = None
        
        result = runner.invoke(app, ["fork", "invalid-123"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestStatusCommand:
    @patch("smartfork.indexer.metadata_store.MetadataStore")
    def test_basic_status(self, mock_store_cls, runner: CliRunner) -> None:
        mock_store = mock_store_cls.return_value
        mock_store.get_stats.return_value = {
            "total_sessions": 10,
            "by_agent": {"claudecode": 10},
            "by_project": {"test": 10},
            "by_quality": {"high": 5, "medium": 5}
        }
        
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Sessions" in result.output
        assert "claudecode 10" in result.output
        assert "Quality" in result.output


class TestConfigCommand:
    def test_get_value(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["config", "get", "theme"])
        assert result.exit_code == 0
        assert "theme =" in result.output

    def test_set_value(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["config", "set", "theme", "ember"])
        assert result.exit_code == 0
        assert "Set theme = ember" in result.output

    def test_list_all(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "Configuration" in result.output
        assert "theme" in result.output
        assert "llm_provider" in result.output

    @patch("smartfork.config.reload_config")
    @patch("smartfork.config.CONFIG_FILE")
    def test_reset(self, mock_config_file, mock_reload, runner: CliRunner) -> None:
        mock_config_file.exists.return_value = True
        result = runner.invoke(app, ["config", "reset"])
        assert result.exit_code == 0
        assert "reset" in result.output.lower()


class TestThemeCommand:
    def test_list_themes(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["theme", "list"])
        assert result.exit_code == 0
        assert "obsidian" in result.output
        assert "phosphor" in result.output

    def test_switch_theme(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["theme", "switch", "ember"])
        assert result.exit_code == 0
        assert "Switched to theme: ember" in result.output

    def test_invalid_theme(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["theme", "switch", "invalid"])
        assert result.exit_code == 0
        assert "Unknown theme" in result.output


class TestVaultCommand:
    @patch("smartfork.indexer.metadata_store.MetadataStore")
    @patch("smartfork.vault.obsidian.ObsidianVaultGenerator")
    def test_generate_vault(self, mock_gen_cls, mock_store_cls, runner: CliRunner) -> None:
        mock_store = mock_store_cls.return_value
        mock_store.get_filtered_ids.return_value = ["sess-123"]
        mock_store.get_session.return_value = {
            "session_id": "sess-123", "agent": "claudecode", "project_name": "test"
        }
        
        mock_gen = mock_gen_cls.return_value
        mock_gen.generate.return_value = "/path/to/vault"
        
        result = runner.invoke(app, ["vault"])
        assert result.exit_code == 0
        assert "Vault created at: /path/to/vault" in result.output


class TestMcpCommand:
    def test_status(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["mcp", "status"])
        assert result.exit_code == 0
        assert "MCP" in result.output

    @patch("smartfork.mcp.server.SmartForkMCPServer")
    def test_serve(self, mock_server_cls, runner: CliRunner) -> None:
        mock_server = mock_server_cls.return_value
        mock_server.is_running = False
        result = runner.invoke(app, ["mcp", "serve"])
        assert result.exit_code == 0
        assert "running" in result.output.lower()
