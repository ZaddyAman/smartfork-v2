# Phase 7 PRD: Quality + Testing

**Phase:** 7 of 7  
**Estimated Duration:** 1-2 days  
**Priority:** Medium  
**Dependencies:** All previous phases  

---

## 1. Overview

This phase builds comprehensive tests for all new architecture components and runs manual evaluation to verify search quality improvements. The goal is confidence: we must know the new system is better than the old one.

**Goal:**
- Unit tests for all new components (QueryInterpreter, SessionGraphEngine, MultiSessionSynthesizer, etc.)
- Integration tests for end-to-end search flows
- Manual evaluation with real queries against real session data
- Verify no regressions in existing functionality

**Success Criteria:**
- [ ] All new components have unit tests with >80% coverage
- [ ] Integration tests pass for fast/default/deep modes
- [ ] Manual evaluation shows expected sessions in top 3 for >=80% of queries
- [ ] Multi-session chains correctly detected for >=70% of timeline queries
- [ ] All existing tests still pass
- [ ] ruff + mypy + pytest all green

---

## 2. Unit Tests

### 2.1 QueryInterpreter Tests

**File:** `tests/search/test_query_interpreter.py`

```python
"""Tests for QueryInterpreter."""

import pytest
from smartfork.search.query_interpreter import QueryInterpreter, SYNONYMS
from smartfork.models.query import QueryInterpretation


class TestQueryInterpreter:
    def test_specific_query_low_confidence(self):
        """'jwt auth bug' should have low multi_session_confidence."""
        interpreter = QueryInterpreter(llm=None)
        result = interpreter.interpret("jwt auth bug")
        assert result.multi_session_confidence < 0.40
        assert result.needs_deep_mode is False
    
    def test_temporal_query_high_confidence(self):
        """'what happened with auth' should have high confidence."""
        interpreter = QueryInterpreter(llm=None)
        result = interpreter.interpret("what happened with auth")
        assert result.multi_session_confidence > 0.75
        assert result.needs_deep_mode is True
    
    def test_continuation_query_high_confidence(self):
        """'continue my API work' should have high confidence."""
        interpreter = QueryInterpreter(llm=None)
        result = interpreter.interpret("continue my API work")
        assert result.multi_session_confidence > 0.80
        assert result.needs_deep_mode is True
    
    def test_synonym_expansion(self):
        """'auth bug' should expand to include 'authentication', 'error', etc."""
        interpreter = QueryInterpreter(llm=None)
        result = interpreter.interpret("auth bug")
        assert "authentication" in result.synonyms or "login" in result.synonyms
        assert "error" in result.synonyms or "fix" in result.synonyms
    
    def test_intent_detection(self):
        """Various queries should map to correct intents."""
        interpreter = QueryInterpreter(llm=None)
        
        tests = [
            ("how did I fix the auth bug", "solution_hunting"),
            ("that error last week", "error_recall"),
            ("continue my work", "continuation"),
            ("what was I doing yesterday", "temporal_lookup"),
            ("why did I choose OAuth", "decision_hunting"),
        ]
        
        for query, expected_intent in tests:
            result = interpreter.interpret(query)
            assert result.intent == expected_intent, f"Failed for: {query}"
    
    def test_llm_fallback(self):
        """If LLM fails, should fall back to deterministic parsing."""
        # Mock LLM that raises exception
        class FailingLLM:
            def complete_structured(self, *args, **kwargs):
                raise RuntimeError("LLM failed")
        
        interpreter = QueryInterpreter(llm=FailingLLM())
        result = interpreter.interpret("jwt auth bug")
        assert result.keywords  # Should still produce keywords
        assert result.intent != "unknown"
```

---

### 2.2 SessionGraphEngine Tests

**File:** `tests/search/test_session_graph_engine.py`

```python
"""Tests for SessionGraphEngine."""

import pytest
from smartfork.search.session_graph_engine import SessionGraphEngine
from smartfork.models.relationship import SessionRelationship
from smartfork.models.session import SessionDocument, QualityTag


class TestSessionGraphEngine:
    def test_find_chain_forward(self, mock_store):
        """Follow chain forward from oldest session."""
        engine = SessionGraphEngine(store=mock_store)
        chain = engine.find_chain("sess_A", direction="forward")
        
        assert len(chain) == 3
        assert chain[0].session_id == "sess_A"
        assert chain[1].session_id == "sess_B"
        assert chain[2].session_id == "sess_C"
    
    def test_find_chain_backward(self, mock_store):
        """Follow chain backward from newest session."""
        engine = SessionGraphEngine(store=mock_store)
        chain = engine.find_chain("sess_C", direction="backward")
        
        assert len(chain) == 3
        assert chain[0].session_id == "sess_A"
        assert chain[2].session_id == "sess_C"
    
    def test_find_branches(self, mock_store_with_branches):
        """Detect parallel branches from a common parent."""
        engine = SessionGraphEngine(store=mock_store_with_branches)
        branches = engine.find_branches("sess_A")
        
        assert len(branches) == 2
        # Branch 1: A → B
        # Branch 2: A → D
    
    def test_build_timeline(self, mock_store):
        """Build timeline from session chain."""
        engine = SessionGraphEngine(store=mock_store)
        sessions = [
            SessionDocument(session_id="A", task_raw="Debug auth", quality_tag=QualityTag.DEAD_END, session_start=1000),
            SessionDocument(session_id="B", task_raw="Fix auth", quality_tag=QualityTag.SOLUTION_FOUND, session_start=2000),
        ]
        timeline = engine.build_timeline(sessions)
        
        assert len(timeline) == 2
        assert timeline[0].task == "Debug auth"
        assert timeline[1].task == "Fix auth"
        assert timeline[0].relationship_to_next == "supersession"
```

---

### 2.3 DeterministicSearchEngine Tests

**File:** `tests/search/test_deterministic_engine.py`

```python
"""Tests for rewritten DeterministicSearchEngine."""

import pytest
from smartfork.search.deterministic import DeterministicSearchEngine


class TestDeterministicSearchEngine:
    def test_fts5_search(self, mock_store_with_data):
        """FTS5 search returns ranked results."""
        engine = DeterministicSearchEngine(store=mock_store_with_data)
        results = engine._bm25_search("auth bug", top_k=5)
        
        assert len(results) > 0
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)
    
    def test_vector_search(self, mock_store_with_vectors):
        """sqlite-vec search returns similar sessions."""
        engine = DeterministicSearchEngine(store=mock_store_with_vectors)
        results = engine._vector_search("authentication error", top_k=5)
        
        assert len(results) > 0
        assert all(0.0 <= score <= 1.0 for _, score in results)
    
    def test_rrf_fusion(self):
        """RRF combines FTS5 and vector ranks."""
        engine = DeterministicSearchEngine()
        fts5_results = [("A", 0.9), ("B", 0.8), ("C", 0.7)]
        vector_results = [("B", 0.95), ("C", 0.85), ("A", 0.75)]
        
        fused = engine._rrf_fuse(fts5_results, vector_results)
        
        assert len(fused) == 3
        # B should be highest (appears in both with good ranks)
        assert fused[0][0] == "B"
    
    def test_relationship_boost(self, mock_store_with_relationships):
        """Latest session boosted, superseded session demoted."""
        engine = DeterministicSearchEngine(store=mock_store_with_relationships)
        results = [
            {"session_id": "old", "match_score": 0.8, "quality_tag": "dead_end"},
            {"session_id": "new", "match_score": 0.8, "quality_tag": "solution_found"},
        ]
        
        reranked = engine._rerank(results)
        
        # "new" should score higher than "old" due to relationship boost
        new_score = next(r["match_score"] for r in reranked if r["session_id"] == "new")
        old_score = next(r["match_score"] for r in reranked if r["session_id"] == "old")
        assert new_score > old_score
```

---

### 2.4 MultiSessionSynthesizer Tests

**File:** `tests/search/test_multi_session_synthesizer.py`

```python
"""Tests for MultiSessionSynthesizer."""

import pytest
from smartfork.search.multi_session_synthesizer import MultiSessionSynthesizer
from smartfork.models.relationship import Chain, TimelineSummary
from smartfork.models.session import SessionDocument, QualityTag


class TestMultiSessionSynthesizer:
    def test_synthesize_timeline(self, mock_llm):
        """Synthesizer produces TimelineSummary from chains."""
        synthesizer = MultiSessionSynthesizer(llm=mock_llm)
        chains = [
            Chain(
                sessions=[
                    SessionDocument(session_id="A", task_raw="Debug JWT", quality_tag=QualityTag.DEAD_END, session_start=1000),
                    SessionDocument(session_id="B", task_raw="Fix JWT middleware", quality_tag=QualityTag.SOLUTION_FOUND, session_start=2000),
                ],
                chain_type="linear",
                head_session_id="A",
                tail_session_id="B",
            )
        ]
        
        result = synthesizer.synthesize_timeline("what happened with auth", chains)
        
        assert result is not None
        assert result.narrative  # Non-empty narrative
        assert result.resolution_status in ("solved", "ongoing", "dead_end", "mixed")
        assert result.suggested_fork_session_id == "B"
    
    def test_empty_chains(self):
        """Empty chains return None."""
        synthesizer = MultiSessionSynthesizer(llm=None)
        result = synthesizer.synthesize_timeline("query", [])
        assert result is None
```

---

### 2.5 Integration Tests

**File:** `tests/search/test_integration.py`

```python
"""Integration tests for complete search flow."""

import pytest
from smartfork.search.orchestrator import SearchOrchestrator


class TestSearchIntegration:
    def test_fast_mode_no_llm_calls(self, mock_embedder, mock_store):
        """Fast mode uses 0 LLM calls."""
        orchestrator = SearchOrchestrator(embedder=mock_embedder, store=mock_store)
        results = orchestrator.search("jwt auth bug", mode="fast")
        
        assert isinstance(results, list)
        assert len(results) <= 5
    
    def test_default_mode_one_llm_call(self, mock_llm, mock_embedder, mock_store):
        """Default mode uses 1 LLM call."""
        orchestrator = SearchOrchestrator(llm=mock_llm, embedder=mock_embedder, store=mock_store)
        results = orchestrator.search("jwt auth bug", mode="default")
        
        assert mock_llm.call_count == 1  # Only QueryInterpreter
        assert len(results) <= 5
    
    def test_deep_mode_two_llm_calls(self, mock_llm, mock_embedder, mock_store):
        """Deep mode uses 2 LLM calls."""
        orchestrator = SearchOrchestrator(llm=mock_llm, embedder=mock_embedder, store=mock_store)
        results = orchestrator.search("what happened with auth", mode="deep")
        
        assert mock_llm.call_count == 2  # QueryInterpreter + Synthesizer
        assert len(results) <= 5
```

---

## 3. Manual Evaluation

### 3.1 Test Cases

**File:** `tests/search/test_manual_evaluation.py`

```python
"""Manual evaluation tests for search quality.

These tests use the real DeterministicSearchEngine + mocked LLM stages
to verify the new architecture finds expected sessions.
"""

import pytest
from smartfork.search.orchestrator import SearchOrchestrator


# Test cases: query → expected_session_id → minimum_rank
MANUAL_TEST_CASES = [
    ("jwt auth bug", "sess_jwt_fix", 1),
    ("how did I fix the middleware", "sess_middleware_fix", 1),
    ("that database thing I was debugging", "sess_db_debug", 2),
    ("what happened with auth across sessions", "sess_auth_latest", 1),
    ("continue my API work", "sess_api_latest", 1),
    ("PostgreSQL connection pooling issue", "sess_postgres_pool", 1),
    ("why did I choose OAuth over JWT", "sess_oauth_decision", 1),
    ("the CSS layout problem from last week", "sess_css_fix", 2),
    ("Docker deployment pipeline", "sess_docker_deploy", 1),
    ("React component testing with Jest", "sess_react_test", 1),
]


class TestManualEvaluation:
    @pytest.mark.parametrize("query,expected_session_id,min_rank", MANUAL_TEST_CASES)
    def test_orchestrator_finds_session(self, query, expected_session_id, min_rank):
        """Verify orchestrator finds expected session at or above minimum rank."""
        orchestrator = SearchOrchestrator(...)
        results = orchestrator.search(query, top_k=5)
        
        session_ids = [r.session_id for r in results]
        
        if expected_session_id in session_ids:
            rank = session_ids.index(expected_session_id) + 1
            assert rank <= min_rank, f"Expected {expected_session_id} at rank <= {min_rank}, got {rank}"
        else:
            pytest.fail(f"Expected session {expected_session_id} not found in results for query: {query}")
    
    @pytest.mark.parametrize("query,expected_session_id,min_rank", MANUAL_TEST_CASES)
    def test_deterministic_alone_fails(self, query, expected_session_id, min_rank):
        """Prove deterministic search alone is insufficient (shows value of new architecture)."""
        from smartfork.search.deterministic import DeterministicSearchEngine
        engine = DeterministicSearchEngine(...)
        results = engine.search(query, top_k=5)
        
        session_ids = [r["session_id"] for r in results]
        
        # Deterministic should FAIL to find expected session (or rank it poorly)
        # This proves the orchestrator adds value
        if expected_session_id in session_ids:
            rank = session_ids.index(expected_session_id) + 1
            assert rank > min_rank or rank > 3, f"Deterministic found it too easily — test case may not prove orchestrator value"
```

---

## 4. Fallback / Error Handling Tests

**File:** `tests/search/test_fallbacks.py`

```python
"""Tests for graceful degradation when components fail."""

import pytest
from smartfork.search.orchestrator import SearchOrchestrator
from smartfork.search.deterministic import DeterministicSearchEngine


class TestFallbacks:
    def test_llm_unavailable_uses_deterministic(self):
        """If LLM fails, fallback to deterministic search."""
        orchestrator = SearchOrchestrator(llm=None, ...)
        results = orchestrator.search("jwt auth bug")
        assert len(results) > 0
    
    def test_vector_db_empty_uses_fts5(self):
        """If no vectors, use FTS5 only."""
        engine = DeterministicSearchEngine(store=empty_vector_store)
        results = engine.search("jwt auth bug")
        assert len(results) > 0
    
    def test_fts5_empty_returns_empty(self):
        """If FTS5 empty, return empty list gracefully."""
        engine = DeterministicSearchEngine(store=empty_store)
        results = engine.search("nonexistent query")
        assert results == []
    
    def test_no_relationships_returns_single_sessions(self):
        """If no relationships, deep mode returns single sessions."""
        orchestrator = SearchOrchestrator(...)
        results = orchestrator.search("what happened with auth", mode="deep")
        # Should still return results, just without chain grouping
        assert len(results) > 0
```

---

## 5. Performance Benchmarks

**File:** `tests/search/test_performance.py`

```python
"""Performance benchmarks for search latency."""

import time
import pytest
from smartfork.search.orchestrator import SearchOrchestrator


class TestPerformance:
    def test_fast_mode_latency(self):
        """Fast mode should complete in <500ms."""
        orchestrator = SearchOrchestrator(...)
        
        start = time.time()
        results = orchestrator.search("jwt auth bug", mode="fast")
        elapsed = time.time() - start
        
        assert elapsed < 0.5, f"Fast mode took {elapsed:.2f}s (expected <0.5s)"
    
    def test_default_mode_latency(self):
        """Default mode should complete in <3s."""
        orchestrator = SearchOrchestrator(...)
        
        start = time.time()
        results = orchestrator.search("jwt auth bug", mode="default")
        elapsed = time.time() - start
        
        assert elapsed < 3.0, f"Default mode took {elapsed:.2f}s (expected <3s)"
    
    def test_deep_mode_latency(self):
        """Deep mode should complete in <4s."""
        orchestrator = SearchOrchestrator(...)
        
        start = time.time()
        results = orchestrator.search("what happened with auth", mode="deep")
        elapsed = time.time() - start
        
        assert elapsed < 4.0, f"Deep mode took {elapsed:.2f}s (expected <4s)"
```

---

## 6. Deliverables

| # | Deliverable | File | Acceptance Criteria |
|---|-------------|------|-------------------|
| 1 | QueryInterpreter tests | `tests/search/test_query_interpreter.py` | All intent/confidence cases covered |
| 2 | SessionGraphEngine tests | `tests/search/test_session_graph_engine.py` | Chain following, branches, timeline |
| 3 | DeterministicSearchEngine tests | `tests/search/test_deterministic_engine.py` | FTS5, vector, RRF, relationship boost |
| 4 | MultiSessionSynthesizer tests | `tests/search/test_multi_session_synthesizer.py` | Narrative generation, fallback |
| 5 | Integration tests | `tests/search/test_integration.py` | Fast/default/deep modes |
| 6 | Fallback tests | `tests/search/test_fallbacks.py` | LLM fail, empty DB, no relationships |
| 7 | Performance tests | `tests/search/test_performance.py` | Latency benchmarks |
| 8 | Manual evaluation | `tests/search/test_manual_evaluation.py` | 10+ real queries, 80% top-3 accuracy |

---

## 7. Quality Gates

Before declaring the refactor complete, verify:

```bash
# 1. Linting
ruff check src/           # Must pass with 0 errors

# 2. Type checking
mypy src/                 # Must pass with 0 errors

# 3. Tests
pytest tests/ -x          # Must pass all tests

# 4. Coverage
pytest tests/ --cov=src/smartfork --cov-report=term-missing
# Coverage for new code: >80%

# 5. Manual check
python -m smartfork search "jwt auth bug" --fast      # <500ms
python -m smartfork search "jwt auth bug"             # <3s, good results
python -m smartfork search "what happened with auth" --deep   # Shows timeline
```

---

## 8. Notes for Implementer

1. **Mock fixtures:** Create comprehensive fixtures in `tests/conftest.py` for:
   - `mock_llm` — Supports `complete()` and `complete_structured()`
   - `mock_embedder` — Returns fixed 1024d vectors
   - `mock_store` — In-memory SQLite with test data
   - `mock_store_with_relationships` — Pre-populated relationships
   
2. **Test data:** Create realistic test sessions covering:
   - Multiple projects
   - Various quality tags
   - Relationship chains
   - Different time ranges
   
3. **Performance tests:** May need to be marked as `@pytest.mark.slow` if they take >1s each.

4. **Manual evaluation:** The 10 test cases should use UNIQUE keywords per session so deterministic behavior is predictable.

5. **No real LLM calls in CI:** All tests must use mocked LLMs.
