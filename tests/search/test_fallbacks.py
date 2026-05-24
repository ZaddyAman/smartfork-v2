"""Tests for graceful degradation when components fail."""

from unittest.mock import MagicMock

from smartfork.indexer.metadata_store import MetadataStore
from smartfork.models.query import QueryInterpretation
from smartfork.models.session import QualityTag, SessionDocument
from smartfork.search.deterministic import DeterministicSearchEngine
from smartfork.search.orchestrator import SearchOrchestrator


class TestEmptyFTS5:
    def test_empty_store_returns_empty_results(self, tmp_path):
        """If FTS5 has no indexed sessions, deterministic search returns empty."""
        db_path = tmp_path / "empty.db"
        store = MetadataStore(db_path)
        engine = DeterministicSearchEngine(metadata_store=store)

        results = engine.search("nonexistent query", top_k=5)

        assert results == []

    def test_orchestrator_returns_empty_when_no_sessions(self, tmp_path):
        """Orchestrator gracefully returns empty when the store is empty."""
        db_path = tmp_path / "empty.db"
        store = MetadataStore(db_path)
        orch = SearchOrchestrator(
            embedder=None,
            metadata_store=store,
            llm=None,
            use_fast=True,
        )

        results = orch.search("jwt auth bug", top_k=5)

        assert results == []
        assert orch.last_empty_reasoning != ""


class TestEmptyVectorDB:
    def test_vector_unavailable_uses_fts5_only(self, tmp_path):
        """If no vectors, deterministic search falls back to FTS5 only."""
        db_path = tmp_path / "no_vectors.db"
        store = MetadataStore(db_path)
        sess = SessionDocument(
            session_id="sess_001",
            agent="kilocode",
            project_name="test",
            project_root="/tmp",
            task_raw="Fix JWT authentication bug",
            quality_tag=QualityTag.SOLUTION_FOUND,
        )
        store.upsert_session(sess)

        # No embedder provided -> vector search skipped
        engine = DeterministicSearchEngine(embedder=None, metadata_store=store)
        results = engine.search("jwt auth bug", top_k=5)

        assert len(results) > 0
        assert results[0].session_id == "sess_001"

    def test_vector_available_but_empty_table(self, tmp_path):
        """Embedder available but no vectors stored; FTS5 still works."""
        db_path = tmp_path / "empty_vectors.db"
        store = MetadataStore(db_path)
        sess = SessionDocument(
            session_id="sess_002",
            agent="kilocode",
            project_name="test",
            project_root="/tmp",
            task_raw="Implement PostgreSQL connection pooling",
            quality_tag=QualityTag.SOLUTION_FOUND,
        )
        store.upsert_session(sess)

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1024

        engine = DeterministicSearchEngine(embedder=mock_embedder, metadata_store=store)
        results = engine.search("postgresql pooling", top_k=5)

        assert len(results) > 0
        assert results[0].session_id == "sess_002"


class TestLLMUnavailable:
    def test_orchestrator_fallback_when_llm_none(self, tmp_path):
        """If LLM is None, orchestrator falls back to deterministic search."""
        db_path = tmp_path / "fallback.db"
        store = MetadataStore(db_path)
        sess = SessionDocument(
            session_id="sess_003",
            agent="kilocode",
            project_name="test",
            project_root="/tmp",
            task_raw="Debug Docker container networking issue",
            quality_tag=QualityTag.SOLUTION_FOUND,
        )
        store.upsert_session(sess)

        orch = SearchOrchestrator(
            embedder=None,
            metadata_store=store,
            llm=None,
        )
        results = orch.search("docker networking", top_k=5)

        assert len(results) > 0
        assert results[0].session_id == "sess_003"

    def test_orchestrator_fallback_when_llm_raises(self, tmp_path, mock_llm):
        """If LLM raises, orchestrator catches exception and falls back."""
        db_path = tmp_path / "fallback_raise.db"
        store = MetadataStore(db_path)
        sess = SessionDocument(
            session_id="sess_004",
            agent="kilocode",
            project_name="test",
            project_root="/tmp",
            task_raw="Set up OAuth2 authentication flow",
            quality_tag=QualityTag.SOLUTION_FOUND,
        )
        store.upsert_session(sess)

        mock_llm.complete_structured.side_effect = RuntimeError("LLM service down")

        orch = SearchOrchestrator(
            embedder=None,
            metadata_store=store,
            llm=mock_llm,
        )
        results = orch.search("oauth2 authentication", top_k=5)

        assert len(results) > 0
        assert results[0].session_id == "sess_004"

    def test_interpreter_fallback_deterministic(self, mock_llm):
        """QueryInterpreter falls back to deterministic parsing when LLM fails."""
        from smartfork.search.query_interpreter import QueryInterpreter

        mock_llm.complete_structured.side_effect = RuntimeError("LLM failed")
        interpreter = QueryInterpreter(llm=mock_llm)
        result = interpreter.interpret("jwt auth bug")

        assert "jwt" in result.keywords or "bug" in result.keywords
        assert result.intent != "unknown"


class TestNoRelationships:
    def test_deep_mode_returns_single_sessions_without_chains(self, tmp_path):
        """If no relationships, deep mode returns single sessions without chain grouping."""
        db_path = tmp_path / "no_rel.db"
        store = MetadataStore(db_path)
        sess = SessionDocument(
            session_id="sess_005",
            agent="kilocode",
            project_name="test",
            project_root="/tmp",
            task_raw="Build React component with hooks",
            quality_tag=QualityTag.SOLUTION_FOUND,
        )
        store.upsert_session(sess)

        mock_llm = MagicMock()
        mock_llm.complete_structured.return_value = QueryInterpretation(
            original_query="react hooks",
            keywords=["react", "hooks"],
            synonyms=["component"],
            expanded_query='"react" OR "hooks" OR "component"',
            intent="implementation_lookup",
            multi_session_confidence=0.85,
            needs_deep_mode=True,
        )

        orch = SearchOrchestrator(
            embedder=None,
            metadata_store=store,
            llm=mock_llm,
            use_deep=True,
        )
        results = orch.search("react hooks", top_k=5)

        assert len(results) > 0
        assert results[0].session_id == "sess_005"
        assert results[0].relevance_explanation == "Deep mode: multi-session analysis requested."

    def test_graph_engine_empty_chain(self, tmp_path):
        """SessionGraphEngine returns empty chains when no relationships exist."""
        db_path = tmp_path / "no_rel_graph.db"
        store = MetadataStore(db_path)
        sess = SessionDocument(
            session_id="sess_006",
            agent="kilocode",
            project_name="test",
            project_root="/tmp",
            task_raw="Implement FastAPI middleware",
            quality_tag=QualityTag.SOLUTION_FOUND,
        )
        store.upsert_session(sess)

        from smartfork.search.session_graph_engine import SessionGraphEngine

        graph = SessionGraphEngine(store)
        chains = graph.find_related_sessions("sess_006", max_chains=5)

        assert chains == []

    def test_engine_search_no_metadata_store(self):
        """DeterministicSearchEngine.search() returns empty when no store is wired."""
        engine = DeterministicSearchEngine(embedder=None, metadata_store=None)
        results = engine.search("any query", top_k=5)

        assert results == []

    def test_orchestrator_empty_results_sets_reasoning(self, tmp_path):
        """When no results are found, orchestrator sets last_empty_reasoning."""
        db_path = tmp_path / "empty_reasoning.db"
        store = MetadataStore(db_path)
        orch = SearchOrchestrator(
            embedder=None,
            metadata_store=store,
            llm=None,
            use_fast=True,
        )

        results = orch.search("completely unknown query xyz", top_k=5)

        assert results == []
        assert "No results" in orch.last_empty_reasoning

    def test_deterministic_engine_exception_returns_empty(self, tmp_path):
        """If the engine raises, orchestrator catches and returns empty list."""
        db_path = tmp_path / "broken.db"
        store = MetadataStore(db_path)
        engine = DeterministicSearchEngine(metadata_store=store)

        # Break the engine by monkey-patching _bm25_search to raise
        engine._bm25_search = MagicMock(side_effect=RuntimeError("FTS5 error"))

        orch = SearchOrchestrator(
            embedder=None,
            metadata_store=store,
            llm=None,
            use_fast=True,
        )
        orch.engine = engine

        results = orch.search("any query", top_k=5)

        assert results == []
