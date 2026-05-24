"""Tests for SmartFork v2 CLI commands."""

from __future__ import annotations

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
        mock_indexer.index_all.return_value = {
            "scanned": 1,
            "parsed": 1,
            "chunked": 10,
            "stored": 10,
            "errors": 0,
        }

        result = runner.invoke(app, ["index", "--full"])
        assert result.exit_code == 0
        assert "Indexing Summary" in result.output
        assert "Indexing complete" in result.output

    @patch("smartfork.indexer.indexer.FullIndexer")
    @patch("smartfork.cli.display.IndexDisplay")
    def test_incremental_index(self, mock_display, mock_indexer_cls, runner: CliRunner) -> None:
        mock_indexer = mock_indexer_cls.return_value
        mock_indexer.index_incremental.return_value = {
            "scanned": 1,
            "parsed": 1,
            "chunked": 10,
            "stored": 10,
            "errors": 0,
        }

        result = runner.invoke(app, ["index"])
        assert result.exit_code == 0
        assert "Indexing Summary" in result.output
        assert "Indexing complete" in result.output

    @patch("smartfork.indexer.indexer.FullIndexer")
    @patch("smartfork.cli.display.IndexDisplay")
    def test_no_embeddings_stored(self, mock_display, mock_indexer_cls, runner: CliRunner) -> None:
        mock_indexer = mock_indexer_cls.return_value
        mock_indexer.index_all.return_value = {
            "scanned": 1,
            "parsed": 1,
            "stored": 0,
            "errors": 0,
        }

        result = runner.invoke(app, ["index", "--full"])
        assert result.exit_code == 0
        assert "0 vectors stored" in result.output

    @patch("smartfork.indexer.intelligence.IndexIntelligence")
    @patch("smartfork.providers.get_llm")
    @patch("smartfork.indexer.indexer.FullIndexer")
    @patch("smartfork.cli.display.IndexDisplay")
    def test_index_with_enrich_flag(
        self,
        mock_display: MagicMock,
        mock_indexer_cls: MagicMock,
        mock_get_llm: MagicMock,
        mock_intelligence_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        mock_get_llm.return_value = MagicMock()
        mock_indexer = mock_indexer_cls.return_value
        mock_indexer.index_all.return_value = {
            "scanned": 1,
            "parsed": 1,
            "chunked": 10,
            "stored": 10,
            "errors": 0,
        }

        result = runner.invoke(app, ["index", "--full", "--enrich"])
        assert result.exit_code == 0
        assert "Indexing Summary" in result.output

        mock_get_llm.assert_called_once()
        mock_intelligence_cls.assert_called_once()
        _, kwargs = mock_intelligence_cls.call_args
        assert kwargs.get("llm") is not None

    @patch("smartfork.indexer.intelligence.IndexIntelligence")
    @patch("smartfork.providers.get_llm")
    @patch("smartfork.indexer.indexer.FullIndexer")
    @patch("smartfork.cli.display.IndexDisplay")
    def test_index_without_enrich_flag(
        self,
        mock_display: MagicMock,
        mock_indexer_cls: MagicMock,
        mock_get_llm: MagicMock,
        mock_intelligence_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        mock_indexer = mock_indexer_cls.return_value
        mock_indexer.index_all.return_value = {
            "scanned": 1,
            "parsed": 1,
            "chunked": 10,
            "stored": 10,
            "errors": 0,
        }

        result = runner.invoke(app, ["index", "--full"])
        assert result.exit_code == 0
        assert "Indexing Summary" in result.output

        mock_get_llm.assert_not_called()
        mock_intelligence_cls.assert_called_once()
        _, kwargs = mock_intelligence_cls.call_args
        assert kwargs.get("llm") is None


class TestSearchCommand:
    @patch("smartfork.search.orchestrator.SearchOrchestrator")
    @patch("smartfork.providers.get_llm")
    @patch("smartfork.providers.helpers.check_ollama_available")
    def test_basic_search(
        self, mock_check, mock_get_llm, mock_orchestrator_cls, runner: CliRunner
    ) -> None:
        from smartfork.models.search import ResultCard

        mock_check.return_value = True
        mock_orchestrator = mock_orchestrator_cls.return_value
        mock_orchestrator.search.return_value = [
            ResultCard(
                rank=1,
                session_id="sess-123",
                title="Fix auth bug",
                project_name="auth-service",
                match_score=0.95,
                time_ago="2 days ago",
                excerpt="Fixed the login flow.",
                tags=["python", "auth"],
                files_summary="3 files edited",
                fork_command="smartfork fork sess-123",
            )
        ]
        result = runner.invoke(app, ["search", "auth bug"])
        assert result.exit_code == 0
        assert "Fix auth bug" in result.output
        assert "auth-service" in result.output
        assert "default (interpret + deterministic search)" in result.output

    @patch("smartfork.search.orchestrator.SearchOrchestrator")
    @patch("smartfork.providers.get_llm")
    @patch("smartfork.providers.helpers.check_ollama_available")
    def test_no_results(
        self, mock_check, mock_get_llm, mock_orchestrator_cls, runner: CliRunner
    ) -> None:
        mock_check.return_value = True
        mock_orchestrator = mock_orchestrator_cls.return_value
        mock_orchestrator.search.return_value = []
        result = runner.invoke(app, ["search", "auth bug"])
        assert result.exit_code == 0
        assert "No relevant sessions found" in result.output

    @patch("smartfork.search.deterministic.DeterministicSearchEngine")
    def test_fast_flag(self, mock_engine_cls, runner: CliRunner) -> None:
        from smartfork.models.search import ResultCard

        mock_engine = mock_engine_cls.return_value
        mock_engine.search.return_value = [
            ResultCard(
                rank=1,
                session_id="sess-456",
                title="Fast result",
                project_name="fast-project",
                match_score=0.85,
                time_ago="1 day ago",
                excerpt="Fast path result.",
                tags=["fast"],
                files_summary="1 file edited",
                fork_command="smartfork fork sess-456",
            )
        ]
        result = runner.invoke(app, ["search", "--fast", "fast query"])
        assert result.exit_code == 0
        assert "Fast result" in result.output
        assert "fast-project" in result.output
        assert "deterministic" in result.output

    @patch("smartfork.providers.llm.get_llm")
    def test_llm_failure_suggests_fast(self, mock_get_llm, runner: CliRunner) -> None:
        mock_get_llm.side_effect = RuntimeError("Ollama not available")
        result = runner.invoke(app, ["search", "auth bug"])
        assert result.exit_code == 1
        assert "LLM setup failed" in result.output
        assert "--fast" in result.output

    @patch("smartfork.search.orchestrator.SearchOrchestrator")
    @patch("smartfork.providers.get_llm")
    @patch("smartfork.providers.helpers.check_ollama_available")
    def test_empty_results_shows_reasoning(
        self, mock_check, mock_get_llm, mock_orchestrator_cls, runner: CliRunner
    ) -> None:
        mock_check.return_value = True
        mock_orchestrator = mock_orchestrator_cls.return_value
        mock_orchestrator.search.return_value = []
        mock_orchestrator.last_empty_reasoning = (
            "Reviewed 3 candidates but none matched. s1: not relevant"
        )
        result = runner.invoke(app, ["search", "auth bug"])
        assert result.exit_code == 0
        assert "No relevant sessions found" in result.output
        assert "Reviewed 3 candidates" in result.output

    @patch("smartfork.search.orchestrator.SearchOrchestrator")
    @patch("smartfork.providers.get_llm")
    @patch("smartfork.providers.helpers.check_ollama_available")
    def test_card_display_format(
        self, mock_check, mock_get_llm, mock_orchestrator_cls, runner: CliRunner
    ) -> None:
        from smartfork.models.search import ResultCard

        mock_check.return_value = True
        mock_orchestrator = mock_orchestrator_cls.return_value
        mock_orchestrator.search.return_value = [
            ResultCard(
                rank=1,
                session_id="sess-789",
                title="Card Title",
                project_name="my-project",
                match_score=0.92,
                time_ago="3 hours ago",
                excerpt="Query-aware excerpt here.",
                quality_badge="[green]Strong match[/green]",
                tags=["python", "api"],
                files_summary="5 files edited",
                fork_command="smartfork fork sess-789",
            )
        ]
        result = runner.invoke(app, ["search", "card test"])
        assert result.exit_code == 0
        assert "Card Title" in result.output
        assert "my-project" in result.output
        assert "3 hours ago" in result.output
        assert "Query-aware excerpt here" in result.output
        assert "tags:" in result.output
        assert "5 files edited" in result.output
        assert "smartfork fork sess-789" in result.output


class TestForkCommand:
    @patch("smartfork.indexer.metadata_store.MetadataStore")
    @patch("smartfork.fork.assembler.ForkAssembler")
    @patch("smartfork.fork.assembler.ForkExporter")
    def test_fork_continue(
        self, mock_exporter, mock_assembler_cls, mock_store_cls, runner: CliRunner
    ) -> None:
        mock_store = mock_store_cls.return_value
        mock_store.get_session_document.return_value = MagicMock()

        mock_assembler = mock_assembler_cls.return_value
        mock_assembler.assemble.return_value = "Handoff content"

        result = runner.invoke(app, ["fork", "sess-123"])
        assert result.exit_code == 0
        assert "Generating" in result.output

    @patch("smartfork.indexer.metadata_store.MetadataStore")
    def test_fork_invalid_session(self, mock_store_cls, runner: CliRunner) -> None:
        mock_store = mock_store_cls.return_value
        mock_store.get_session_document.return_value = None

        result = runner.invoke(app, ["fork", "invalid-123"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    @patch("smartfork.indexer.metadata_store.MetadataStore")
    @patch("smartfork.fork.assembler.ForkAssembler")
    @patch("smartfork.fork.assembler.ForkExporter")
    def test_fork_superseded_session_warning(
        self, mock_exporter, mock_assembler_cls, mock_store_cls, runner: CliRunner
    ) -> None:
        mock_store = mock_store_cls.return_value
        mock_store.get_session_document.return_value = MagicMock()
        mock_store.get_superseding_sessions.return_value = [
            {"superseding_id": "sess-latest"}
        ]

        mock_assembler = mock_assembler_cls.return_value
        mock_assembler.assemble.return_value = "Handoff content"

        result = runner.invoke(app, ["fork", "sess-old"])
        assert result.exit_code == 0
        assert "superseded by sess-latest" in result.output.lower()

    @patch("smartfork.indexer.metadata_store.MetadataStore")
    @patch("smartfork.fork.assembler.ForkAssembler")
    @patch("smartfork.fork.assembler.ForkExporter")
    def test_fork_latest_session_no_warning(
        self, mock_exporter, mock_assembler_cls, mock_store_cls, runner: CliRunner
    ) -> None:
        mock_store = mock_store_cls.return_value
        mock_store.get_session_document.return_value = MagicMock()
        mock_store.get_superseding_sessions.return_value = []

        mock_assembler = mock_assembler_cls.return_value
        mock_assembler.assemble.return_value = "Handoff content"

        result = runner.invoke(app, ["fork", "sess-latest"])
        assert result.exit_code == 0
        assert "superseded" not in result.output.lower()


class TestStatusCommand:
    @patch("smartfork.indexer.metadata_store.MetadataStore")
    def test_basic_status(self, mock_store_cls, runner: CliRunner) -> None:
        mock_store = mock_store_cls.return_value
        mock_store.get_stats.return_value = {
            "total_sessions": 10,
            "by_agent": {"claudecode": 10},
            "by_project": {"test": 10},
            "by_quality": {"high": 5, "medium": 5},
        }
        mock_store.get_vector_count.return_value = 0

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
        mock_store.get_all_session_documents.return_value = [MagicMock()]

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
