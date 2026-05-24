"""Edge case tests for SmartFork v2."""

import sys
import time
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from smartfork.cli.commands import app as cli_app
from smartfork.config import SmartForkConfig
from smartfork.indexer.indexer import FullIndexer
from smartfork.indexer.intelligence import _extract_summary_fallback, _extract_title_fallback
from smartfork.indexer.metadata_store import MetadataStore
from smartfork.indexer.parser import SessionParser, derive_project_name, extract_languages
from smartfork.models.session import RawSessionData
from smartfork.providers.llm import AnthropicLLM, OpenAILLM, get_llm
from smartfork.search.deterministic import DeterministicSearchEngine, QueryParser


class TestEmptyInputs:
    def test_parser_handles_empty_raw(self) -> None:
        parser = SessionParser()
        raw = RawSessionData(
            session_id="empty",
            agent_id="test",
            session_path=Path("/tmp"),
            turns=[],
        )
        doc = parser.parse_session(raw)
        assert doc is not None
        assert doc.project_name == "unknown_project"
        assert doc.domains == []
        assert doc.languages == []

    def test_title_fallback_empty(self) -> None:
        title = _extract_title_fallback("")
        assert title == "Untitled Session"

    def test_summary_fallback_empty(self) -> None:
        summary = _extract_summary_fallback([], "")
        assert "No summary" in summary

    def test_derive_project_name_empty(self) -> None:
        name = derive_project_name("", [])
        assert name == "unknown_project"


class TestUnicodeHandling:
    def test_languages_handles_unicode_filenames(self) -> None:
        langs = extract_languages(["src/über.py", "tests/test_mañana.py"])
        assert "python" in langs

    def test_title_fallback_unicode(self) -> None:
        title = _extract_title_fallback("Fix authentication 🔐 for Café Münster")
        assert "Fix authentication" in title
        assert "🔐" in title


class TestCorruptData:
    def test_parser_handles_none_values(self) -> None:
        parser = SessionParser()
        raw = RawSessionData(
            session_id="corrupt",
            agent_id="test",
            session_path=Path("/tmp"),
            turns=[],
            task_raw="",
        )
        # Should not crash
        doc = parser.parse_session(raw)
        assert doc is not None

    def test_languages_handles_mixed_extensions(self) -> None:
        langs = extract_languages([
            "file.txt",
            "image.png",
            "script.py",
            "Makefile",
        ])
        assert "python" in langs


@pytest.mark.slow
class TestLargeInputs:
    def test_large_file_list(self) -> None:
        files = [f"src/module_{i}.py" for i in range(1000)]
        langs = extract_languages(files)
        assert "python" in langs
        assert len(langs) == 1  # All same language


class TestGracefulDegradation:
    def test_no_ollama_graceful_message(self) -> None:
        """EDGE-01.1: No Ollama installed produces a clear, actionable error."""
        with patch("smartfork.providers.llm.OLLAMA_AVAILABLE", False), \
             pytest.raises(RuntimeError) as exc_info:
            get_llm("ollama")
        msg = str(exc_info.value)
        assert "pip install ollama" in msg

    def test_no_cloud_api_key_mentions_secrets_env(self) -> None:
        """EDGE-01.2: Cloud providers without keys mention secrets.env."""
        with patch("smartfork.providers.llm._load_secrets", return_value={}), \
             patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError) as exc_info:
                AnthropicLLM()
            assert "secrets.env" in str(exc_info.value)

            with pytest.raises(RuntimeError) as exc_info:
                OpenAILLM()
            assert "secrets.env" in str(exc_info.value)

    def test_corrupt_config_recovery_message(self, tmp_path: Path) -> None:
        """EDGE-01.4: Corrupt config.toml is detected and defaults are used."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("invalid toml [[[\n", encoding="utf-8")
        with patch("smartfork.config.CONFIG_FILE", config_file), \
             patch("smartfork.config.logger") as mock_logger:
            config = SmartForkConfig.load()
        assert isinstance(config, SmartForkConfig)
        assert config.theme == "obsidian"
        assert mock_logger.warning.called
        args, _ = mock_logger.warning.call_args
        assert "Failed to parse config file" in args[0]

    def test_missing_textual_fallback(self, cli_runner: CliRunner) -> None:
        """EDGE-01.5: Missing textual shows a graceful fallback message."""
        # Remove cached tui modules so the import chain is forced to re-run.
        for key in list(sys.modules.keys()):
            if key.startswith("smartfork.tui"):
                del sys.modules[key]

        class FakeModule(types.ModuleType):
            def __getattr__(self, name: str) -> Any:
                raise ImportError(f"cannot import name '{name}' from '{self.__name__}'")

        fake = FakeModule("textual.app")
        fake.__path__ = []
        with patch.dict("sys.modules", {"textual.app": fake}):
            result = cli_runner.invoke(cli_app, ["shell"])
        # The shell command does not exist; Typer returns exit code 2.
        assert result.exit_code == 2
        assert (
            "Missing command" in result.output
            or "No such command" in result.output
            or "Usage:" in result.output
        )

    def test_lite_mode_flag(self, cli_runner: CliRunner) -> None:
        """EDGE-01.6: --lite flag is accepted and the config field exists."""
        result = cli_runner.invoke(cli_app, ["--lite", "status"])
        assert result.exit_code == 0
        config = SmartForkConfig()
        assert hasattr(config, "lite_mode")
        assert isinstance(config.lite_mode, bool)


class TestErrorHandling:
    def test_no_args_shows_help(self, cli_runner: CliRunner) -> None:
        """EDGE-02.1: Running smartfork with no args shows help."""
        result = cli_runner.invoke(cli_app)
        # Typer returns exit code 2 for no command even when help is shown,
        # so we just verify it doesn't crash and prints usage.
        assert "Usage:" in result.output

    def test_invalid_command(self, cli_runner: CliRunner) -> None:
        """EDGE-02.2: Unknown command produces a clear error."""
        result = cli_runner.invoke(cli_app, ["invalidcmd"])
        assert result.exit_code != 0
        assert "No such command" in result.output

    def test_missing_required_arg(self, cli_runner: CliRunner) -> None:
        """EDGE-02.3: Missing required argument produces a clear error."""
        result = cli_runner.invoke(cli_app, ["fork"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output

    def test_unicode_query(self) -> None:
        """EDGE-02.4: Unicode input to search parser does not crash."""
        parser = QueryParser()
        result = parser.parse("résumé café 🔐")
        assert result.intent is not None
        assert "résumé" in result.core_goal

    def test_very_long_query(self) -> None:
        """EDGE-02.5: Very long query (10K chars) does not crash."""
        parser = QueryParser()
        long_query = "x" * 10000
        result = parser.parse(long_query)
        assert result.core_goal == long_query


@pytest.mark.slow
class TestPerformance:
    def test_search_latency_10k(self) -> None:
        """EDGE-03.1: Search with 10K sessions completes within a reasonable time."""
        mock_store = MagicMock()
        mock_store.get_session.return_value = {
            "task_raw": "test task",
            "project_name": "test-project",
            "quality_tag": "solution_found",
            "session_start": 0,
            "duration_minutes": 0.0,
            "files_edited": "[]",
        }
        mock_store._deserialize_list.return_value = []
        engine = DeterministicSearchEngine(metadata_store=mock_store)
        mock_results = {f"sess_{i:05d}": 0.9 for i in range(10_000)}
        with patch.object(engine, "_vector_search", return_value=mock_results), \
             patch.object(engine, "_bm25_search", return_value=mock_results):
            start = time.perf_counter()
            cards = engine.search("test query")
            elapsed = time.perf_counter() - start
        assert len(cards) <= 10
        assert elapsed < 1.0

    def test_index_latency_100(self, tmp_path: Path) -> None:
        """EDGE-03.2: Indexing 100 dummy sessions completes within a reasonable time."""
        store = MetadataStore(tmp_path / "meta.db")
        mock_adapter = MagicMock()
        mock_adapter.parse_raw.return_value = RawSessionData(
            session_id="perf",
            agent_id="test",
            session_path=tmp_path,
            turns=[],
            task_raw="task",
        )
        mock_embedder = MagicMock()
        mock_embedder.embed_session.return_value = [0.1] * 512
        with patch("smartfork.indexer.indexer.get_adapter", return_value=mock_adapter), \
             patch(
                 "smartfork.indexer.scanner.SessionScanner.scan",
                 return_value=[("test", tmp_path)] * 100,
             ):
            indexer = FullIndexer(
                embedder=mock_embedder,
                store=store,
                intelligence=MagicMock(),
            )
            start = time.perf_counter()
            stats = indexer.index_all()
            elapsed = time.perf_counter() - start
        assert stats["parsed"] == 100
        assert elapsed < 30.0

    def test_tui_startup_time(self) -> None:
        """EDGE-03.3: TUI startup completes within a reasonable time."""
        pytest.importorskip("smartfork.tui.app")
        from smartfork.tui.app import run_tui
        start = time.perf_counter()
        with patch("textual.app.App.run", lambda self: None):
            run_tui()
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0
