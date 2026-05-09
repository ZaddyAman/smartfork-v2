"""Tests for KiloCodeAdapter."""

import importlib
from pathlib import Path

from smartfork.adapters.kilocode import (
    TOOL_CALL_TAGS,
    _clean_content,
    _extract_text,
    _is_tool_call,
    _resolve_ide_path,
)
from smartfork.adapters.registry import clear_registry, get_adapter

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "kilocode_session"


class TestKilocodeModuleHelpers:
    def test_extract_text_plain_string(self) -> None:
        assert _extract_text("hello world") == "hello world"

    def test_extract_text_array_of_parts(self) -> None:
        content = [
            {"type": "text", "text": "first part"},
            {"type": "text", "text": "second part"},
        ]
        result = _extract_text(content)
        assert "first part" in result
        assert "second part" in result

    def test_extract_text_nested_dict(self) -> None:
        content = {"type": "text", "text": {"value": "nested text"}}
        result = _extract_text(content)
        assert result == "nested text"

    def test_extract_text_empty(self) -> None:
        assert _extract_text([]) == ""

    def test_clean_content_removes_file_content(self) -> None:
        text = "Some text <file_content>secret</file_content> more text"
        result = _clean_content(text)
        assert "secret" not in result
        assert "Some text" in result
        assert "more text" in result

    def test_clean_content_removes_environment_details(self) -> None:
        text = "Before <environment_details>env stuff</environment_details> After"
        result = _clean_content(text)
        assert "env stuff" not in result

    def test_clean_content_removes_code_blocks(self) -> None:
        text = "Look at this: ```python\nprint('hello')\n``` end"
        result = _clean_content(text)
        assert "print" not in result

    def test_is_tool_call_detects_tags(self) -> None:
        assert _is_tool_call("<read_file>src/main.py</read_file>") is True
        assert _is_tool_call("<write_to_file>test.py</write_to_file>") is True
        assert _is_tool_call("regular conversation text") is False

    def test_all_tool_tags_documented(self) -> None:
        assert len(TOOL_CALL_TAGS) >= 15

    def test_resolve_ide_path_returns_path(self) -> None:
        path = _resolve_ide_path("Cursor")
        # Should return a Path or None (depending on platform env)
        assert path is None or isinstance(path, Path)


class TestKiloCodeAdapter:
    def setup_method(self) -> None:
        clear_registry()
        # Re-register by reloading module
        from smartfork.adapters import kilocode

        importlib.reload(kilocode)

    def teardown_method(self) -> None:
        clear_registry()

    def test_registered_in_registry(self) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        assert adapter.agent_id == "kilocode"
        assert adapter.display_name == "Kilo Code"

    def test_is_valid_session_true(self) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        # FIXTURES_DIR has api_conversation_history.json
        assert adapter.is_valid_session(FIXTURES_DIR) is True

    def test_is_valid_session_false_for_empty_dir(self, tmp_path: Path) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        assert adapter.is_valid_session(empty_dir) is False

    def test_is_valid_session_false_for_file(self, tmp_path: Path) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        f = tmp_path / "not_a_session.json"
        f.write_text("{}")
        assert adapter.is_valid_session(f) is False

    def test_get_session_files(self) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        files = adapter.get_session_files(Path("/fake"))
        assert "task_metadata.json" in files
        assert "api_conversation_history.json" in files
        assert "ui_messages.json" in files

    def test_parse_raw_extracts_session_id(self) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        result = adapter.parse_raw(FIXTURES_DIR)
        assert result is not None
        assert result.session_id == "kilocode_session"

    def test_parse_raw_extracts_file_signals(self) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        result = adapter.parse_raw(FIXTURES_DIR)
        assert result is not None
        assert "src/main.py" in result.files_edited
        assert "README.md" in result.files_read
        assert "tests/test_main.py" in result.files_mentioned

    def test_parse_raw_extracts_workspace_dir(self) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        result = adapter.parse_raw(FIXTURES_DIR)
        assert result is not None
        assert result.workspace_dir == "/home/dev/myproject"

    def test_parse_raw_extracts_task(self) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        result = adapter.parse_raw(FIXTURES_DIR)
        assert result is not None
        assert "authentication" in result.task_raw.lower()

    def test_parse_raw_extracts_model(self) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        result = adapter.parse_raw(FIXTURES_DIR)
        assert result is not None
        assert result.model_used == "claude-sonnet-4-20250514"

    def test_parse_raw_extracts_turns(self) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        result = adapter.parse_raw(FIXTURES_DIR)
        assert result is not None
        assert len(result.turns) > 0
        # Should have user turns
        user_turns = [t for t in result.turns if t.role == "user"]
        assert len(user_turns) >= 2

    def test_parse_raw_extracts_reasoning(self) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        result = adapter.parse_raw(FIXTURES_DIR)
        assert result is not None
        # Reasoning from ui_messages.json should appear as assistant turns
        reasoning_turns = [
            t for t in result.turns
            if t.role == "assistant" and "JWT" in t.content
        ]
        assert len(reasoning_turns) >= 1

    def test_parse_raw_filters_tool_calls(self) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        result = adapter.parse_raw(FIXTURES_DIR)
        assert result is not None
        # Tool call turns should be marked as tool calls
        tool_turns = [t for t in result.turns if t.is_tool_call]
        assert len(tool_turns) >= 1

    def test_parse_raw_cleans_content(self) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        result = adapter.parse_raw(FIXTURES_DIR)
        assert result is not None
        # No turn content should contain file_content tags
        for turn in result.turns:
            assert "<file_content>" not in turn.content

    def test_parse_raw_handles_multi_format_content(self) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        result = adapter.parse_raw(FIXTURES_DIR)
        assert result is not None
        # The array-of-parts content should be extracted
        text_turns = [t for t in result.turns if "auth module" in t.content]
        assert len(text_turns) >= 1

    def test_parse_raw_returns_none_for_nonexistent_dir(self, tmp_path: Path) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        result = adapter.parse_raw(tmp_path / "nonexistent")
        assert result is None

    def test_parse_raw_returns_none_for_corrupt_json(self, tmp_path: Path) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        corrupt_dir = tmp_path / "corrupt"
        corrupt_dir.mkdir()
        (corrupt_dir / "api_conversation_history.json").write_text("{invalid json")
        (corrupt_dir / "task_metadata.json").write_text("{}")
        (corrupt_dir / "ui_messages.json").write_text("[]")
        result = adapter.parse_raw(corrupt_dir)
        assert result is None

    def test_get_ide_choices(self) -> None:
        adapter = get_adapter("kilocode")
        assert adapter is not None
        choices = adapter.get_ide_choices()
        assert "Cursor" in choices
        assert "VS Code" in choices
        assert "AntiGravity" in choices
