"""Tests for OpenCodeAdapter."""

import importlib
import json
import sqlite3
from pathlib import Path

from smartfork.adapters.opencode import (
    get_default_opencode_db_path,
)
from smartfork.adapters.registry import clear_registry, get_adapter
from smartfork.indexer.parser import SessionParser


def _create_test_db(db_path: Path) -> None:
    """Create a minimal OpenCode SQLite database with sample data."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE session (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            parent_id TEXT,
            slug TEXT,
            directory TEXT,
            title TEXT,
            version TEXT,
            time_created INTEGER,
            time_updated INTEGER,
            agent TEXT,
            model TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE message (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            role TEXT,
            time_created INTEGER,
            data TEXT,
            FOREIGN KEY (session_id) REFERENCES session(id)
        )
    """)
    conn.execute("""
        CREATE TABLE part (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT,
            type TEXT,
            content TEXT,
            time_created INTEGER,
            data TEXT,
            FOREIGN KEY (message_id) REFERENCES message(id)
        )
    """)

    # Insert a session
    conn.execute(
        "INSERT INTO session (id, directory, title, time_created, time_updated, model) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "sess-001",
            "/home/dev/project",
            "Fix async database bug",
            1700000100000,
            1700000100000,
            "claude-sonnet-4-20250514",
        ),
    )
    conn.execute(
        "INSERT INTO session (id, directory, title, time_created, time_updated, model) VALUES (?, ?, ?, ?, ?, ?)",
        ("sess-002", "/home/dev/project", "Refactor config system", 1700000000000, 1700000000000, "gpt-4o")
    )

    # Insert messages for sess-001
    conn.execute(
        "INSERT INTO message (id, session_id, role, time_created, data) VALUES (?, ?, ?, ?, ?)",
        ("msg-1", "sess-001", "user", 1700000001000, json.dumps({"role": "user"}))
    )
    conn.execute(
        "INSERT INTO message (id, session_id, role, time_created, data) VALUES (?, ?, ?, ?, ?)",
        ("msg-2", "sess-001", "assistant", 1700000002000, json.dumps({"role": "assistant"}))
    )
    conn.execute(
        "INSERT INTO message (id, session_id, role, time_created, data) VALUES (?, ?, ?, ?, ?)",
        ("msg-3", "sess-001", "assistant", 1700000003000, json.dumps({"role": "assistant"}))
    )

    # Insert parts
    conn.execute(
        "INSERT INTO part (message_id, type, time_created, data) VALUES (?, ?, ?, ?)",
        ("msg-1", "text", 1700000001000, json.dumps({"type": "text", "text": "I'm getting a deadlock in the async database layer. How do I fix it?"}))
    )
    conn.execute(
        "INSERT INTO part (message_id, type, time_created, data) VALUES (?, ?, ?, ?)",
        (
            "msg-2",
            "tool",
            1700000002000,
            json.dumps({
                "type": "tool",
                "tool": "read_file",
                "state": {"input": {"file_path": "src/database.py"}}
            }),
        ),
    )
    conn.execute(
        "INSERT INTO part (message_id, type, time_created, data) VALUES (?, ?, ?, ?)",
        (
            "msg-2",
            "reasoning",
            1700000002500,
            json.dumps({
                "type": "reasoning",
                "text": "[Reasoning] The deadlock is caused by a circular wait between two async tasks both trying to acquire the same connection pool lock."
            }),
        ),
    )
    conn.execute(
        "INSERT INTO part (message_id, type, time_created, data) VALUES (?, ?, ?, ?)",
        (
            "msg-3",
            "text",
            1700000003000,
            json.dumps({"type": "text", "text": "The issue is a connection pool contention. Add a timeout to prevent deadlocks."}),
        ),
    )

    conn.commit()
    conn.close()


def _create_test_db_with_parent(db_path: Path, parent_id: str | None) -> None:
    """Create a minimal OpenCode SQLite database with a session that has parent_id."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE session (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            parent_id TEXT,
            slug TEXT,
            directory TEXT,
            title TEXT,
            version TEXT,
            time_created INTEGER,
            time_updated INTEGER,
            agent TEXT,
            model TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE message (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            role TEXT,
            time_created INTEGER,
            data TEXT,
            FOREIGN KEY (session_id) REFERENCES session(id)
        )
    """)
    conn.execute("""
        CREATE TABLE part (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT,
            type TEXT,
            content TEXT,
            time_created INTEGER,
            data TEXT,
            FOREIGN KEY (message_id) REFERENCES message(id)
        )
    """)

    conn.execute(
        "INSERT INTO session (id, parent_id, directory, title, time_created, time_updated, model) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("sess-parent", parent_id, "/home/dev/project", "Test task", 1700000100000, 1700000100000, "claude-sonnet-4"),
    )

    conn.execute(
        "INSERT INTO message (id, session_id, role, time_created, data) VALUES (?, ?, ?, ?, ?)",
        ("msg-1", "sess-parent", "user", 1700000001000, json.dumps({"role": "user"}))
    )

    conn.execute(
        "INSERT INTO part (message_id, type, time_created, data) VALUES (?, ?, ?, ?)",
        ("msg-1", "text", 1700000001000, json.dumps({"type": "text", "text": "Hello"}))
    )

    conn.commit()
    conn.close()


class TestOpenCodeModuleHelpers:
    def test_get_default_path(self) -> None:
        path = get_default_opencode_db_path()
        assert path.name == "opencode.db"
        assert ".local" in str(path) or "opencode" in str(path)

    def test_get_all_sessions_from_empty_db(self, tmp_path: Path) -> None:
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE session (id TEXT, title TEXT, created_at INTEGER, model TEXT)")
        conn.close()
        from smartfork.adapters.opencode import OpenCodeAdapter
        adapter = OpenCodeAdapter()
        sessions = adapter.get_all_sessions_from_db(db_path)
        assert sessions == []

    def test_get_all_sessions(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)
        from smartfork.adapters.opencode import OpenCodeAdapter
        adapter = OpenCodeAdapter()
        sessions = adapter.get_all_sessions_from_db(db_path)
        assert len(sessions) >= 1


class TestOpenCodeAdapter:
    def setup_method(self) -> None:
        clear_registry()
        import smartfork.adapters.opencode as oc
        importlib.reload(oc)

    def teardown_method(self) -> None:
        clear_registry()

    def test_registered_in_registry(self) -> None:
        adapter = get_adapter("opencode")
        assert adapter is not None
        assert adapter.agent_id == "opencode"
        assert adapter.display_name == "OpenCode"

    def test_is_valid_session_true(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)
        adapter = get_adapter("opencode")
        assert adapter is not None
        assert adapter.is_valid_session(db_path) is True

    def test_is_valid_session_false_for_no_session_table(self, tmp_path: Path) -> None:
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.close()
        adapter = get_adapter("opencode")
        assert adapter is not None
        assert adapter.is_valid_session(db_path) is False

    def test_is_valid_session_false_for_non_db(self, tmp_path: Path) -> None:
        f = tmp_path / "not_a_db.txt"
        f.write_text("hello")
        adapter = get_adapter("opencode")
        assert adapter is not None
        assert adapter.is_valid_session(f) is False

    def test_parse_raw_extracts_session_data(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)
        adapter = get_adapter("opencode")
        assert adapter is not None
        result = adapter.parse_raw(db_path)
        assert result is not None
        assert result.session_id == "sess-001"
        assert result.workspace_dir == "/home/dev/project"
        assert result.model_used == "claude-sonnet-4-20250514"

    def test_parse_raw_extracts_turns(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)
        adapter = get_adapter("opencode")
        assert adapter is not None
        result = adapter.parse_raw(db_path)
        assert result is not None
        assert len(result.turns) > 0
        user_turns = [t for t in result.turns if t.role == "user"]
        assert len(user_turns) >= 1

    def test_parse_raw_extracts_reasoning(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)
        adapter = get_adapter("opencode")
        assert adapter is not None
        result = adapter.parse_raw(db_path)
        assert result is not None
        reasoning_turns = [t for t in result.turns if "[Reasoning]" in t.content]
        assert len(reasoning_turns) >= 1

    def test_parse_raw_returns_none_for_nonexistent(self, tmp_path: Path) -> None:
        adapter = get_adapter("opencode")
        assert adapter is not None
        result = adapter.parse_raw(tmp_path / "nonexistent.db")
        assert result is None

    def test_session_type_is_sqlite(self) -> None:
        adapter = get_adapter("opencode")
        assert adapter is not None
        assert adapter.session_type == "sqlite"

    def test_session_with_parent_id(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db_with_parent(db_path, parent_id="sess_001")
        adapter = get_adapter("opencode")
        assert adapter is not None
        raw = adapter.parse_raw(db_path)
        assert raw is not None
        assert raw.parent_id == "sess_001"
        parser = SessionParser()
        doc = parser.parse_session(raw)
        assert doc is not None
        assert doc.parent_id == "sess_001"

    def test_session_without_parent_id(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db_with_parent(db_path, parent_id=None)
        adapter = get_adapter("opencode")
        assert adapter is not None
        raw = adapter.parse_raw(db_path)
        assert raw is not None
        assert raw.parent_id is None
        parser = SessionParser()
        doc = parser.parse_session(raw)
        assert doc is not None
        assert doc.parent_id is None
