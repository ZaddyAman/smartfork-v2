"""SQLite metadata store for SmartFork v2."""

import json
import sqlite3
from pathlib import Path
from typing import Any

from loguru import logger

from smartfork.models.relationship import SessionRelationship
from smartfork.models.session import QualityTag, SessionDocument

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
    reasoning_docs TEXT NOT NULL DEFAULT '[]',
    indexed_at INTEGER NOT NULL DEFAULT 0,
    schema_version INTEGER NOT NULL DEFAULT 4
);

CREATE TABLE IF NOT EXISTS session_relationships (
    from_session TEXT NOT NULL,
    to_session TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    detected_by TEXT NOT NULL,
    reasons TEXT NOT NULL DEFAULT '[]',
    created_at INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (from_session, to_session, relationship_type),
    FOREIGN KEY (from_session) REFERENCES sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (to_session) REFERENCES sessions(session_id) ON DELETE CASCADE
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

CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
    task_raw,
    summary_doc,
    reasoning_text,
    tech_tags,
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS sessions_fts_insert AFTER INSERT ON sessions BEGIN
    INSERT INTO sessions_fts(rowid, task_raw, summary_doc, reasoning_text, tech_tags)
    VALUES (
        new.rowid,
        new.task_raw,
        new.summary_doc,
        COALESCE((SELECT group_concat(value) FROM json_each(new.reasoning_docs)), ''),
        COALESCE((SELECT group_concat(value) FROM json_each(new.tech_tags)), '')
    );
END;

CREATE TRIGGER IF NOT EXISTS sessions_fts_update AFTER UPDATE ON sessions BEGIN
    UPDATE sessions_fts SET
        task_raw = new.task_raw,
        summary_doc = new.summary_doc,
        reasoning_text = COALESCE(
            (SELECT group_concat(value) FROM json_each(new.reasoning_docs)), ''),
        tech_tags = COALESCE(
            (SELECT group_concat(value) FROM json_each(new.tech_tags)), '')
    WHERE rowid = new.rowid;
END;

CREATE TRIGGER IF NOT EXISTS sessions_fts_delete AFTER DELETE ON sessions BEGIN
    DELETE FROM sessions_fts WHERE rowid = old.rowid;
END;

CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_name);
CREATE INDEX IF NOT EXISTS idx_sessions_quality ON sessions(quality_tag);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(session_start);
CREATE INDEX IF NOT EXISTS idx_sessions_indexed ON sessions(indexed_at);
CREATE INDEX IF NOT EXISTS idx_rel_from ON session_relationships(from_session);
CREATE INDEX IF NOT EXISTS idx_rel_to ON session_relationships(to_session);
CREATE INDEX IF NOT EXISTS idx_rel_type ON session_relationships(relationship_type);
CREATE INDEX IF NOT EXISTS idx_rel_detected ON session_relationships(detected_by);
CREATE INDEX IF NOT EXISTS idx_superseded ON supersession_links(superseded_id);
CREATE INDEX IF NOT EXISTS idx_superseding ON supersession_links(superseding_id);
"""


class MetadataStore:
    """SQLite-backed metadata store for SmartFork sessions.

    Provides CRUD operations, structured queries, supersession tracking,
    relationship management, FTS5 full-text search, and sqlite-vec
    vector search. Uses WAL mode for concurrent read performance.
    """

    def __init__(self, db_path: str | Path = "~/.smartfork/metadata.db") -> None:
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._vec_available = False
        self._init_db()
        self._ensure_schema()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._get_conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.executescript(SCHEMA_SQL)
            self._try_create_vec0(conn)
            conn.commit()

    def _try_create_vec0(self, conn: sqlite3.Connection) -> None:
        """Attempt to create the sqlite-vec vec0 table.

        Logs a warning if the extension is unavailable but never crashes.
        """
        try:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS session_vectors USING vec0(
                    session_id TEXT PRIMARY KEY,
                    embedding float[1024]
                )
            """)
            self._vec_available = True
        except sqlite3.OperationalError as exc:
            logger.warning(
                f"sqlite-vec extension not available (vec0 table creation failed: {exc}). "
                "Vector operations will be disabled."
            )
            self._vec_available = False

    def _ensure_schema(self) -> None:
        """Migrate existing databases to the current schema (v4)."""
        with self._get_conn() as conn:
            cursor = conn.execute("PRAGMA user_version")
            current_version = cursor.fetchone()[0]

            if current_version < 4:
                logger.info(
                    f"Migrating database from schema v{current_version} to v4"
                )
                self._migrate_to_v4(conn)
                conn.execute("PRAGMA user_version = 4")
                conn.commit()
                logger.info("Schema v4 migration complete")

    def _migrate_to_v4(self, conn: sqlite3.Connection) -> None:
        """Migrate from schema v3 to v4.

        Steps:
        1. Ensure reasoning_docs column exists (pre-v3 databases).
        2. Create session_relationships table and indexes.
        3. Migrate supersession_links → session_relationships.
        4. Create sessions_fts and populate from existing data.
        5. Create FTS5 triggers.
        6. Create session_vectors (empty, for future population).
        """
        # 1. Ensure reasoning_docs exists for pre-v3 databases
        cursor = conn.execute("PRAGMA table_info(sessions)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "reasoning_docs" not in columns:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN reasoning_docs TEXT NOT NULL DEFAULT '[]'"
            )

        # 2. Create new relationship table and indexes
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_relationships (
                from_session TEXT NOT NULL,
                to_session TEXT NOT NULL,
                relationship_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                detected_by TEXT NOT NULL,
                reasons TEXT NOT NULL DEFAULT '[]',
                created_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (from_session, to_session, relationship_type),
                FOREIGN KEY (from_session) REFERENCES sessions(session_id) ON DELETE CASCADE,
                FOREIGN KEY (to_session) REFERENCES sessions(session_id) ON DELETE CASCADE
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rel_from ON session_relationships(from_session)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rel_to ON session_relationships(to_session)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rel_type ON session_relationships(relationship_type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rel_detected ON session_relationships(detected_by)"
        )

        # 3. Migrate supersession_links → session_relationships
        try:
            cursor = conn.execute("SELECT * FROM supersession_links")
            for row in cursor.fetchall():
                conn.execute(
                    """
                    INSERT OR IGNORE INTO session_relationships (
                        from_session, to_session, relationship_type,
                        confidence, detected_by, reasons, created_at
                    ) VALUES (?, ?, 'supersession', ?, 'heuristic', '[]', ?)
                    """,

                    (
                        row["superseded_id"],
                        row["superseding_id"],
                        row["confidence"],
                        row["detected_at"],
                    ),
                )
        except sqlite3.OperationalError:
            # supersession_links may not exist in very old databases
            pass

        # 4. Create FTS5 virtual table and populate from existing data
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
                task_raw,
                summary_doc,
                reasoning_text,
                tech_tags,
                tokenize='porter unicode61'
            )
        """)

        conn.execute("""
            INSERT OR IGNORE INTO sessions_fts(
                rowid, task_raw, summary_doc, reasoning_text, tech_tags
            )
            SELECT rowid, task_raw, summary_doc,
                   COALESCE(
                       (SELECT group_concat(value) FROM json_each(reasoning_docs)), ''
                   ),
                   COALESCE(
                       (SELECT group_concat(value) FROM json_each(tech_tags)), ''
                   )
            FROM sessions
        """)

        # 5. Create FTS5 triggers
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS sessions_fts_insert AFTER INSERT ON sessions BEGIN
                INSERT INTO sessions_fts(rowid, task_raw, summary_doc, reasoning_text, tech_tags)
                VALUES (
                    new.rowid,
                    new.task_raw,
                    new.summary_doc,
                    COALESCE(
                        (SELECT group_concat(value) FROM json_each(new.reasoning_docs)), ''),
                    COALESCE(
                        (SELECT group_concat(value) FROM json_each(new.tech_tags)), '')
                );
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS sessions_fts_update AFTER UPDATE ON sessions BEGIN
                UPDATE sessions_fts SET
                    task_raw = new.task_raw,
                    summary_doc = new.summary_doc,
                    reasoning_text = COALESCE(
                        (SELECT group_concat(value) FROM json_each(new.reasoning_docs)), ''),
                    tech_tags = COALESCE(
                        (SELECT group_concat(value) FROM json_each(new.tech_tags)), '')
                WHERE rowid = new.rowid;
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS sessions_fts_delete AFTER DELETE ON sessions BEGIN
                DELETE FROM sessions_fts WHERE rowid = old.rowid;
            END
        """)

        # 6. Create session_vectors (empty, for future population)
        self._try_create_vec0(conn)

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
                    quality_tag, tech_tags, reasoning_docs, indexed_at, schema_version
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
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
                    self._serialize_list(session.reasoning_docs),
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

    # --- Supersession (deprecated, kept for backward compatibility) ---

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

    # --- Relationship CRUD ---

    def add_relationship(self, rel: SessionRelationship) -> None:
        """Insert or replace a session relationship."""
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO session_relationships (
                    from_session, to_session, relationship_type,
                    confidence, detected_by, reasons, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rel.from_session,
                    rel.to_session,
                    rel.relationship_type,
                    rel.confidence,
                    rel.detected_by,
                    self._serialize_list(rel.reasons),
                    rel.created_at,
                ),
            )
            conn.commit()

    def get_relationships(
        self, session_id: str, direction: str = "both"
    ) -> list[SessionRelationship]:
        """Get all relationships for a session.

        Args:
            session_id: The session ID to query.
            direction: "from" (outgoing), "to" (incoming), or "both".

        Returns:
            List of SessionRelationship objects.
        """
        relationships: list[SessionRelationship] = []
        with self._get_conn() as conn:
            if direction in ("from", "both"):
                cursor = conn.execute(
                    "SELECT * FROM session_relationships WHERE from_session = ?",
                    (session_id,),
                )
                for row in cursor.fetchall():
                    relationships.append(self._row_to_relationship(row))

            if direction in ("to", "both"):
                cursor = conn.execute(
                    "SELECT * FROM session_relationships WHERE to_session = ?",
                    (session_id,),
                )
                for row in cursor.fetchall():
                    relationships.append(self._row_to_relationship(row))

        return relationships

    def get_relationships_by_type(
        self, session_id: str, rel_type: str, direction: str = "both"
    ) -> list[SessionRelationship]:
        """Get relationships of a specific type for a session.

        Args:
            session_id: The session ID to query.
            rel_type: The relationship type to filter by.
            direction: "from" (outgoing), "to" (incoming), or "both".

        Returns:
            List of SessionRelationship objects.
        """
        relationships: list[SessionRelationship] = []
        with self._get_conn() as conn:
            if direction in ("from", "both"):
                cursor = conn.execute(
                    "SELECT * FROM session_relationships "
                    "WHERE from_session = ? AND relationship_type = ?",
                    (session_id, rel_type),
                )
                for row in cursor.fetchall():
                    relationships.append(self._row_to_relationship(row))

            if direction in ("to", "both"):
                cursor = conn.execute(
                    "SELECT * FROM session_relationships "
                    "WHERE to_session = ? AND relationship_type = ?",
                    (session_id, rel_type),
                )
                for row in cursor.fetchall():
                    relationships.append(self._row_to_relationship(row))

        return relationships

    def delete_relationships_for_session(self, session_id: str) -> int:
        """Delete all relationships involving a session.

        Args:
            session_id: The session ID to remove relationships for.

        Returns:
            Number of rows deleted.
        """
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM session_relationships WHERE from_session = ? OR to_session = ?",
                (session_id, session_id),
            )
            conn.commit()
            return cursor.rowcount

    def _row_to_relationship(self, row: sqlite3.Row) -> SessionRelationship:
        """Convert a database row to SessionRelationship."""
        return SessionRelationship(
            from_session=row["from_session"],
            to_session=row["to_session"],
            relationship_type=row["relationship_type"],
            confidence=row["confidence"],
            detected_by=row["detected_by"],
            reasons=self._deserialize_list(row["reasons"]),
            created_at=row["created_at"],
        )

    # --- FTS5 Search ---

    def fts5_search(self, query: str, limit: int = 30) -> list[tuple[str, float]]:
        """Search using FTS5 BM25 ranking.

        Args:
            query: FTS5 MATCH query string.
            limit: Maximum results to return.

        Returns:
            List of (session_id, bm25_score) tuples.
        """
        results: list[tuple[str, float]] = []
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT s.session_id, bm25(sessions_fts) as score
                FROM sessions_fts
                JOIN sessions s ON s.rowid = sessions_fts.rowid
                WHERE sessions_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (query, limit),
            )
            for row in cursor.fetchall():
                results.append((row["session_id"], float(row["score"])))
        return results

    # --- sqlite-vec ---

    def store_vector(self, session_id: str, vector: list[float]) -> None:
        """Store a session's embedding vector.

        Args:
            session_id: The session identifier.
            vector: The embedding vector (1024 dimensions).
        """
        if not self._vec_available:
            logger.warning("sqlite-vec not available; store_vector is a no-op")
            return
        with self._get_conn() as conn:
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO session_vectors(session_id, embedding) VALUES (?, ?)",
                    (session_id, json.dumps(vector)),
                )
                conn.commit()
            except sqlite3.OperationalError as exc:
                logger.warning(f"store_vector failed: {exc}")

    def get_vector(self, session_id: str) -> list[float] | None:
        """Retrieve a session's embedding vector.

        Args:
            session_id: The session identifier.

        Returns:
            The embedding vector, or None if not found.
        """
        if not self._vec_available:
            logger.warning("sqlite-vec not available; get_vector returning None")
            return None
        with self._get_conn() as conn:
            try:
                row = conn.execute(
                    "SELECT embedding FROM session_vectors WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if row:
                    result: list[float] = json.loads(row["embedding"])
                    return result
            except sqlite3.OperationalError as exc:
                logger.warning(f"get_vector failed: {exc}")
        return None

    def vector_search(
        self, query_vector: list[float], limit: int = 30
    ) -> list[tuple[str, float]]:
        """Search for similar vectors using sqlite-vec.

        Args:
            query_vector: The query embedding (1024 dimensions).
            limit: Maximum results.

        Returns:
            List of (session_id, similarity) tuples.
        """
        if not self._vec_available:
            logger.warning("sqlite-vec not available; vector_search returning empty")
            return []
        results: list[tuple[str, float]] = []
        with self._get_conn() as conn:
            try:
                cursor = conn.execute(
                    """
                    SELECT session_id, distance FROM session_vectors
                    WHERE vss_search(embedding, vss_search_params(?, ?))
                    ORDER BY distance LIMIT ?
                    """,
                    (json.dumps(query_vector), limit, limit),
                )
                for row in cursor.fetchall():
                    similarity = max(0.0, 1.0 - (row["distance"] / 2.0))
                    results.append((row["session_id"], similarity))
            except sqlite3.OperationalError as exc:
                logger.warning(f"vector_search failed: {exc}")
        return results

    def delete_vector(self, session_id: str) -> None:
        """Delete a session's vector.

        Args:
            session_id: The session identifier.
        """
        if not self._vec_available:
            logger.warning("sqlite-vec not available; delete_vector is a no-op")
            return
        with self._get_conn() as conn:
            try:
                conn.execute(
                    "DELETE FROM session_vectors WHERE session_id = ?",
                    (session_id,),
                )
                conn.commit()
            except sqlite3.OperationalError as exc:
                logger.warning(f"delete_vector failed: {exc}")

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

    # --- Deserialization helpers ---

    def get_session_document(self, session_id: str) -> SessionDocument | None:
        """Retrieve a session by ID as a fully deserialized SessionDocument.

        Args:
            session_id: The session identifier.

        Returns:
            SessionDocument, or None if not found.
        """
        data = self.get_session(session_id)
        if data is None:
            return None

        return SessionDocument(
            session_id=data["session_id"],
            agent=data["agent"],
            project_name=data["project_name"],
            project_root=data.get("project_root", ""),
            session_start=data.get("session_start", 0),
            session_end=data.get("session_end", 0),
            duration_minutes=data.get("duration_minutes", 0.0),
            model_used=data.get("model_used"),
            files_edited=self._deserialize_list(data.get("files_edited", "[]")),
            files_read=self._deserialize_list(data.get("files_read", "[]")),
            files_mentioned=self._deserialize_list(data.get("files_mentioned", "[]")),
            edit_count=data.get("edit_count", 0),
            user_edit_count=data.get("user_edit_count", 0),
            final_files=self._deserialize_list(data.get("final_files", "[]")),
            domains=self._deserialize_list(data.get("domains", "[]")),
            languages=self._deserialize_list(data.get("languages", "[]")),
            layers=self._deserialize_list(data.get("layers", "[]")),
            session_pattern=data.get("session_pattern", "standard_implementation"),
            task_raw=data.get("task_raw", ""),
            reasoning_docs=self._deserialize_list(data.get("reasoning_docs", "[]")),
            summary_doc=data.get("summary_doc", ""),
            propositions=self._deserialize_list(data.get("propositions", "[]")),
            quality_tag=QualityTag(data.get("quality_tag", "unknown")),
            tech_tags=self._deserialize_list(data.get("tech_tags", "[]")),
            indexed_at=data.get("indexed_at", 0),
            schema_version=data.get("schema_version", 4),
        )

    def get_all_session_documents(
        self,
        project: str | None = None,
        domain: str | None = None,
        quality: str | None = None,
        agent: str | None = None,
        limit: int = 10_000,
    ) -> list[SessionDocument]:
        """Retrieve multiple sessions as fully deserialized SessionDocuments.

        Args:
            project: Filter by project name.
            domain: Filter by domain.
            quality: Filter by quality tag.
            agent: Filter by agent ID.
            limit: Maximum number of results.

        Returns:
            List of SessionDocument objects.
        """
        session_ids = self.get_filtered_ids(
            project=project, domain=domain, quality=quality, agent=agent, limit=limit
        )
        documents: list[SessionDocument] = []
        for sid in session_ids:
            doc = self.get_session_document(sid)
            if doc:
                documents.append(doc)
        return documents
