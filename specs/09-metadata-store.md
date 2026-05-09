# SmartFork v2 — SQLite Metadata Store (Layer 5)

> **Design:** SQLite for structured queries. Provides hard filtering BEFORE vector search — eliminates 80-90% of index before embedding computation.

---

## Schema

**File:** `src/smartfork/database/metadata_store.py`

```sql
CREATE TABLE IF NOT EXISTS sessions (
    session_id       TEXT PRIMARY KEY,
    agent            TEXT NOT NULL,
    project_name     TEXT NOT NULL,
    project_root     TEXT,
    session_start    INTEGER,
    session_end      INTEGER,
    duration_minutes REAL,
    model_used       TEXT,
    
    -- Quality & tags
    quality_tag      TEXT DEFAULT 'unknown',
    tech_tags        TEXT DEFAULT '[]',
    resolution_status TEXT DEFAULT 'unknown',
    had_errors       INTEGER DEFAULT 0,
    
    -- File signals (JSON arrays stored as TEXT)
    files_edited     TEXT DEFAULT '[]',
    files_read       TEXT DEFAULT '[]',
    files_mentioned  TEXT DEFAULT '[]',
    edit_count       INTEGER DEFAULT 0,
    user_edit_count  INTEGER DEFAULT 0,
    final_files      TEXT DEFAULT '[]',
    
    -- Derived (JSON arrays)
    domains          TEXT DEFAULT '[]',
    languages        TEXT DEFAULT '[]',
    layers           TEXT DEFAULT '[]',
    session_pattern  TEXT DEFAULT 'standard_implementation',
    
    -- Content
    title            TEXT DEFAULT '',
    task_raw         TEXT DEFAULT '',
    summary_doc      TEXT DEFAULT '',
    reasoning_docs   TEXT DEFAULT '[]',
    propositions     TEXT DEFAULT '[]',
    
    indexed_at       INTEGER,
    schema_version   INTEGER DEFAULT 2
);

CREATE TABLE IF NOT EXISTS session_supersessions (
    superseded_id  TEXT NOT NULL,
    superseding_id TEXT NOT NULL,
    confidence     REAL NOT NULL,
    detected_at    INTEGER NOT NULL,
    reason         TEXT DEFAULT '',
    PRIMARY KEY (superseded_id, superseding_id)
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_name);
CREATE INDEX IF NOT EXISTS idx_sessions_quality ON sessions(quality_tag);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(session_start);
CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent);
```

---

## MetadataStore API

```python
class MetadataStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    # CRUD
    def upsert_session(self, doc: SessionDocument) -> None: ...
    def get_session(self, session_id: str) -> Optional[SessionDocument]: ...
    def delete_session(self, session_id: str) -> None: ...
    
    # Query
    def get_session_count(self) -> int: ...
    def get_unique_projects(self) -> List[str]: ...
    def get_unique_agents(self) -> List[str]: ...
    def get_sessions_by_project(self, project: str, limit: int = 100) -> List[SessionDocument]: ...
    def get_sessions_by_domain(self, domain: str, limit: int = 100) -> List[SessionDocument]: ...
    def get_sessions_by_quality(self, tag: str, limit: int = 100) -> List[SessionDocument]: ...
    def get_all_session_ids(self) -> List[str]: ...
    
    # Supersession
    def add_supersession_link(self, link: SupersessionLink) -> None: ...
    def get_superseding_sessions(self, session_id: str) -> List[Tuple[str, float, int]]: ...
    def get_superseded_by(self, session_id: str) -> List[Tuple[str, float, int]]: ...
    
    # Stats
    def get_stats(self) -> dict:
        """Returns: total_sessions, total_projects, quality_breakdown, agent_breakdown"""
    
    # Filtering (for pre-search hard filter)
    def get_filtered_ids(self, 
                         project: str = None,
                         quality: str = None,
                         agent: str = None,
                         days: int = None,
                         domain: str = None) -> List[str]:
        """Get session IDs matching filters. Used BEFORE vector/BM25 search."""
```

---

## upsert_session() — JSON Serialization

List fields (files_edited, domains, languages, layers, tech_tags, reasoning_docs, propositions) are stored as JSON arrays in TEXT columns.

```python
import json

def _serialize_list(lst: List[str]) -> str:
    return json.dumps(lst)

def _deserialize_list(text: str) -> List[str]:
    return json.loads(text) if text else []
```

On upsert: serialize all lists. On read: deserialize all lists.

---

## Performance Design

- **WAL mode** for concurrent reads during indexing
- **Indexes** on query-common columns (project, quality, start time, agent)
- **Batch upsert**: `executemany()` for bulk indexing
- JSON stored as TEXT (SQLite has no native JSON type) — trade simplicity for query speed on JSON fields
- Filter first (SQL WHERE), then vector search (ChromaDB) on remaining IDs

---

## Connection Management

```python
import sqlite3

def _get_conn(self):
    conn = sqlite3.connect(str(self.db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
```

Short-lived connections (open, execute, close). Not pooled. SQLite is single-writer anyway.

---

## Testing

- Test upsert → get roundtrip (all fields survive)
- Test JSON serialization of empty lists
- Test WAL mode is enabled
- Test foreign key constraint on supersession table
- Test get_filtered_ids with combinations of filters
- Test with 10,000 sessions (performance)
