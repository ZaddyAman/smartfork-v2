# SmartFork v2 — Testing Strategy (Layer 13)

> **Design:** Multi-level testing for both deterministic and non-deterministic (LLM) components.
> **Framework:** pytest + pytest-asyncio
> **Coverage target:** >80% for deterministic code, >60% for agentic code

---

## Test Structure

```
tests/
├── conftest.py                     # Shared fixtures, mock LLM, test DB
├── test_providers.py               # LLM + Embedding providers
├── test_adapters.py                # All 7 adapters (with test data)
├── test_parser.py                  # SessionParser + project extractor
├── test_chunking.py                # Chunker strategies
├── test_embedding.py               # Embedding pipeline
├── test_index_intelligence.py      # Quality tags, tech tags, summaries
├── test_supersession.py            # Supersession detection + annotation
├── test_metadata_store.py          # SQLite CRUD + queries
├── test_search_deterministic.py    # Path A: vector + BM25 + RRF + rerank
├── test_search_agentic.py          # Path B: agentic pipeline steps
├── test_fork.py                    # Fork assembler + generator
├── test_vault.py                   # Obsidian vault generation
├── test_tui.py                     # Textual TUI screens
├── test_mcp.py                     # MCP server tools
├── test_cli.py                     # CLI commands
├── test_config.py                  # Config load/save/migration
│
└── fixtures/                       # Test data
    ├── kilocode_session/           # Sample Kilo Code session directory
    ├── claudecode_session.jsonl    # Sample Claude Code session
    ├── opencode.db                 # Sample OpenCode SQLite database
    └── empty_session/              # Edge case: empty session
```

---

## Conftest: Shared Fixtures

**File:** `tests/conftest.py`

```python
@pytest.fixture
def mock_llm():
    """Returns an LLM provider that returns predictable responses."""
    class MockLLM:
        def complete(self, prompt, max_tokens=500, temperature=0.1):
            if "title" in prompt.lower():
                return "Debugging JWT race condition"
            if "classify" in prompt.lower():
                return "SOLUTION_FOUND"
            if "extract" in prompt.lower():
                return "FastAPI, JWT, PostgreSQL"
            return "Mock response"
        def complete_structured(self, prompt, output_schema, max_tokens=500):
            return None
    return MockLLM()

@pytest.fixture
def mock_embedder():
    """Returns an embedder that returns fixed-dimension vectors."""
    class MockEmbedder:
        def embed(self, text, doc_type="task_doc"):
            return [0.1] * 512
        def embed_query(self, query):
            return [0.2] * 512
        def embed_batch(self, texts, doc_type="task_doc"):
            return [[0.1] * 512] * len(texts)
        def get_dimensions(self):
            return 512
    return MockEmbedder()

@pytest.fixture
def temp_db(tmp_path):
    """Temporary SQLite database."""
    return MetadataStore(tmp_path / "test.db")

@pytest.fixture
def temp_chroma(tmp_path):
    """Temporary ChromaDB."""
    # Use tmp_path for test ChromaDB storage

@pytest.fixture
def sample_session_doc():
    """A valid SessionDocument for testing."""
    return SessionDocument(
        session_id="test123",
        agent="kilocode",
        project_name="TestProject",
        task_raw="Fix JWT race condition in auth middleware",
        files_edited=["auth.py", "middleware.py"],
        domains=["auth", "backend"],
        languages=["python"],
    )
```

---

## Test Categories

### 1. Unit Tests (deterministic code)

Test every pure function independently:
- `derive_project_name()` with various inputs
- `extract_domains()` with file paths
- `extract_languages()` with extensions
- `cosine_similarity()` with known vectors
- `RRF fusion` with known rankings
- `recency_score()` with known timestamps
- `split_reasoning()` with known text
- Config validation rules

### 2. Integration Tests (pipeline)

Test components working together:
- Adapter → Parser → SessionDocument (roundtrip)
- Chunker → Embedder → ChromaDB (store and retrieve)
- Indexer → MetadataStore (all fields survive)
- Search → ResultCard (end-to-end)

### 3. Agentic Tests (non-deterministic)

**The hard problem:** How do you test LLM output?

**Strategy:**
- **Mock LLM** for pipeline tests (test that the framework calls LLM correctly)
- **Snapshot tests** for LLM prompts (verify prompt templates don't drift)
- **Schema validation** for structured output (verify Pydantic models parse)
- **Manual E2E** for quality assessment (not automated)

```python
def test_agentic_pipeline_mock(mock_llm, mock_embedder):
    """Test the agentic pipeline with mocked LLM."""
    engine = AgenticSearchEngine(mock_llm, mock_embedder, ...)
    results = await engine.search("test query")
    assert len(results) > 0

def test_query_understanding_prompt():
    """Snapshot test: verify the prompt template hasn't changed."""
    from smartfork.search.agentic import QUERY_UNDERSTANDING_PROMPT
    assert "developer queries" in QUERY_UNDERSTANDING_PROMPT

def test_structured_output_validation():
    """Verify QueryDecomposition model validates correctly."""
    valid = QueryDecomposition(
        intent=SearchIntent.ERROR_RECALL,
        core_goal="fix bug",
        entities=["JWT"],
        search_variants=["JWT fix"],
        what_should_match="debugging",
        what_should_not_match="setup"
    )
    assert valid.intent == SearchIntent.ERROR_RECALL
```

### 4. Adapter Tests (with fixtures)

```python
def test_kilocode_adapter():
    adapter = KiloCodeAdapter()
    path = Path("tests/fixtures/kilocode_session/")
    assert adapter.is_valid_session(path)
    raw = adapter.parse_raw(path)
    assert raw is not None
    assert raw.session_id == "test123"
    assert len(raw.turns) > 0
    assert len(raw.files_edited) > 0

def test_claudecode_adapter():
    adapter = ClaudeCodeAdapter()
    path = Path("tests/fixtures/claudecode_session.jsonl")
    assert adapter.is_valid_session(path)
    raw = adapter.parse_raw(path)
    assert raw is not None

def test_opencode_adapter():
    adapter = OpenCodeAdapter()
    path = Path("tests/fixtures/opencode.db")
    raw = adapter.parse_raw(path)
    assert raw is not None
```

### 5. Edge Case Tests

- Empty database → search returns empty
- Missing files → graceful error, not crash
- Corrupt JSON → adapter returns None, not exception
- 10,000 sessions → search < 500ms
- Unicode in task descriptions → stored and retrieved correctly
- Missing Ollama → fallback behavior works
- Wrong embedding dimensions → warning, not silent failure

### 6. Performance Tests

```python
@pytest.mark.slow
def test_search_performance_10k():
    """Search should complete in <500ms with 10K sessions."""
    # Populate 10K sessions
    # Time the search
    # Assert < 500ms

@pytest.mark.slow
def test_index_performance_1000():
    """Index 1000 sessions in < 5 minutes."""
```

---

## Test Data / Fixtures

Create minimal but real session data:
- 1 Kilo Code session (real 3-file format)
- 1 Claude Code session (real .jsonl)
- 1 OpenCode database (real SQLite with sessions table)
- Edge cases: empty, corrupt, unicode, large

---

## CI Integration

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -x --cov=src/smartfork --cov-report=term
      - run: ruff check src/
      - run: mypy src/
```

---

## Testing Rules for Ralph

1. Write tests alongside implementation, never after
2. Every public function has at least one test
3. Edge cases tested explicitly (empty, None, corrupt, large)
4. Use fixtures for shared test data
5. Mock external services (Ollama, ChromaDB, Anthropic API)
6. Mark slow tests with `@pytest.mark.slow`
