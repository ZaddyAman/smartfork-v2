# Phase 1 PRD: Data Model + Schema Foundation

**Phase:** 1 of 7  
**Estimated Duration:** 2-3 days  
**Priority:** Critical (blocks all other phases)  
**Dependencies:** None  

---

## 1. Overview

This phase establishes the data model and database schema foundation for the entire refactor. All other phases depend on the models and schema defined here. This phase must be completed with zero ambiguity before proceeding.

**Goal:** Create new data models, update existing models, and define the complete SQLite schema (including FTS5 and sqlite-vec virtual tables) that all subsequent phases will use.

**Success Criteria:**
- [ ] All new model files compile without errors
- [ ] SQLite schema initializes correctly (including virtual tables)
- [ ] Migration from old `supersession_links` to new `session_relationships` works
- [ ] All existing tests still pass (backward compatibility maintained where possible)
- [ ] New schema supports all use cases: single-session search, multi-session graph queries, relationship detection, timeline generation

---

## 2. New Data Models

### 2.1 `SessionRelationship` (NEW)

**File:** `src/smartfork/models/relationship.py`  
**Purpose:** Represents a directed relationship between two sessions. Replaces the flat `SupersessionLink` model.

```python
@dataclass
class SessionRelationship:
    """
    A directed relationship between two coding sessions.
    
    This model supports four types of relationships:
    - "continuation": Newer session continues work from older session
    - "supersession": Newer session makes older session obsolete
    - "branch": Parallel work that diverged from a common session
    - "related": Sessions share context but neither continues nor supersedes
    
    Attributes:
        from_session: The source session ID (older or parent)
        to_session: The target session ID (newer or child)
        relationship_type: One of "continuation", "supersession", "branch", "related"
        confidence: 0.0 to 1.0, probability that this relationship exists
        detected_by: "explicit" (from adapter metadata), "heuristic" (computed), or "llm_verified"
        reasons: List of strings explaining why this relationship was detected
        created_at: Unix timestamp in milliseconds when relationship was stored
    """
    from_session: str
    to_session: str
    relationship_type: str
    confidence: float
    detected_by: str
    reasons: list[str]
    created_at: int = 0
```

**Validation Rules:**
- `from_session` != `to_session` (no self-relationships)
- `relationship_type` must be one of: `"continuation"`, `"supersession"`, `"branch"`, `"related"`
- `confidence` must be in range [0.0, 1.0]
- `detected_by` must be one of: `"explicit"`, `"heuristic"`, `"llm_verified"`
- `created_at` must be > 0 (milliseconds since epoch)

**Export:** Add to `src/smartfork/models/__init__.py`

---

### 2.2 `Chain` (NEW)

**File:** `src/smartfork/models/relationship.py`  
**Purpose:** Represents an ordered sequence of related sessions forming a work chain.

```python
@dataclass
class Chain:
    """
    An ordered sequence of related sessions forming a continuous work chain.
    
    Example chain:
        Session A (Mar 1) → Session B (Mar 15) → Session C (Apr 2)
        All about "auth system" work, with A superseded by B, B by C.
    
    Attributes:
        sessions: Ordered list of SessionDocument objects (oldest first)
        chain_type: "linear" (A→B→C), "branched" (A→B and A→D), or "merged"
        head_session_id: First session in the chain (oldest)
        tail_session_id: Last session in the chain (most recent)
    """
    sessions: list[SessionDocument]
    chain_type: str
    head_session_id: str
    tail_session_id: str
```

**Validation Rules:**
- `chain_type` must be one of: `"linear"`, `"branched"`, `"merged"`
- `sessions` must have at least 1 element
- `head_session_id` == `sessions[0].session_id`
- `tail_session_id` == `sessions[-1].session_id`

---

### 2.3 `TimelineEntry` (NEW)

**File:** `src/smartfork/models/relationship.py`  
**Purpose:** A single point in a session timeline for display/synthesis.

```python
@dataclass
class TimelineEntry:
    """
    A single entry in a multi-session timeline view.
    
    Attributes:
        session_id: The session identifier
        timestamp: Session start time in milliseconds
        task: The task_raw (shortened if needed)
        quality_tag: The quality tag (solution_found, dead_end, partial, etc.)
        summary: Brief summary of what happened in this session
        relationship_to_next: How this connects to the next session in chain
                             (e.g., "superseded_by", "continued_in", "branched_to")
    """
    session_id: str
    timestamp: int
    task: str
    quality_tag: str
    summary: str
    relationship_to_next: str | None = None
```

---

### 2.4 `TimelineSummary` (NEW)

**File:** `src/smartfork/models/relationship.py`  
**Purpose:** Human-readable synthesis of a session chain for deep mode display.

```python
@dataclass
class TimelineSummary:
    """
    The complete output of MultiSessionSynthesizer for display.
    
    Attributes:
        narrative: Human-readable paragraph summarizing the journey
        timeline: Structured timeline entries
        suggested_fork_session_id: Which session to fork from (usually the latest)
        resolution_status: Overall status of the work chain
                        "solved" | "ongoing" | "dead_end" | "mixed"
    """
    narrative: str
    timeline: list[TimelineEntry]
    suggested_fork_session_id: str | None = None
    resolution_status: str = "unknown"
```

**Validation Rules:**
- `resolution_status` must be one of: `"solved"`, `"ongoing"`, `"dead_end"`, `"mixed"`, `"unknown"`
- `timeline` must have at least 1 entry
- `suggested_fork_session_id` should be the tail of the primary chain

---

### 2.5 `QueryInterpretation` (NEW)

**File:** `src/smartfork/models/query.py`  
**Purpose:** Structured output from QueryInterpreter containing all search parameters.

```python
@dataclass
class QueryInterpretation:
    """
    The complete structured interpretation of a user's natural language query.
    
    This is the single source of truth for how the search pipeline should
    process a query. Created by QueryInterpreter (1 LLM structured call).
    
    Attributes:
        original_query: The raw user query (preserved for reference)
        keywords: Extracted technical keywords (e.g., ["jwt", "auth", "bug"])
        synonyms: Expanded terms from synonym dictionary
        expanded_query: The query string to pass to FTS5 (keywords + synonyms
                       formatted for MATCH syntax)
        temporal_filter: Optional time range filter (e.g., last_week, yesterday)
        intent: Detected search intent category
        project_hint: If query mentions a specific project name
        multi_session_confidence: 0.0-1.0 probability that this is a multi-session query
        needs_deep_mode: True if confidence > 0.75 or --deep flag passed
        quality_boost: Quality tags to boost in ranking (e.g., ["solution_found"])
    """
    original_query: str
    keywords: list[str] = field(default_factory=list)
    synonyms: list[str] = field(default_factory=list)
    expanded_query: str = ""
    temporal_filter: dict[str, Any] | None = None
    intent: str = "unknown"
    project_hint: str | None = None
    multi_session_confidence: float = 0.0
    needs_deep_mode: bool = False
    quality_boost: list[str] = field(default_factory=list)
```

**Intent Values:**
- `"solution_hunting"`: User wants to find how something was solved
- `"error_recall"`: User wants to find past errors/debugging sessions
- `"continuation"`: User wants to continue previous work
- `"temporal_lookup"`: User references time ("last week", "yesterday")
- `"decision_hunting"`: User wants to understand why a decision was made
- `"implementation_lookup"`: User wants to see how something was built
- `"vague_memory"`: Query is too vague to classify (default fallback)

**Temporal Filter Format:**
```python
{
    "type": "relative",  # or "absolute"
    "value": "last_week",  # or "2026-05-01", "yesterday", etc.
    "start_ms": 1716480000000,  # Optional: absolute start timestamp
    "end_ms": 1717084800000,    # Optional: absolute end timestamp
}
```

**Export:** Add to `src/smartfork/models/__init__.py`

---

### 2.6 `SessionEnrichment` (NEW)

**File:** `src/smartfork/models/enrichment.py`  
**Purpose:** Output from the refactored IndexIntelligence (1 structured LLM call).

```python
@dataclass
class SessionEnrichment:
    """
    The result of a single structured LLM call during indexing.
    
    Replaces the previous 5 separate LLM calls with 1 structured call
    that returns all enrichment fields simultaneously.
    
    Attributes:
        title: Refined task title (max 80 chars)
        summary: 3-sentence summary of the session
        quality_tag: One of "solution_found", "dead_end", "partial", "reference"
        tech_tags: List of technologies/frameworks mentioned
    """
    title: str
    summary: str
    quality_tag: str  # "solution_found" | "dead_end" | "partial" | "reference"
    tech_tags: list[str]
```

**Validation Rules:**
- `quality_tag` must be one of the four valid values
- `title` max 80 characters (truncate if longer)
- `summary` max 500 characters (truncate if longer)
- `tech_tags` deduplicated, sorted alphabetically

---

## 3. Updated Existing Models

### 3.1 `RawSessionData` — Add Relationship Fields

**File:** `src/smartfork/models/session.py`  
**Changes:**

Add after `extra: dict[str, Any] = field(default_factory=dict)`:

```python
    # NEW FIELDS for relationship tracking
    parent_id: str | None = None
    """Explicit parent session ID from adapter metadata (e.g., OpenCode)."""
    
    previous_session_id: str | None = None
    """Explicit chain predecessor from adapter metadata."""
```

**Backward Compatibility:** Default to `None`. Existing adapters that don't set these will continue to work.

---

### 3.2 `SessionDocument` — Add Relationship Fields

**File:** `src/smartfork/models/session.py`  
**Changes:**

Add before `schema_version` field:

```python
    # NEW FIELDS for relationship tracking
    parent_id: str | None = None
    """Explicit parent session ID (from adapter, if available)."""
    
    previous_session_id: str | None = None
    """Explicit chain predecessor (from adapter, if available)."""
```

**Note:** These fields are NOT persisted in the SQLite `sessions` table directly. They are used during indexing for relationship detection, then the relationships are stored in `session_relationships` table.

**Rationale:** The sessions table stores session metadata. Relationships are a separate concern stored in their own table with foreign keys. The `parent_id` in SessionDocument is only used during the indexing pipeline's relationship detection phase.

---

## 4. Database Schema

### 4.1 Complete SQLite Schema

**File:** `src/smartfork/indexer/metadata_store.py` — Replace `SCHEMA_SQL` constant  
**Database:** `~/.smartfork/metadata.db`  
**Mode:** WAL (Write-Ahead Logging) for concurrent reads

```sql
-- Main sessions table (existing, extended reasoning_docs)
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
    schema_version INTEGER NOT NULL DEFAULT 4  -- BUMPED to 4
);

-- NEW: Session relationships (replaces supersession_links)
-- Supports continuation, supersession, branch, related
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

-- DEPRECATED: Keep for migration, remove in Phase 6
-- Will be migrated to session_relationships with type="supersession"
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

-- FTS5 virtual table for full-text search
-- Replaces in-memory BM25 rebuild on every query
CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
    task_raw,
    summary_doc,
    reasoning_text,
    tech_tags,
    content='sessions',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

-- sqlite-vec virtual table for vector embeddings
-- Replaces ChromaDB
CREATE VIRTUAL TABLE IF NOT EXISTS session_vectors USING vec0(
    session_id TEXT PRIMARY KEY,
    embedding float[1024]
);

-- Indexes on main table
CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_name);
CREATE INDEX IF NOT EXISTS idx_sessions_quality ON sessions(quality_tag);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(session_start);
CREATE INDEX IF NOT EXISTS idx_sessions_indexed ON sessions(indexed_at);

-- Indexes on relationship table
CREATE INDEX IF NOT EXISTS idx_rel_from ON session_relationships(from_session);
CREATE INDEX IF NOT EXISTS idx_rel_to ON session_relationships(to_session);
CREATE INDEX IF NOT EXISTS idx_rel_type ON session_relationships(relationship_type);
CREATE INDEX IF NOT EXISTS idx_rel_detected ON session_relationships(detected_by);

-- Indexes on deprecated table (for migration)
CREATE INDEX IF NOT EXISTS idx_superseded ON supersession_links(superseded_id);
CREATE INDEX IF NOT EXISTS idx_superseding ON supersession_links(superseding_id);
```

### 4.2 FTS5 Triggers

**Purpose:** Keep FTS5 index in sync with sessions table automatically.

```sql
-- Trigger: INSERT into sessions → INSERT into sessions_fts
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

-- Trigger: UPDATE on sessions → UPDATE sessions_fts
CREATE TRIGGER IF NOT EXISTS sessions_fts_update AFTER UPDATE ON sessions BEGIN
    UPDATE sessions_fts SET
        task_raw = new.task_raw,
        summary_doc = new.summary_doc,
        reasoning_text = COALESCE((SELECT group_concat(value) FROM json_each(new.reasoning_docs)), ''),
        tech_tags = COALESCE((SELECT group_concat(value) FROM json_each(new.tech_tags)), '')
    WHERE rowid = new.rowid;
END;

-- Trigger: DELETE from sessions → DELETE from sessions_fts
CREATE TRIGGER IF NOT EXISTS sessions_fts_delete AFTER DELETE ON sessions BEGIN
    DELETE FROM sessions_fts WHERE rowid = old.rowid;
END;
```

**Note:** If FTS5 triggers with JSON functions don't work reliably across SQLite versions, implement manual FTS5 sync in Python within `MetadataStore.upsert_session()` and `MetadataStore.delete_session()`.

---

### 4.3 Schema Migration Logic

**File:** `src/smartfork/indexer/metadata_store.py` — `_ensure_schema()` method  
**Purpose:** Migrate existing databases from schema v3 to v4.

```python
def _ensure_schema(self) -> None:
    """Migrate existing databases to current schema (v4)."""
    with self._get_conn() as conn:
        cursor = conn.execute("PRAGMA table_info(sessions)")
        columns = {row["name"] for row in cursor.fetchall()}
        
        # Check current schema version
        cursor = conn.execute("PRAGMA user_version")
        current_version = cursor.fetchone()[0]
        
        if current_version < 4:
            logger.info(f"Migrating database from schema v{current_version} to v4")
            self._migrate_to_v4(conn)
            conn.execute("PRAGMA user_version = 4")
            conn.commit()

def _migrate_to_v4(self, conn: sqlite3.Connection) -> None:
    """Migrate from schema v3 to v4."""
    # 1. Create new tables
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
    
    # 2. Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rel_from ON session_relationships(from_session)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rel_to ON session_relationships(to_session)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rel_type ON session_relationships(relationship_type)")
    
    # 3. Migrate supersession_links → session_relationships
    cursor = conn.execute("SELECT * FROM supersession_links")
    for row in cursor.fetchall():
        conn.execute("""
            INSERT OR IGNORE INTO session_relationships
            (from_session, to_session, relationship_type, confidence, detected_by, reasons, created_at)
            VALUES (?, ?, 'supersession', ?, 'heuristic', '[]', ?)
        """, (row["superseded_id"], row["superseding_id"], row["confidence"], row["detected_at"]))
    
    # 4. Create FTS5 virtual table
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
            task_raw, summary_doc, reasoning_text, tech_tags,
            content='sessions', content_rowid='rowid',
            tokenize='porter unicode61'
        )
    """)
    
    # 5. Populate FTS5 from existing data
    conn.execute("""
        INSERT INTO sessions_fts(rowid, task_raw, summary_doc, reasoning_text, tech_tags)
        SELECT rowid, task_raw, summary_doc, 
               COALESCE((SELECT group_concat(value) FROM json_each(reasoning_docs)), ''),
               COALESCE((SELECT group_concat(value) FROM json_each(tech_tags)), '')
        FROM sessions
    """)
    
    # 6. Create sqlite-vec virtual table
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS session_vectors USING vec0(
            session_id TEXT PRIMARY KEY,
            embedding float[1024]
        )
    """)
    
    logger.info("Schema v4 migration complete")
```

---

## 5. MetadataStore CRUD Methods (New)

### 5.1 Relationship CRUD

**Add to `src/smartfork/indexer/metadata_store.py`:**

```python
def add_relationship(self, rel: SessionRelationship) -> None:
    """Insert or replace a session relationship."""
    with self._get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO session_relationships
            (from_session, to_session, relationship_type, confidence, detected_by, reasons, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            rel.from_session,
            rel.to_session,
            rel.relationship_type,
            rel.confidence,
            rel.detected_by,
            self._serialize_list(rel.reasons),
            rel.created_at,
        ))
        conn.commit()

def get_relationships(self, session_id: str, direction: str = "both") -> list[SessionRelationship]:
    """Get all relationships for a session.
    
    Args:
        session_id: The session ID to query.
        direction: "from" (outgoing), "to" (incoming), or "both".
    """
    relationships = []
    with self._get_conn() as conn:
        if direction in ("from", "both"):
            cursor = conn.execute(
                "SELECT * FROM session_relationships WHERE from_session = ?",
                (session_id,)
            )
            for row in cursor.fetchall():
                relationships.append(self._row_to_relationship(row))
        
        if direction in ("to", "both"):
            cursor = conn.execute(
                "SELECT * FROM session_relationships WHERE to_session = ?",
                (session_id,)
            )
            for row in cursor.fetchall():
                relationships.append(self._row_to_relationship(row))
    
    return relationships

def get_relationships_by_type(
    self, session_id: str, rel_type: str, direction: str = "both"
) -> list[SessionRelationship]:
    """Get relationships of a specific type."""
    relationships = []
    with self._get_conn() as conn:
        if direction in ("from", "both"):
            cursor = conn.execute(
                "SELECT * FROM session_relationships WHERE from_session = ? AND relationship_type = ?",
                (session_id, rel_type)
            )
            for row in cursor.fetchall():
                relationships.append(self._row_to_relationship(row))
        
        if direction in ("to", "both"):
            cursor = conn.execute(
                "SELECT * FROM session_relationships WHERE to_session = ? AND relationship_type = ?",
                (session_id, rel_type)
            )
            for row in cursor.fetchall():
                relationships.append(self._row_to_relationship(row))
    
    return relationships

def delete_relationships_for_session(self, session_id: str) -> int:
    """Delete all relationships involving a session (cascade handled by FK)."""
    with self._get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM session_relationships WHERE from_session = ? OR to_session = ?",
            (session_id, session_id)
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
```

---

### 5.2 FTS5 Search Methods

**Add to `src/smartfork/indexer/metadata_store.py`:**

```python
def fts5_search(self, query: str, limit: int = 30) -> list[tuple[str, float]]:
    """Search using FTS5 BM25 ranking.
    
    Args:
        query: FTS5 MATCH query string (already expanded with synonyms).
        limit: Maximum results to return.
    
    Returns:
        List of (session_id, bm25_score) tuples.
        Score is negated BM25 (lower is better in FTS5), so we return
        the raw bm25 value for RRF fusion.
    """
    results = []
    with self._get_conn() as conn:
        cursor = conn.execute(
            "SELECT rowid, session_id, bm25(sessions_fts) as score "
            "FROM sessions_fts WHERE sessions_fts MATCH ? "
            "ORDER BY score LIMIT ?",
            (query, limit)
        )
        for row in cursor.fetchall():
            results.append((row["session_id"], row["score"]))
    return results
```

---

### 5.3 sqlite-vec Methods

**Add to `src/smartfork/indexer/metadata_store.py`:**

```python
def store_vector(self, session_id: str, vector: list[float]) -> None:
    """Store a session's embedding vector."""
    with self._get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO session_vectors(session_id, embedding) VALUES (?, ?)",
            (session_id, json.dumps(vector))
        )
        conn.commit()

def get_vector(self, session_id: str) -> list[float] | None:
    """Retrieve a session's embedding vector."""
    with self._get_conn() as conn:
        row = conn.execute(
            "SELECT embedding FROM session_vectors WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        if row:
            return json.loads(row["embedding"])
        return None

def vector_search(self, query_vector: list[float], limit: int = 30) -> list[tuple[str, float]]:
    """Search for similar vectors using sqlite-vec.
    
    Args:
        query_vector: The query embedding (1024 dimensions).
        limit: Maximum results.
    
    Returns:
        List of (session_id, distance) tuples.
        Distance is converted to similarity: 1.0 - (distance / 2.0)
    """
    results = []
    with self._get_conn() as conn:
        # sqlite-vec uses vss_search for KNN
        cursor = conn.execute(
            "SELECT session_id, distance FROM session_vectors "
            "WHERE vss_search(embedding, vss_search_params(?, ?))"
            "ORDER BY distance LIMIT ?",
            (json.dumps(query_vector), limit, limit)
        )
        for row in cursor.fetchall():
            # Convert distance to similarity
            similarity = max(0.0, 1.0 - (row["distance"] / 2.0))
            results.append((row["session_id"], similarity))
    return results

def delete_vector(self, session_id: str) -> None:
    """Delete a session's vector."""
    with self._get_conn() as conn:
        conn.execute(
            "DELETE FROM session_vectors WHERE session_id = ?",
            (session_id,)
        )
        conn.commit()
```

**Note:** sqlite-vec syntax may vary. Check exact API. If `vss_search` syntax is different, adjust accordingly.

---

## 6. Model Exports

**File:** `src/smartfork/models/__init__.py`  
**Add these exports:**

```python
from smartfork.models.relationship import (
    SessionRelationship,
    Chain,
    TimelineEntry,
    TimelineSummary,
)
from smartfork.models.query import QueryInterpretation
from smartfork.models.enrichment import SessionEnrichment
```

---

## 7. Testing Requirements

### 7.1 Unit Tests — New Models

**File:** `tests/models/test_relationship.py` (NEW)

```python
"""Tests for relationship models."""

import pytest
from smartfork.models.relationship import SessionRelationship, Chain, TimelineEntry, TimelineSummary
from smartfork.models.session import SessionDocument


class TestSessionRelationship:
    def test_basic_creation(self):
        rel = SessionRelationship(
            from_session="A",
            to_session="B",
            relationship_type="supersession",
            confidence=0.92,
            detected_by="heuristic",
            reasons=["file_overlap", "temporal_proximity"],
            created_at=1716480000000,
        )
        assert rel.from_session == "A"
        assert rel.confidence == 0.92
    
    def test_invalid_relationship_type(self):
        # Should raise ValueError or similar
        with pytest.raises((ValueError, AssertionError)):
            SessionRelationship(
                from_session="A",
                to_session="B",
                relationship_type="invalid_type",
                confidence=0.5,
                detected_by="heuristic",
                reasons=[],
            )
    
    def test_confidence_range(self):
        # Confidence must be 0.0-1.0
        with pytest.raises((ValueError, AssertionError)):
            SessionRelationship(
                from_session="A",
                to_session="B",
                relationship_type="continuation",
                confidence=1.5,  # Invalid
                detected_by="explicit",
                reasons=[],
            )
```

**File:** `tests/models/test_query.py` (NEW)

```python
"""Tests for query interpretation model."""

import pytest
from smartfork.models.query import QueryInterpretation


class TestQueryInterpretation:
    def test_basic_creation(self):
        qi = QueryInterpretation(
            original_query="what happened with auth",
            keywords=["auth"],
            synonyms=["authentication", "login"],
            expanded_query="auth OR authentication OR login",
            intent="temporal_lookup",
            multi_session_confidence=0.92,
            needs_deep_mode=True,
        )
        assert qi.needs_deep_mode is True
        assert qi.multi_session_confidence == 0.92
    
    def test_default_values(self):
        qi = QueryInterpretation(original_query="jwt bug")
        assert qi.keywords == []
        assert qi.multi_session_confidence == 0.0
        assert qi.needs_deep_mode is False
```

### 7.2 Integration Tests — Schema

**File:** `tests/indexer/test_schema_migration.py` (NEW)

```python
"""Tests for database schema creation and migration."""

import tempfile
from pathlib import Path
from smartfork.indexer.metadata_store import MetadataStore


class TestSchemaMigration:
    def test_fresh_database_creates_all_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = MetadataStore(db_path=db_path)
            
            # Check all tables exist
            with store._get_conn() as conn:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                tables = {row["name"] for row in cursor.fetchall()}
            
            assert "sessions" in tables
            assert "session_relationships" in tables
            assert "supersession_links" in tables  # Kept for migration
            assert "sessions_fts" in tables
            assert "session_vectors" in tables
    
    def test_v3_to_v4_migration(self):
        # Create a v3 database, then verify migration
        pass  # Implementation needed
```

---

## 8. Deliverables

| # | Deliverable | File(s) | Acceptance Criteria |
|---|-------------|---------|-------------------|
| 1 | `SessionRelationship` model | `models/relationship.py` | Tests pass, validates correctly |
| 2 | `QueryInterpretation` model | `models/query.py` | Tests pass, all intent values supported |
| 3 | `SessionEnrichment` model | `models/enrichment.py` | Tests pass, quality_tag validated |
| 4 | Updated `RawSessionData` | `models/session.py` | parent_id field present, defaults to None |
| 5 | Updated `SessionDocument` | `models/session.py` | parent_id field present, defaults to None |
| 6 | Schema SQL | `indexer/metadata_store.py` | All tables created, indexes present, WAL mode |
| 7 | FTS5 triggers | `indexer/metadata_store.py` | Auto-sync on INSERT/UPDATE/DELETE |
| 8 | Migration logic | `indexer/metadata_store.py` | v3→v4 migration works, data preserved |
| 9 | Relationship CRUD | `indexer/metadata_store.py` | add/get/delete relationships works |
| 10 | FTS5 search method | `indexer/metadata_store.py` | Returns ranked results |
| 11 | sqlite-vec methods | `indexer/metadata_store.py` | Store/get/search vectors works |
| 12 | Model exports | `models/__init__.py` | All new models exported |
| 13 | Tests | `tests/models/`, `tests/indexer/` | All new tests pass |

---

## 9. Dependencies on Other Phases

| Dependency | Phase | Nature |
|------------|-------|--------|
| None | — | This phase is foundational |

**Phases blocked by this one:**
- Phase 2 (Adapter Layer) — needs `parent_id` field in `RawSessionData`
- Phase 3 (Indexing) — needs `SessionRelationship`, `SessionEnrichment`, schema
- Phase 4 (Search) — needs `QueryInterpretation`, FTS5, sqlite-vec
- Phase 5 (Multi-Session) — needs `Chain`, `TimelineEntry`, `TimelineSummary`

---

## 10. Notes for Implementer

1. **Schema version bump:** Change `schema_version` default from 3 to 4 in sessions table.
2. **WAL mode:** Ensure `PRAGMA journal_mode=WAL;` is set on every connection.
3. **Foreign keys:** Ensure `PRAGMA foreign_keys=ON;` is set on every connection.
4. **sqlite-vec compatibility:** Test on the actual environment. sqlite-vec may require a specific SQLite version or extension loading mechanism.
5. **FTS5 population:** For existing databases, the migration must populate `sessions_fts` from existing data.
6. **Backward compatibility:** `SupersessionLink` model should NOT be deleted yet — keep it in models but deprecate. Remove in Phase 6.
7. **JSON fields:** All list fields in SQLite are stored as JSON strings. The `_serialize_list` and `_deserialize_list` helpers already exist in MetadataStore.
8. **vec0 syntax:** sqlite-vec uses `vec0` virtual table. The exact syntax for `vss_search` may differ from the example above. Verify against sqlite-vec documentation.
