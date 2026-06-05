"""Integration tests for complete search flow (fast / default / deep modes)."""

from unittest.mock import MagicMock

import pytest

from smartfork.indexer.metadata_store import MetadataStore
from smartfork.models.query import QueryInterpretation
from smartfork.models.relationship import TimelineSummary
from smartfork.models.session import QualityTag, SessionDocument
from smartfork.search.deterministic import DeterministicSearchEngine
from smartfork.search.orchestrator import SearchOrchestrator


def _make_session(
    session_id: str,
    task_raw: str,
    summary_doc: str = "",
    quality_tag: QualityTag = QualityTag.UNKNOWN,
    session_start: int = 1_700_000_000_000,
) -> SessionDocument:
    return SessionDocument(
        session_id=session_id,
        agent="kilocode",
        project_name="test_project",
        project_root="/tmp/test",
        task_raw=task_raw,
        summary_doc=summary_doc,
        quality_tag=quality_tag,
        session_start=session_start,
    )


@pytest.fixture
def integration_store(tmp_path) -> MetadataStore:
    """Return a MetadataStore with 5 sample sessions pre-loaded."""
    db_path = tmp_path / "integration.db"
    store = MetadataStore(db_path)
    sessions = [
        _make_session(
            "sess_auth_debug",
            "Debug JWT authentication bug in middleware",
            "Token validation failing",
            QualityTag.DEAD_END,
            1_700_000_000_000,
        ),
        _make_session(
            "sess_auth_fix",
            "Fix JWT authentication bug with new library",
            "Updated to pyjwt 2.0",
            QualityTag.SOLUTION_FOUND,
            1_700_086_400_000,
        ),
        _make_session(
            "sess_db_pool",
            "Implement PostgreSQL connection pooling",
            "Using sqlalchemy pool",
            QualityTag.SOLUTION_FOUND,
            1_700_172_800_000,
        ),
        _make_session(
            "sess_react_component",
            "Build React login component with OAuth",
            "Component with hooks",
            QualityTag.PARTIAL,
            1_700_259_200_000,
        ),
        _make_session(
            "sess_docker_deploy",
            "Set up Docker deployment pipeline for API",
            "Multi-stage Dockerfile",
            QualityTag.SOLUTION_FOUND,
            1_700_345_600_000,
        ),
    ]
    for sess in sessions:
        store.upsert_session(sess)
    return store


@pytest.fixture
def mock_embedder() -> MagicMock:
    """Mock embedder that returns fixed vectors."""
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1] * 1024
    return embedder


@pytest.fixture
def mock_llm_for_integration() -> MagicMock:
    """Mock LLM configured for integration tests."""
    llm = MagicMock()
    llm.complete.return_value = "Mocked narrative"
    llm.complete_structured.return_value = QueryInterpretation(
        original_query="what happened with auth",
        keywords=["auth", "jwt"],
        synonyms=["authentication"],
        expanded_query='"auth" OR "authentication" OR "jwt"',
        intent="temporal_lookup",
        multi_session_confidence=0.85,
        needs_deep_mode=True,
    )
    return llm


class TestFastMode:
    def test_returns_results_without_llm(self, integration_store, mock_embedder, capsys):
        """Fast mode uses 0 LLM calls and returns results via deterministic search."""
        orch = SearchOrchestrator(
            embedder=mock_embedder,
            metadata_store=integration_store,
            llm=None,
            use_fast=True,
        )
        results = orch.search("jwt auth bug", top_k=5)

        assert isinstance(results, list)
        assert len(results) > 0
        session_ids = {r.session_id for r in results}
        assert "sess_auth_debug" in session_ids or "sess_auth_fix" in session_ids

        captured = capsys.readouterr()
        assert "Fast search..." in captured.out
        assert "Interpreting query..." not in captured.out

    def test_no_llm_required(self, integration_store):
        """Fast mode works even when no LLM or embedder is provided."""
        orch = SearchOrchestrator(
            embedder=None,
            metadata_store=integration_store,
            llm=None,
            use_fast=True,
        )
        results = orch.search("postgresql pooling", top_k=5)

        assert isinstance(results, list)
        assert len(results) > 0
        assert any(r.session_id == "sess_db_pool" for r in results)


class TestDefaultMode:
    def test_orchestrator_finds_relevant_sessions(
        self, integration_store, mock_embedder, mock_llm_for_integration, capsys
    ):
        """Default mode uses QueryInterpreter then deterministic search."""
        mock_llm_for_integration.complete_structured.return_value = QueryInterpretation(
            original_query="docker deployment pipeline",
            keywords=["docker", "deployment", "pipeline"],
            synonyms=["container"],
            expanded_query='"docker" OR "deployment" OR "pipeline" OR "container"',
            intent="implementation_lookup",
            multi_session_confidence=0.30,
            needs_deep_mode=False,
        )
        orch = SearchOrchestrator(
            embedder=mock_embedder,
            metadata_store=integration_store,
            llm=mock_llm_for_integration,
            use_fast=False,
        )
        results = orch.search("docker deployment pipeline", top_k=5)

        assert isinstance(results, list)
        assert len(results) > 0
        assert any(r.session_id == "sess_docker_deploy" for r in results)

        captured = capsys.readouterr()
        assert "Interpreting query..." in captured.out
        assert "Searching..." in captured.out
        assert "Deep synthesis..." not in captured.out

    def test_interpreter_called_once(
        self, integration_store, mock_embedder, mock_llm_for_integration
    ):
        """Default mode calls the LLM exactly once (QueryInterpreter)."""
        orch = SearchOrchestrator(
            embedder=mock_embedder,
            metadata_store=integration_store,
            llm=mock_llm_for_integration,
        )
        orch.search("jwt auth bug", top_k=5)

        assert mock_llm_for_integration.complete_structured.call_count == 1


class TestDeepMode:
    def test_deep_mode_uses_synthesis(
        self, integration_store, mock_embedder, mock_llm_for_integration, capsys
    ):
        """Deep mode triggers multi-session synthesis with a second LLM call."""
        mock_llm_for_integration.complete_structured.side_effect = [
            QueryInterpretation(
                original_query="what happened with auth",
                keywords=["auth"],
                synonyms=["authentication"],
                expanded_query='"auth" OR "authentication"',
                intent="temporal_lookup",
                multi_session_confidence=0.85,
                needs_deep_mode=True,
            ),
            TimelineSummary(
                narrative="You debugged and fixed the auth bug.",
                timeline=[],
                suggested_fork_session_id="sess_auth_fix",
                resolution_status="solved",
            ),
        ]

        orch = SearchOrchestrator(
            embedder=mock_embedder,
            metadata_store=integration_store,
            llm=mock_llm_for_integration,
            use_deep=True,
        )
        results = orch.search("what happened with auth", top_k=5)

        assert isinstance(results, list)
        assert len(results) > 0
        assert results[0].relevance_explanation == "Deep mode: multi-session analysis requested."

        captured = capsys.readouterr()
        assert "Interpreting query..." in captured.out
        assert "Searching..." in captured.out
        assert "Deep synthesis..." in captured.out

    def test_deep_mode_falls_back_when_no_relationships(
        self, integration_store, mock_embedder, mock_llm_for_integration
    ):
        """Deep mode on a session with no relationships still returns results."""
        mock_llm_for_integration.complete_structured.return_value = QueryInterpretation(
            original_query="postgresql connection pooling",
            keywords=["postgresql", "pooling"],
            synonyms=["database"],
            expanded_query='"postgresql" OR "pooling" OR "database"',
            intent="implementation_lookup",
            multi_session_confidence=0.85,
            needs_deep_mode=True,
        )

        orch = SearchOrchestrator(
            embedder=mock_embedder,
            metadata_store=integration_store,
            llm=mock_llm_for_integration,
            use_deep=True,
        )
        results = orch.search("postgresql connection pooling", top_k=5)

        assert isinstance(results, list)
        assert len(results) > 0
        assert any(r.session_id == "sess_db_pool" for r in results)

    def test_deep_mode_results_sliced_to_top_k(
        self, integration_store, mock_embedder, mock_llm_for_integration
    ):
        """Deep mode respects top_k slicing."""
        mock_llm_for_integration.complete_structured.return_value = QueryInterpretation(
            original_query="auth",
            keywords=["auth"],
            synonyms=[],
            expanded_query='"auth"',
            intent="vague_memory",
            multi_session_confidence=0.85,
            needs_deep_mode=True,
        )

        orch = SearchOrchestrator(
            embedder=mock_embedder,
            metadata_store=integration_store,
            llm=mock_llm_for_integration,
            use_deep=True,
        )
        results = orch.search("auth", top_k=2)

        assert len(results) <= 2


class TestEndToEndWithRealEngine:
    def test_full_pipeline_with_real_deterministic_engine(self, integration_store):
        """Use the real DeterministicSearchEngine directly against the store."""
        engine = DeterministicSearchEngine(
            embedder=None,
            metadata_store=integration_store,
        )
        cards = engine.search("docker deployment", top_k=3)

        assert isinstance(cards, list)
        assert len(cards) > 0
        assert cards[0].session_id == "sess_docker_deploy"
        assert "docker" in cards[0].title.lower()

    def test_rrf_fusion_with_real_data(self, integration_store, mock_embedder):
        """Vector + BM25 fusion works with real store."""
        engine = DeterministicSearchEngine(
            embedder=mock_embedder,
            metadata_store=integration_store,
        )
        cards = engine.search("jwt authentication middleware", top_k=5)

        assert isinstance(cards, list)
        assert len(cards) >= 1
        session_ids = [c.session_id for c in cards]
        assert "sess_auth_debug" in session_ids or "sess_auth_fix" in session_ids
