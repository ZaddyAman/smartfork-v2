# Phase 6 PRD: Cleanup + Dependencies

**Phase:** 6 of 7  
**Estimated Duration:** 1-2 days  
**Priority:** Medium  
**Dependencies:** Phase 5 (Multi-Session Intelligence)  

---

## 1. Overview

This phase removes dead code, fixes configuration issues, and wires the existing SearchCache. It's cleanup work that makes the codebase maintainable after the major refactor.

**Goal:**
- Remove ChromaDB and rank-bm25 dependencies
- Remove chunker from indexing path
- Remove/move old 5-stage pipeline components
- Fix config precedence (env vars > TOML)
- Wire SearchCache into deterministic search

**Success Criteria:**
- [ ] No ChromaDB imports in active code
- [ ] No rank_bm25 imports in active code
- [ ] Config env vars override TOML values
- [ ] SearchCache caches and invalidates correctly
- [ ] All removed code in `legacy/` or deleted
- [ ] pyproject.toml updated

---

## 2. Remove Dead Code

### 2.1 Dependencies

**File:** `pyproject.toml`  
**Remove:**
```toml
# REMOVE:
"chromadb>=0.5",
"rank-bm25>=0.2",

# KEEP (already present):
"sentence-transformers>=3.0",

# ADD:
"sqlite-vec>=0.1",  # Check actual package name and version
```

### 2.2 Files to Remove or Move

**Move to `src/smartfork/search/legacy/`:**
- `search/reranker.py` — RerankerAgent (was used by old orchestrator)
- `search/judge.py` — BatchJudgeAgent (was used by old orchestrator)
- `search/agentic.py` — AgenticSearchEngine (dead code, never used by CLI)
- `search/decomposer.py` — QueryDecomposer (may keep for --legacy flag)

**Remove from indexing path (keep file for other uses):**
- `indexer/chunker.py` — Remove from `FullIndexer`, but keep `MessageBoundaryChunker` class for export/display if needed

**Update all imports:**
- Check `search/__init__.py` — remove exports of moved files
- Check `cli/commands.py` — remove imports of old components

---

## 3. Fix Config Precedence

**File:** `src/smartfork/config.py`  
**Current problem:** `load()` passes all TOML values as init kwargs, overriding env vars.

**Fix:** Implement `settings_customise_sources()` or manually merge sources.

```python
from pydantic_settings import SettingsConfigDict, BaseSettings

class SmartForkConfig(BaseSettings):
    # ... existing fields ...
    
    model_config = SettingsConfigDict(
        env_prefix="SMARTFORK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    @classmethod
    def load(cls) -> "SmartForkConfig":
        """Load config with correct precedence: env vars > TOML > defaults."""
        # Step 1: Load from TOML (lowest priority)
        toml_data = {}
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "rb") as f:
                    data = tomllib.load(f)
                toml_data = cls._flatten_toml(data)
            except Exception as exc:
                logger.warning(f"Failed to load config: {exc}")
        
        # Step 2: Instantiate with TOML values (allows env var override)
        # DON'T pass TOML as kwargs — let pydantic-settings handle sources
        instance = cls()
        
        # Step 3: Apply TOML values only for fields NOT set by env var
        for key, value in toml_data.items():
            if key in instance.model_fields:
                # Only set if env var is NOT set
                env_var = f"SMARTFORK_{key.upper()}"
                if env_var not in os.environ:
                    setattr(instance, key, value)
        
        return instance
```

**Alternative (cleaner):** Use `settings_customise_sources()` if pydantic-settings supports it.

```python
@classmethod
@override  # type: ignore
# Actually, pydantic-settings v2 uses:
def settings_customise_sources(
    cls,
    settings_cls: type[BaseSettings],
    init_settings: PydanticBaseSettingsSource,
    env_settings: PydanticBaseSettingsSource,
    dotenv_settings: PydanticBaseSettingsSource,
    file_secret_settings: PydanticBaseSettingsSource,
) -> tuple[PydanticBaseSettingsSource, ...]:
    """Custom source order: env vars > .env > TOML > defaults."""
    # Load TOML as a custom source
    toml_source = TomlConfigSource(CONFIG_FILE)
    return (
        init_settings,
        env_settings,      # Env vars (highest)
        dotenv_settings,   # .env file
        toml_source,       # TOML file
        file_secret_settings,
    )
```

**Test:**
```python
def test_env_var_overrides_toml():
    os.environ["SMARTFORK_LLM_MODEL"] = "gpt-4"
    config = SmartForkConfig.load()
    assert config.llm_model == "gpt-4"
    del os.environ["SMARTFORK_LLM_MODEL"]
```

---

## 4. Wire SearchCache

**File:** `src/smartfork/search/cache.py` (already exists but unused)  
**File:** `src/smartfork/search/deterministic.py`

```python
# In DeterministicSearchEngine.__init__:

class DeterministicSearchEngine:
    def __init__(self, ...):
        # ... existing init ...
        self.cache = SearchCache()  # NEW

# In DeterministicSearchEngine.search():

def search(self, query: str, top_k: int = 5, ...):
    # Build cache key
    cache_key = f"{query}|{project_filter}|{quality_filter}|{top_k}"
    
    # Check cache
    cached = self.cache.get(cache_key)
    if cached is not None:
        return cached
    
    # ... existing search logic ...
    results = ...
    
    # Store in cache
    self.cache.set(cache_key, results)
    
    return results
```

**Cache invalidation on index:**

```python
# In MetadataStore.upsert_session():

def upsert_session(self, session: SessionDocument) -> None:
    # ... existing upsert logic ...
    
    # Invalidate cache entries containing this session
    # This requires cache to track which sessions are in each entry
    # Or simply: clear entire cache on any index update
    SearchCache().clear()  # Simple approach
```

---

## 5. Deliverables

| # | Deliverable | File | Acceptance Criteria |
|---|-------------|------|-------------------|
| 1 | Remove ChromaDB dependency | `pyproject.toml` | No chromadb in deps |
| 2 | Remove rank-bm25 dependency | `pyproject.toml` | No rank-bm25 in deps |
| 3 | Add sqlite-vec dependency | `pyproject.toml` | sqlite-vec in deps |
| 4 | Move old search components | `search/legacy/` | Reranker, Judge, Agentic, Decomposer |
| 5 | Remove chunker from indexing | `indexer/indexer.py` | No chunker.chunk() call |
| 6 | Fix config precedence | `config.py` | Env vars override TOML |
| 7 | Wire SearchCache | `search/deterministic.py`, `search/cache.py` | Cache hits/misses work |
| 8 | Tests | `tests/` | All tests pass |

---

## 6. Dependencies

### Depends on:
- Phase 5: Multi-session intelligence is working before cleanup

### Blocks:
- Phase 7: Testing should verify no regressions from cleanup

---

## 7. Notes for Implementer

1. **Don't delete old code immediately.** Move to `legacy/` first. Delete in a future release after confirming no one needs it.
2. **sqlite-vec package name:** Verify the exact PyPI package name. It might be `sqlite-vec` or similar.
3. **Config precedence test:** Must test both directions: env var set (should win) and env var unset (should use TOML).
4. **Cache TTL:** Default 300 seconds. Consider making it configurable.
5. **Cache invalidation:** Simple approach (clear all on index) is fine for now. Fine-grained invalidation can be added later.
