# Phase 2 PRD: Adapter Layer

**Phase:** 2 of 7  
**Estimated Duration:** 1 day  
**Priority:** High  
**Dependencies:** Phase 1 (Data Model + Schema)  

---

## 1. Overview

This phase fixes the adapter layer to preserve hierarchy metadata from raw session data and prepares the interface for relationship detection. The primary work is in the OpenCode adapter (which currently discards `parent_id`) and updating the `SessionParser` to propagate this field.

**Goal:**
- Stop discarding `parent_id` from OpenCode adapter
- Update `SessionParser` to include `parent_id` in `SessionDocument`
- Leave KiloCode/ClaudeCode/AntiGravity adapters unchanged (they don't have explicit hierarchy)

**Success Criteria:**
- [ ] OpenCode adapter passes `parent_id` from SQLite to `RawSessionData`
- [ ] `SessionParser` includes `parent_id` in `SessionDocument`
- [ ] Existing tests for OpenCode adapter still pass
- [ ] New test: OpenCode session with `parent_id` produces `SessionDocument` with `parent_id`

---

## 2. Changes by File

### 2.1 `src/smartfork/adapters/opencode.py`

**Current behavior (BROKEN):**
```python
# Line 89: Query reads parent_id
SELECT id, project_id, parent_id, slug, directory, title, ...

# But at line 98: Never used
cursor.fetchall() → row["parent_id"] exists but is never assigned
```

**Required fix:** Pass `parent_id` into `RawSessionData` at the point where sessions are constructed (around line 155-174).

**Specific change:**

In `parse_raw()` method, inside the `for row in cur.fetchall():` loop:

```python
# EXISTING CODE (lines ~98-103):
session_id = row["id"]
session_dir = row["directory"] or ""
title = row["title"] or ""
time_created = row["time_created"] or 0
time_updated = row["time_updated"] or 0
model_used = row["model"] or "opencode"

# ADD THIS LINE:
parent_id = row.get("parent_id") or None
```

Then at the `RawSessionData` construction (around line 155-174):

```python
# EXISTING CODE:
sessions.append(
    RawSessionData(
        session_id=session_id,
        agent_id=self.agent_id,
        session_path=Path(session_dir),
        turns=turns,
        ...
        session_start=time_created,
        session_end=time_updated,
    )
)

# CHANGE TO:
sessions.append(
    RawSessionData(
        session_id=session_id,
        agent_id=self.agent_id,
        session_path=Path(session_dir),
        turns=turns,
        files_edited=list(set(files_edited))[:20],
        files_read=list(set(files_read))[:20],
        files_mentioned=[],
        files_user_edited=[],
        final_files=[],
        workspace_dir=session_dir,
        task_raw=task_raw,
        model_used=model_used,
        session_start=time_created,
        session_end=time_updated,
        edit_count=len(set(files_edited)),
        user_edit_count=0,
        parent_id=parent_id,  # NEW FIELD
    )
)
```

**Why this matters:**
- OpenCode's SQLite schema already has `parent_id` in the `session` table
- This represents the user's explicit "continue from previous session" action
- Without this, we lose the most reliable source of session hierarchy
- The relationship detector in Phase 3 will use this as Tier 1 (explicit) data

---

### 2.2 `src/smartfork/indexer/parser.py`

**Current behavior:** `parse_session()` creates `SessionDocument` but does NOT populate `parent_id`.

**Required fix:** Pass `parent_id` from `RawSessionData` to `SessionDocument`.

**Specific change:**

In `SessionParser.parse_session()`, around the `SessionDocument(...)` construction:

```python
# EXISTING CODE:
doc = SessionDocument(
    session_id=raw.session_id,
    agent=raw.agent_id,
    project_name=project_name,
    project_root=project_root,
    session_start=raw.session_start,
    session_end=raw.session_end,
    duration_minutes=duration_minutes,
    model_used=raw.model_used,
    files_edited=raw.files_edited,
    files_read=raw.files_read,
    files_mentioned=raw.files_mentioned,
    files_user_edited=raw.files_user_edited,
    edit_count=raw.edit_count,
    user_edit_count=raw.user_edit_count,
    final_files=raw.final_files,
    domains=domains,
    languages=languages,
    layers=layers,
    session_pattern=session_pattern,
    task_raw=task_raw,
    reasoning_docs=reasoning_docs,
    summary_doc="",
    propositions=[],
    quality_tag=QualityTag.UNKNOWN,
    tech_tags=[],
    indexed_at=0,
    schema_version=3,
)

# ADD parent_id:
doc = SessionDocument(
    ...
    schema_version=3,
    parent_id=raw.parent_id,  # NEW FIELD
    previous_session_id=raw.previous_session_id,  # NEW FIELD
)
```

**Note:** `previous_session_id` is also passed for future adapters that might have chain IDs different from `parent_id`.

---

### 2.3 No Changes Needed

The following files do NOT need changes in this phase:

| File | Reason |
|------|--------|
| `adapters/kilocode.py` | No hierarchy metadata in raw data |
| `adapters/claudecode.py` | No hierarchy metadata in raw data |
| `adapters/antigravity.py` | Inherits from KiloCode, same reason |
| `adapters/cursor_agent.py` | Placeholder, returns None |
| `adapters/gemini.py` | Placeholder, returns None |
| `adapters/cline.py` | Placeholder, returns None |
| `adapters/base.py` | Interface already supports `parent_id` via `extra` or model |

---

## 3. Data Flow After Changes

```
OpenCode SQLite Database
    session table:
        id: "sess_001"
        parent_id: null
        
        id: "sess_002"
        parent_id: "sess_001"  ← This was discarded, now preserved
        
        id: "sess_003"
        parent_id: "sess_002"

OpenCodeAdapter.get_all_sessions_from_db()
    ↓
RawSessionData(session_id="sess_002", parent_id="sess_001")
    ↓
SessionParser.parse_session()
    ↓
SessionDocument(session_id="sess_002", parent_id="sess_001")
    ↓
RelationshipDetector.detect_explicit()
    ↓
SessionRelationship(
    from_session="sess_001",
    to_session="sess_002",
    relationship_type="continuation",
    confidence=1.0,
    detected_by="explicit"
)
    ↓
MetadataStore.add_relationship() → session_relationships table
```

---

## 4. Testing Requirements

### 4.1 Test OpenCode Adapter Parent ID Preservation

**File:** `tests/adapters/test_opencode.py` (NEW or extend existing)

```python
"""Tests for OpenCode adapter parent_id preservation."""

import sqlite3
import tempfile
from pathlib import Path
from smartfork.adapters.opencode import OpenCodeAdapter
from smartfork.models.session import RawSessionData


class TestOpenCodeParentId:
    def test_session_with_parent_id(self):
        """Verify that parent_id from SQLite is preserved in RawSessionData."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "opencode.db"
            
            # Create minimal OpenCode database
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE session (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    parent_id TEXT,
                    directory TEXT,
                    title TEXT,
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
                    time_created INTEGER,
                    data TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE part (
                    id TEXT PRIMARY KEY,
                    message_id TEXT,
                    time_created INTEGER,
                    data TEXT
                )
            """)
            
            # Insert test sessions
            conn.execute(
                "INSERT INTO session VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("sess_001", "proj_1", None, "/workspace/proj", "Task 1", 
                 1716480000000, 1716483600000, "opencode", "gpt-4")
            )
            conn.execute(
                "INSERT INTO session VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("sess_002", "proj_1", "sess_001", "/workspace/proj", "Task 2",
                 1716566400000, 1716570000000, "opencode", "gpt-4")
            )
            conn.commit()
            conn.close()
            
            # Test adapter
            adapter = OpenCodeAdapter()
            sessions = adapter.get_all_sessions_from_db(db_path)
            
            assert len(sessions) == 2
            
            sess_001 = next(s for s in sessions if s.session_id == "sess_001")
            sess_002 = next(s for s in sessions if s.session_id == "sess_002")
            
            assert sess_001.parent_id is None
            assert sess_002.parent_id == "sess_001"
    
    def test_session_without_parent_id(self):
        """Verify that null parent_id becomes None in RawSessionData."""
        pass  # Similar to above but assert None
```

### 4.2 Test SessionParser Propagation

**File:** `tests/indexer/test_parser.py` (extend existing)

```python
def test_parser_preserves_parent_id():
    """Verify SessionParser passes parent_id from RawSessionData to SessionDocument."""
    from smartfork.indexer.parser import SessionParser
    from smartfork.models.session import RawSessionData, RawTurn
    
    raw = RawSessionData(
        session_id="test_001",
        agent_id="opencode",
        session_path=Path("/tmp"),
        turns=[RawTurn(role="user", content="Test task", timestamp=0)],
        files_edited=[],
        files_read=[],
        parent_id="parent_001",
    )
    
    parser = SessionParser()
    doc = parser.parse_session(raw)
    
    assert doc is not None
    assert doc.parent_id == "parent_001"
```

---

## 5. Deliverables

| # | Deliverable | File | Acceptance Criteria |
|---|-------------|------|-------------------|
| 1 | OpenCode adapter fix | `adapters/opencode.py` | `parent_id` passed to `RawSessionData` |
| 2 | SessionParser update | `indexer/parser.py` | `parent_id` propagated to `SessionDocument` |
| 3 | OpenCode adapter tests | `tests/adapters/test_opencode.py` | Tests pass for parent_id preservation |
| 4 | Parser tests | `tests/indexer/test_parser.py` | Tests pass for parent_id propagation |

---

## 6. Dependencies

### Depends on:
- **Phase 1:** `RawSessionData` and `SessionDocument` must have `parent_id` field

### Blocks:
- **Phase 3:** Relationship detection needs `parent_id` for explicit relationships

---

## 7. Notes for Implementer

1. **Minimal change:** This phase is intentionally small. Only fix what's broken (discarded `parent_id`). Don't refactor adapters beyond this.
2. **Future adapters:** When Cursor/Gemini/Cline adapters are implemented later, they should follow the same pattern: if raw data has hierarchy metadata, pass it via `parent_id` or `previous_session_id`.
3. **The `extra` field:** If an adapter has other hierarchy fields not covered by `parent_id`, they can be stored in `RawSessionData.extra` and handled by a custom relationship detector for that adapter.
4. **Testing strategy:** Create a minimal OpenCode SQLite database in tests. Don't depend on the user's real `~/.local/share/opencode/opencode.db`.
