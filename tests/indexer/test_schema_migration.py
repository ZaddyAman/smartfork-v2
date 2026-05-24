"""Tests for database schema creation and migration."""

import sqlite3
from pathlib import Path

from smartfork.indexer.metadata_store import MetadataStore


def _sqlite_vec_available() -> bool:
    """Check if sqlite-vec extension is available."""
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE VIRTUAL TABLE test USING vec0(id text primary key, v float[1])"
        )
        conn.close()
        return True
    except sqlite3.OperationalError:
        return False


SQLITE_VEC_AVAILABLE = _sqlite_vec_available()


class TestSchemaMigration:
    def test_fresh_database_creates_all_tables(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        store = MetadataStore(db_path)

        with store._get_conn() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row["name"] for row in cursor.fetchall()}

        assert "sessions" in tables
        assert "session_relationships" in tables
        assert "supersession_links" in tables
        assert "sessions_fts" in tables
        if SQLITE_VEC_AVAILABLE:
            assert "session_vectors" in tables

        # Verify user_version is 4
        with store._get_conn() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 4

    def test_v3_to_v4_migration_preserves_data(self, tmp_path: Path) -> None:
        db_path = tmp_path / "v3.db"

        # Create a raw v3 database
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(
            """
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY,
                agent TEXT NOT NULL,
                project_name TEXT NOT NULL,
                project_root TEXT NOT NULL DEFAULT '',
                session_start INTEGER NOT NULL DEFAULT 0,
                session_end INTEGER NOT NULL DEFAULT 0,
                duration_minutes REAL NOT NULL DEFAULT 0.0,
                model_used TEXT,
                files_edited TEXT NOT NULL DEFAULT '[]',
                files_read TEXT NOT NULL DEFAULT '[]',
                files_mentioned TEXT NOT NULL DEFAULT '[]',
                edit_count INTEGER NOT NULL DEFAULT 0,
                user_edit_count INTEGER NOT NULL DEFAULT 0,
                final_files TEXT NOT NULL DEFAULT '[]',
                domains TEXT NOT NULL DEFAULT '[]',
                languages TEXT NOT NULL DEFAULT '[]',
                layers TEXT NOT NULL DEFAULT '[]',
                session_pattern TEXT NOT NULL DEFAULT 'standard_implementation',
                task_raw TEXT NOT NULL DEFAULT '',
                summary_doc TEXT NOT NULL DEFAULT '',
                propositions TEXT NOT NULL DEFAULT '[]',
                quality_tag TEXT NOT NULL DEFAULT 'unknown',
                tech_tags TEXT NOT NULL DEFAULT '[]',
                reasoning_docs TEXT NOT NULL DEFAULT '[]',
                indexed_at INTEGER NOT NULL DEFAULT 0,
                schema_version INTEGER NOT NULL DEFAULT 3
            );

            CREATE TABLE supersession_links (
                superseded_id TEXT NOT NULL,
                superseding_id TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.0,
                detected_at INTEGER NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (superseded_id, superseding_id)
            );
            """
        )
        conn.execute(
            "INSERT INTO sessions (session_id, agent, project_name, task_raw, schema_version) "
            "VALUES (?, ?, ?, ?, ?)",
            ("sess-1", "kilocode", "proj-a", "Fix auth bug", 3),
        )
        conn.execute(
            "INSERT INTO sessions (session_id, agent, project_name, task_raw, schema_version) "
            "VALUES (?, ?, ?, ?, ?)",
            ("sess-2", "kilocode", "proj-a", "Refactor login system", 3),
        )
        conn.execute(
            "INSERT INTO supersession_links (superseded_id, superseding_id, confidence, reason) "
            "VALUES (?, ?, ?, ?)",
            ("sess-1", "sess-2", 0.95, "same task"),
        )
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
        conn.close()

        # Instantiate MetadataStore — should auto-migrate
        store = MetadataStore(db_path)

        # Verify sessions data preserved
        result = store.get_session("sess-1")
        assert result is not None
        assert result["session_id"] == "sess-1"
        assert result["agent"] == "kilocode"
        assert result["project_name"] == "proj-a"
        assert result["task_raw"] == "Fix auth bug"

        # Verify supersession_links migrated to session_relationships
        rels = store.get_relationships("sess-1", direction="from")
        assert len(rels) == 1
        assert rels[0].from_session == "sess-1"
        assert rels[0].to_session == "sess-2"
        assert rels[0].relationship_type == "supersession"
        assert rels[0].confidence == 0.95
        assert rels[0].detected_by == "heuristic"

        # Verify FTS5 populated
        fts_results = store.fts5_search("auth")
        assert len(fts_results) == 1
        assert fts_results[0][0] == "sess-1"

        # Verify PRAGMA user_version is now 4
        with store._get_conn() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 4

    def test_migration_is_idempotent(self, tmp_path: Path) -> None:
        db_path = tmp_path / "v3.db"

        # Create a raw v3 database
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(
            """
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY,
                agent TEXT NOT NULL,
                project_name TEXT NOT NULL,
                project_root TEXT NOT NULL DEFAULT '',
                session_start INTEGER NOT NULL DEFAULT 0,
                session_end INTEGER NOT NULL DEFAULT 0,
                duration_minutes REAL NOT NULL DEFAULT 0.0,
                model_used TEXT,
                files_edited TEXT NOT NULL DEFAULT '[]',
                files_read TEXT NOT NULL DEFAULT '[]',
                files_mentioned TEXT NOT NULL DEFAULT '[]',
                edit_count INTEGER NOT NULL DEFAULT 0,
                user_edit_count INTEGER NOT NULL DEFAULT 0,
                final_files TEXT NOT NULL DEFAULT '[]',
                domains TEXT NOT NULL DEFAULT '[]',
                languages TEXT NOT NULL DEFAULT '[]',
                layers TEXT NOT NULL DEFAULT '[]',
                session_pattern TEXT NOT NULL DEFAULT 'standard_implementation',
                task_raw TEXT NOT NULL DEFAULT '',
                summary_doc TEXT NOT NULL DEFAULT '',
                propositions TEXT NOT NULL DEFAULT '[]',
                quality_tag TEXT NOT NULL DEFAULT 'unknown',
                tech_tags TEXT NOT NULL DEFAULT '[]',
                reasoning_docs TEXT NOT NULL DEFAULT '[]',
                indexed_at INTEGER NOT NULL DEFAULT 0,
                schema_version INTEGER NOT NULL DEFAULT 3
            );

            CREATE TABLE supersession_links (
                superseded_id TEXT NOT NULL,
                superseding_id TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.0,
                detected_at INTEGER NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (superseded_id, superseding_id)
            );
            """
        )
        conn.execute(
            "INSERT INTO sessions (session_id, agent, project_name, task_raw) "
            "VALUES (?, ?, ?, ?)",
            ("sess-1", "kilocode", "proj-a", "Fix auth bug"),
        )
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
        conn.close()

        store = MetadataStore(db_path)

        # Run migration again directly — should not error
        with store._get_conn() as conn:
            store._migrate_to_v4(conn)

        # Verify basic functionality still works
        result = store.get_session("sess-1")
        assert result is not None
        assert result["session_id"] == "sess-1"
