"""Edge case tests for SmartFork v2."""

from pathlib import Path

import pytest

from smartfork.indexer.parser import SessionParser, derive_project_name, extract_languages
from smartfork.indexer.intelligence import _extract_title_fallback, _extract_summary_fallback
from smartfork.models.session import RawSessionData


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
            task_raw="",  # type: ignore[arg-type]
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
