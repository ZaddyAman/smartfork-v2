"""SQLite metadata store for SmartFork v2."""

import json
import sqlite3
from pathlib import Path
from typing import Any

from smartfork.models.session import SessionDocument

# SQL Schema
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
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
    indexed_at INTEGER NOT NULL DEFAULT 0,
    schema_version INTEGER NOT NULL DEFAULT 2
);

CREATE TABLE IF NOT EXISTS supersession_links (
    superseded_id TEXT NOT NULL,
    superseding_id TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    detected_at INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (superseded_id, superseding_id),
    FOREIGN KEY (superseded_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (superseding_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_name);
CREATE INDEX IF NOT EXISTS idx_sessions_quality ON sessions(quality_tag);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(session_start);
CREATE INDEX IF NOT EXISTS idx_sessions_indexed ON sessions(indexed_at);
CREATE INDEX IF NOT EXISTS idx_superseded ON supersession_links(superseded_id);
CREATE INDEX IF NOT EXISTS idx_superseding ON supersession_links(superseding_id);
"""


class MetadataStore:
    """SQLite-backed metadata store for SmartFork sessions.

    Provides CRUD operations, structured queries, and supersession tracking.
    Uses WAL mode for concurrent read performance.
    """

    def __init__(self, db_path: str | Path = "~/.smartfork/metadata.db") -> None:
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._get_conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.executescript(SCHEMA_SQL)
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a SQLite connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @staticmethod
    def _serialize_list(value: list[Any]) -> str:
        return json.dumps(value)

    @staticmethod
    def _deserialize_list(value: str) -> list[Any]:
        if not value:
            return []
        try:
            result: list[Any] = json.loads(value)
            return result
        except json.JSONDecodeError:
            return []

    # --- CRUD ---

    def upsert_session(self, session: SessionDocument) -> None:
        """Insert or update a session in the metadata store.

        Args:
            session: The SessionDocument to store.
        """
        with self._get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sessions (
                    session_id, agent, project_name, project_root,
                    session_start, session_end, duration_minutes, model_used,
                    files_edited, files_read, files_mentioned,
                    edit_count, user_edit_count, final_files,
                    domains, languages, layers, session_pattern,
                    task_raw, summary_doc, propositions,
                    quality_tag, tech_tags, indexed_at, schema_version
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?
                )""",
                (
                    session.session_id,
                    session.agent,
                    session.project_name,
                    session.project_root,
                    session.session_start,
                    session.session_end,
                    session.duration_minutes,
                    session.model_used,
                    self._serialize_list(session.files_edited),
                    self._serialize_list(session.files_read),
                    self._serialize_list(session.files_mentioned),
                    session.edit_count,
                    session.user_edit_count,
                    self._serialize_list(session.final_files),
                    self._serialize_list(session.domains),
                    self._serialize_list(session.languages),
                    self._serialize_list(session.layers),
                    session.session_pattern,
                    session.task_raw,
                    session.summary_doc,
                    self._serialize_list(session.propositions),
                    (
                        session.quality_tag.value
                        if hasattr(session.quality_tag, "value")
                        else str(session.quality_tag)
                    ),
                    self._serialize_list(session.tech_tags),
                    session.indexed_at,
                    session.schema_version,
                ),
            )
            conn.commit()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Retrieve a session by ID.

        Args:
            session_id: The session identifier.

        Returns:
            Dict of session data, or None if not found.
        """
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row:
                return dict(row)
            return None

    def delete_session(self, session_id: str) -> bool:
        """Delete a session from the store.

        Args:
            session_id: The session to delete.

        Returns:
            True if deleted, False if not found.
        """
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    # --- Queries ---

    def get_sessions_by_project(self, project_name: str) -> list[dict[str, Any]]:
        """Get all sessions for a project."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE project_name = ? ORDER BY session_start DESC",
                (project_name,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_sessions_by_domain(self, domain: str) -> list[dict[str, Any]]:
        """Get sessions matching a domain (JSON contains search)."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE domains LIKE ? ORDER BY session_start DESC",
                (f'%"{domain}"%',),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_sessions_by_quality(self, quality_tag: str) -> list[dict[str, Any]]:
        """Get sessions by quality tag."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE quality_tag = ? ORDER BY session_start DESC",
                (quality_tag,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_sessions_by_agent(self, agent: str) -> list[dict[str, Any]]:
        """Get sessions from a specific agent."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE agent = ? ORDER BY session_start DESC",
                (agent,),
            ).fetchall()
            return [dict(r) for r in rows]

    # --- Supersession ---

    def add_supersession_link(
        self,
        superseded_id: str,
        superseding_id: str,
        confidence: float = 0.0,
        detected_at: int = 0,
        reason: str = "",
    ) -> None:
        """Add a supersession link between two sessions."""
        with self._get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO supersession_links
                   (superseded_id, superseding_id, confidence, detected_at, reason)
                   VALUES (?, ?, ?, ?, ?)""",
                (superseded_id, superseding_id, confidence, detected_at, reason),
            )
            conn.commit()

    def get_superseding_sessions(self, session_id: str) -> list[dict[str, Any]]:
        """Get sessions that supersede the given session."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM supersession_links WHERE superseded_id = ?",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_superseded_sessions(self, session_id: str) -> list[dict[str, Any]]:
        """Get sessions that are superseded by the given session."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM supersession_links WHERE superseding_id = ?",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # --- Stats ---

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the metadata store.

        Returns:
            Dict with counts by project, quality, agent, and total.
        """
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

            by_project = conn.execute(
                "SELECT project_name, COUNT(*) as cnt "
                "FROM sessions GROUP BY project_name ORDER BY cnt DESC"
            ).fetchall()

            by_quality = conn.execute(
                "SELECT quality_tag, COUNT(*) as cnt "
                "FROM sessions GROUP BY quality_tag ORDER BY cnt DESC"
            ).fetchall()

            by_agent = conn.execute(
                "SELECT agent, COUNT(*) as cnt "
                "FROM sessions GROUP BY agent ORDER BY cnt DESC"
            ).fetchall()

            return {
                "total_sessions": total,
                "by_project": {r["project_name"]: r["cnt"] for r in by_project},
                "by_quality": {r["quality_tag"]: r["cnt"] for r in by_quality},
                "by_agent": {r["agent"]: r["cnt"] for r in by_agent},
            }

    # --- Filtering ---

    def get_filtered_ids(
        self,
        project: str | None = None,
        domain: str | None = None,
        quality: str | None = None,
        agent: str | None = None,
        limit: int = 100,
    ) -> list[str]:
        """Get session IDs matching multiple filter criteria.

        Args:
            project: Filter by project name.
            domain: Filter by domain (JSON contains check).
            quality: Filter by quality tag.
            agent: Filter by agent ID.
            limit: Maximum number of results.

        Returns:
            List of session_id strings.
        """
        conditions: list[str] = []
        params: list[Any] = []

        if project:
            conditions.append("project_name = ?")
            params.append(project)
        if domain:
            conditions.append("domains LIKE ?")
            params.append(f'%"{domain}"%')
        if quality:
            conditions.append("quality_tag = ?")
            params.append(quality)
        if agent:
            conditions.append("agent = ?")
            params.append(agent)

        query = "SELECT session_id FROM sessions"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY session_start DESC LIMIT ?"
        params.append(limit)

        with self._get_conn() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [r["session_id"] for r in rows]
