"""Tests for SessionParser."""

from pathlib import Path

from smartfork.indexer.parser import (
    SessionParser,
    classify_session_pattern,
    derive_project_name,
    extract_domains,
    extract_languages,
    extract_layers,
    extract_reasoning,
)
from smartfork.models.session import QualityTag, RawSessionData, RawTurn


class TestDeriveProjectName:
    def test_from_workspace_dir(self) -> None:
        name = derive_project_name("/home/dev/myproject", [])
        assert name == "myproject"

    def test_from_workspace_dir_windows(self) -> None:
        name = derive_project_name(r"C:\Users\dev\myproject", [])
        assert name == "myproject"

    def test_common_root(self) -> None:
        name = derive_project_name(
            "", ["smartfork/src/main.py", "smartfork/tests/test.py"]
        )
        assert name == "smartfork"

    def test_fallback_first_dir(self) -> None:
        name = derive_project_name("", ["src/main.py", "tests/test.py"])
        assert name == "src"

    def test_unknown(self) -> None:
        name = derive_project_name("", [])
        assert name == "unknown_project"


class TestExtractDomains:
    def test_from_file_paths(self) -> None:
        domains = extract_domains(
            ["src/auth.py", "tests/test_auth.py", "src/database.py"]
        )
        assert "auth" in domains
        assert "database" in domains
        assert "testing" in domains

    def test_empty(self) -> None:
        assert extract_domains([]) == []

    def test_unique_and_sorted(self) -> None:
        domains = extract_domains(["auth/login.py", "auth/jwt.py"])
        assert domains == ["auth"]


class TestExtractLanguages:
    def test_basic(self) -> None:
        langs = extract_languages(
            ["src/main.py", "src/utils.js", "src/style.css", "README.md"]
        )
        assert "python" in langs
        assert "javascript" in langs
        assert "css" in langs

    def test_typescript_variants(self) -> None:
        langs = extract_languages(["app.tsx", "types.ts", "config.json"])
        assert "typescript" in langs
        assert "json" in langs

    def test_cpp_and_c(self) -> None:
        langs = extract_languages(
            ["main.c", "main.cpp", "header.hpp", "source.cxx"]
        )
        assert "c" in langs
        assert "c++" in langs

    def test_empty(self) -> None:
        assert extract_languages([]) == []


class TestExtractLayers:
    def test_frontend(self) -> None:
        layers = extract_layers(["src/App.tsx", "src/components/Button.tsx"])
        assert layers == ["frontend"]

    def test_backend(self) -> None:
        layers = extract_layers(["src/api.py", "src/database.py"])
        assert layers == ["backend"]

    def test_backend_from_py_file(self) -> None:
        layers = extract_layers(["src/models.py"])
        assert layers == ["backend"]

    def test_fullstack(self) -> None:
        layers = extract_layers(["src/App.tsx", "src/api.py"])
        assert "frontend" in layers
        assert "backend" in layers

    def test_empty(self) -> None:
        assert extract_layers([]) == []


class TestClassifySessionPattern:
    def test_debugging_from_keywords(self) -> None:
        pattern = classify_session_pattern(
            [], [], 0, 0, "fix the bug in login error handling"
        )
        assert pattern == "debugging_session"

    def test_debugging_from_tool_ratio(self) -> None:
        turns = [
            RawTurn(
                role="assistant",
                content="<read_file>",
                is_tool_call=True,
                tool_name="read_file",
            ),
            RawTurn(
                role="assistant",
                content="<search_files>",
                is_tool_call=True,
                tool_name="search_files",
            ),
            RawTurn(
                role="assistant",
                content="<search_files>",
                is_tool_call=True,
                tool_name="search_files",
            ),
            RawTurn(
                role="assistant",
                content="<search_files>",
                is_tool_call=True,
                tool_name="search_files",
            ),
            RawTurn(
                role="assistant",
                content="<write_to_file>",
                is_tool_call=True,
                tool_name="write_to_file",
            ),
        ]
        pattern = classify_session_pattern(
            turns, [], 0, 0, "investigate issue"
        )
        assert pattern == "debugging_session"

    def test_exploration(self) -> None:
        turns = [
            RawTurn(
                role="assistant",
                content="<list_files>",
                is_tool_call=True,
                tool_name="list_files",
            ),
            RawTurn(
                role="assistant",
                content="<search_files>",
                is_tool_call=True,
                tool_name="search_files",
            ),
        ]
        pattern = classify_session_pattern(
            turns, [], 0, 0, "explore the codebase"
        )
        assert pattern == "exploration_session"

    def test_refactoring_from_tool_calls(self) -> None:
        turns = [
            RawTurn(
                role="assistant",
                content="<replace_in_file>",
                is_tool_call=True,
                tool_name="replace_in_file",
            )
            for _ in range(5)
        ]
        pattern = classify_session_pattern(
            turns, [], 0, 0, "refactor code"
        )
        assert pattern == "refactoring_session"

    def test_refactoring_from_edit_count(self) -> None:
        pattern = classify_session_pattern(
            [], ["a.py", "b.py", "c.py", "d.py"], 0, 5, "clean up"
        )
        assert pattern == "refactoring_session"

    def test_configuration(self) -> None:
        pattern = classify_session_pattern(
            [], ["config.yaml", "settings.json"], 0, 0, "setup project"
        )
        assert pattern == "configuration_session"

    def test_not_configuration_when_code_present(self) -> None:
        pattern = classify_session_pattern(
            [], ["config.yaml", "main.py"], 0, 0, "setup project"
        )
        assert pattern != "configuration_session"

    def test_standard_implementation(self) -> None:
        pattern = classify_session_pattern(
            [], [], 0, 0, "add new feature to dashboard"
        )
        assert pattern == "standard_implementation"


class TestExtractReasoning:
    def test_deduplicates(self) -> None:
        turns = [
            RawTurn(
                role="assistant",
                content="Need to check JWT validation logic here.",
                timestamp=1000,
            ),
            RawTurn(
                role="assistant",
                content="Need to check JWT validation logic here.",
                timestamp=2000,
            ),
            RawTurn(
                role="assistant",
                content="The fix should be in middleware.",
                timestamp=3000,
            ),
        ]
        result = extract_reasoning(turns)
        # First two are duplicates (first 100 chars match)
        assert len(result) == 2

    def test_skips_tool_calls(self) -> None:
        turns = [
            RawTurn(
                role="assistant",
                content="Some reasoning here that is long enough.",
                is_tool_call=True,
            ),
        ]
        assert extract_reasoning(turns) == []

    def test_skips_short_content(self) -> None:
        turns = [
            RawTurn(role="assistant", content="Short.", timestamp=1000),
        ]
        assert extract_reasoning(turns) == []

    def test_skips_non_assistant(self) -> None:
        turns = [
            RawTurn(
                role="user",
                content="This is a long user message with enough chars.",
                timestamp=1000,
            ),
        ]
        assert extract_reasoning(turns) == []


class TestSessionParser:
    def test_parse_session_full(self) -> None:
        raw = RawSessionData(
            session_id="test-sess-1",
            agent_id="kilocode",
            session_path=Path("/tmp/test"),
            turns=[
                RawTurn(
                    role="user",
                    content="fix auth bug",
                    timestamp=1700000001000,
                ),
                RawTurn(
                    role="assistant",
                    content="I will check the database connection first.",
                    timestamp=1700000002000,
                ),
            ],
            files_edited=["src/auth.py", "src/database.py"],
            files_read=["README.md"],
            workspace_dir="/home/dev/myproject",
            task_raw="fix authentication bug in login",
            model_used="claude-sonnet-4",
            session_start=1700000001000,
            session_end=1700000002000,
            edit_count=2,
        )

        parser = SessionParser()
        doc = parser.parse_session(raw)

        assert doc is not None
        assert doc.session_id == "test-sess-1"
        assert doc.agent == "kilocode"
        assert doc.project_name == "myproject"
        assert doc.project_root == "/home/dev/myproject"
        assert "auth" in doc.domains
        assert "database" in doc.domains
        assert "python" in doc.languages
        assert len(doc.reasoning_docs) > 0
        assert doc.schema_version == 4
        assert doc.quality_tag == QualityTag.UNKNOWN

    def test_parse_session_infers_all_fields(self) -> None:
        raw = RawSessionData(
            session_id="sess-2",
            agent_id="claudecode",
            session_path=Path("/tmp/test"),
            turns=[
                RawTurn(
                    role="assistant",
                    content="Refactoring the configuration module now.",
                    timestamp=1000,
                ),
            ],
            files_edited=["src/main.py", "config/settings.yaml"],
            workspace_dir="/home/dev/config-project",
            task_raw="refactor and clean the configuration system",
            edit_count=5,
        )

        parser = SessionParser()
        doc = parser.parse_session(raw)

        assert doc is not None
        assert doc.session_pattern == "refactoring_session"
        assert "config" in doc.domains
        assert "python" in doc.languages

    def test_parse_session_kilocode_tools(self) -> None:
        raw = RawSessionData(
            session_id="kilocode-1",
            agent_id="kilocode",
            session_path=Path("/tmp/kilocode.json"),
            turns=[
                RawTurn(
                    role="user",
                    content="Implement auth system",
                    timestamp=1000,
                ),
                RawTurn(
                    role="assistant",
                    content="Let me analyze the requirements first.",
                    timestamp=2000,
                ),
                RawTurn(
                    role="assistant",
                    content="<read_file>src/auth.py</read_file>",
                    is_tool_call=True,
                    tool_name="read_file",
                    timestamp=3000,
                ),
                RawTurn(
                    role="assistant",
                    content="<write_to_file>src/auth.py</write_to_file>",
                    is_tool_call=True,
                    tool_name="write_to_file",
                    timestamp=4000,
                ),
            ],
            files_edited=["src/auth.py"],
            workspace_dir="/home/dev/project",
            task_raw="Implement auth system",
        )

        parser = SessionParser()
        doc = parser.parse_session(raw)

        assert doc is not None
        assert doc.project_name == "project"
        assert "auth" in doc.domains
        assert doc.session_pattern == "standard_implementation"

    def test_parse_session_returns_none_for_none_raw(self) -> None:
        parser = SessionParser()
        assert parser.parse_session(None) is None  # type: ignore[arg-type]

    def test_parse_session_empty_files(self) -> None:
        raw = RawSessionData(
            session_id="empty-1",
            agent_id="opencode",
            session_path=Path("/tmp/empty"),
            turns=[
                RawTurn(
                    role="assistant",
                    content="No files were modified in this session.",
                    timestamp=1000,
                ),
            ],
            workspace_dir="",
            task_raw="Ask a question",
        )

        parser = SessionParser()
        doc = parser.parse_session(raw)

        assert doc is not None
        assert doc.domains == []
        assert doc.languages == []
        assert doc.layers == []
        assert doc.project_name == "unknown_project"
