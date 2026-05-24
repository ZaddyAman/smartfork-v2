"""Tests for ClaudeCodeAdapter."""

import importlib
from pathlib import Path

from smartfork.adapters.claudecode import (
    _extract_file_signals_from_tools,
    _extract_text_from_content,
    _get_claude_projects_dir,
    scan_claude_sessions,
)
from smartfork.adapters.registry import clear_registry, get_adapter
from smartfork.indexer.parser import SessionParser

FIXTURE_FILE = Path(__file__).parent.parent / "fixtures" / "claudecode_session.jsonl"


class TestClaudeModuleHelpers:
    def test_extract_text_from_string(self) -> None:
        assert _extract_text_from_content("hello") == "hello"

    def test_extract_text_from_blocks(self) -> None:
        content = [
            {"type": "text", "text": "I found the issue."},
            {"type": "tool_use", "name": "read_file", "input": {"file_path": "x.py"}},
        ]
        result = _extract_text_from_content(content)
        assert "I found the issue" in result
        assert "[tool_use: read_file]" in result

    def test_extract_file_signals(self) -> None:
        messages = [
            {"content": [
                {"type": "tool_use", "name": "read_file", "input": {"file_path": "src/a.py"}},
                {"type": "tool_use", "name": "write_file", "input": {"file_path": "src/b.py"}},
            ]},
        ]
        signals = _extract_file_signals_from_tools(messages)
        assert "src/a.py" in signals["files_read"]
        assert "src/b.py" in signals["files_edited"]

    def test_get_claude_projects_dir_default(self) -> None:
        path = _get_claude_projects_dir()
        assert path.name == "projects"
        assert str(Path.home()) in str(path)


class TestClaudeCodeAdapter:
    def setup_method(self) -> None:
        clear_registry()
        from smartfork.adapters import claudecode

        importlib.reload(claudecode)

    def teardown_method(self) -> None:
        clear_registry()

    def test_registered_in_registry(self) -> None:
        adapter = get_adapter("claudecode")
        assert adapter is not None
        assert adapter.agent_id == "claudecode"
        assert adapter.display_name == "Claude Code"

    def test_is_valid_session_true_for_jsonl(self) -> None:
        adapter = get_adapter("claudecode")
        assert adapter is not None
        assert adapter.is_valid_session(FIXTURE_FILE) is True

    def test_is_valid_session_false_for_dir(self, tmp_path: Path) -> None:
        adapter = get_adapter("claudecode")
        assert adapter is not None
        assert adapter.is_valid_session(tmp_path) is False

    def test_is_valid_session_false_for_txt(self, tmp_path: Path) -> None:
        adapter = get_adapter("claudecode")
        assert adapter is not None
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert adapter.is_valid_session(f) is False

    def test_get_session_files(self) -> None:
        adapter = get_adapter("claudecode")
        assert adapter is not None
        files = adapter.get_session_files(Path("/tmp/test.jsonl"))
        assert len(files) == 1

    def test_parse_raw_extracts_session_id(self) -> None:
        adapter = get_adapter("claudecode")
        assert adapter is not None
        result = adapter.parse_raw(FIXTURE_FILE)
        assert result is not None
        assert result.session_id == "claudecode_session"

    def test_parse_raw_extracts_turns(self) -> None:
        adapter = get_adapter("claudecode")
        assert adapter is not None
        result = adapter.parse_raw(FIXTURE_FILE)
        assert result is not None
        assert len(result.turns) > 0
        user_turns = [t for t in result.turns if t.role == "user"]
        assert len(user_turns) >= 1

    def test_parse_raw_extracts_workspace_dir(self) -> None:
        adapter = get_adapter("claudecode")
        assert adapter is not None
        result = adapter.parse_raw(FIXTURE_FILE)
        assert result is not None
        assert result.workspace_dir == "/home/dev/myproject"

    def test_parse_raw_extracts_model(self) -> None:
        adapter = get_adapter("claudecode")
        assert adapter is not None
        result = adapter.parse_raw(FIXTURE_FILE)
        assert result is not None
        assert result.model_used == "claude-sonnet-4-20250514"

    def test_parse_raw_extracts_file_signals(self) -> None:
        adapter = get_adapter("claudecode")
        assert adapter is not None
        result = adapter.parse_raw(FIXTURE_FILE)
        assert result is not None
        assert "src/database.py" in result.files_read
        assert "src/database_async.py" in result.files_edited

    def test_parse_raw_returns_none_for_nonexistent(self, tmp_path: Path) -> None:
        adapter = get_adapter("claudecode")
        assert adapter is not None
        result = adapter.parse_raw(tmp_path / "nonexistent.jsonl")
        assert result is None

    def test_parse_raw_handles_empty_jsonl(self, tmp_path: Path) -> None:
        adapter = get_adapter("claudecode")
        assert adapter is not None
        f = tmp_path / "empty.jsonl"
        f.write_text("")
        # Empty file is valid jsonl but has no turns
        # Should still parse without crashing
        result = adapter.parse_raw(f)
        assert result is None  # is_valid_session returns True but no content

    def test_session_type_is_project(self) -> None:
        adapter = get_adapter("claudecode")
        assert adapter is not None
        assert adapter.session_type == "project"

    def test_scan_claude_sessions_empty_dir(self, tmp_path: Path) -> None:
        result = scan_claude_sessions(tmp_path)
        assert result == []

    def test_claudecode_session_parent_id_is_none(self) -> None:
        adapter = get_adapter("claudecode")
        assert adapter is not None
        raw = adapter.parse_raw(FIXTURE_FILE)
        assert raw is not None
        assert raw.parent_id is None
        assert raw.previous_session_id is None
        parser = SessionParser()
        doc = parser.parse_session(raw)
        assert doc is not None
        assert doc.parent_id is None
        assert doc.previous_session_id is None
