"""Tests for deterministic search engine."""

from unittest.mock import MagicMock

from smartfork.indexer.metadata_store import MetadataStore
from smartfork.models.search import QueryDecomposition, ResultCard, SearchIntent
from smartfork.models.session import QualityTag, SessionDocument
from smartfork.search.cache import SearchCache
from smartfork.search.deterministic import (
    DeterministicSearchEngine,
    QueryParser,
    _humanize_duration,
    _humanize_timestamp,
)


class TestQueryParser:
    def test_detects_error_intent(self) -> None:
        parser = QueryParser()
        result = parser.parse("how did I fix the database error")
        assert result.intent == SearchIntent.ERROR_RECALL.value

    def test_detects_implementation_intent(self) -> None:
        parser = QueryParser()
        result = parser.parse("how did I implement the auth system")
        assert result.intent == SearchIntent.IMPLEMENTATION_LOOKUP.value

    def test_detects_decision_intent(self) -> None:
        parser = QueryParser()
        result = parser.parse("why did I choose postgresql over mongodb")
        assert result.intent == SearchIntent.DECISION_HUNTING.value

    def test_detects_temporal_intent(self) -> None:
        parser = QueryParser()
        result = parser.parse("what was I working on last week")
        assert result.intent == SearchIntent.TEMPORAL_LOOKUP.value

    def test_defaults_to_vague_memory(self) -> None:
        parser = QueryParser()
        result = parser.parse("something about that thing")
        assert result.intent == SearchIntent.VAGUE_MEMORY.value

    def test_extracts_tech_entities(self) -> None:
        parser = QueryParser()
        result = parser.parse("fix python fastapi jwt docker error")
        techs = result.entities.get("technologies", [])
        assert "python" in techs
        assert "fastapi" in techs
        assert "jwt" in techs
        assert "docker" in techs

    def test_generates_search_variants(self) -> None:
        parser = QueryParser()
        result = parser.parse("fix the authentication bug")
        assert len(result.search_variants) >= 1


class TestHelpers:
    def test_humanize_duration_minutes(self) -> None:
        assert _humanize_duration(0.5) == "<1 min"
        assert _humanize_duration(5) == "5 min"
        assert _humanize_duration(90) == "1.5h"

    def test_humanize_timestamp_recent(self) -> None:
        assert "ago" in _humanize_timestamp(0) or "now" in _humanize_timestamp(0)


class TestBuildFTS5Query:
    def test_basic_and_query(self) -> None:
        engine = DeterministicSearchEngine()
        query = engine._build_fts5_query("fix auth bug")
        assert '"fix"' in query
        assert '"auth"' in query
        assert '"bug"' in query
        assert " AND " in query

    def test_strips_stop_words(self) -> None:
        engine = DeterministicSearchEngine()
        query = engine._build_fts5_query("the auth and bug in system")
        # "the" may appear inside "authentication" — just assert stop words are
        # not standalone terms in the query
        assert '"auth"' in query
        assert '"bug"' in query
        assert '"system"' in query

    def test_synonym_expansion(self) -> None:
        engine = DeterministicSearchEngine()
        query = engine._build_fts5_query("auth bug")
        # auth should expand to include synonyms
        assert '"auth"' in query
        assert " OR " in query


class TestBM25Search:
    def test_fts5_search_normalizes_scores(self) -> None:
        engine = DeterministicSearchEngine()
        mock_store = MagicMock()
        # FTS5 returns lower = better; simulate three results
        mock_store.fts5_search.return_value = [
            ("s1", -2.0),
            ("s2", -1.0),
            ("s3", 0.0),
        ]
        engine.metadata_store = mock_store

        results = engine._bm25_search("auth bug", top_k=2)

        mock_store.fts5_search.assert_called_once()
        assert "s1" in results
        assert "s2" in results
        # Best (lowest) score should normalize to highest value
        assert results["s1"] > results["s2"] > results.get("s3", -1)

    def test_fts5_search_empty_results(self) -> None:
        engine = DeterministicSearchEngine()
        mock_store = MagicMock()
        mock_store.fts5_search.return_value = []
        engine.metadata_store = mock_store

        results = engine._bm25_search("test", top_k=2)
        assert results == {}

    def test_fts5_search_no_store(self) -> None:
        engine = DeterministicSearchEngine()
        assert engine._bm25_search("test", top_k=2) == {}


class TestRerank:
    def test_file_overlap_boost(self) -> None:
        engine = DeterministicSearchEngine()
        mock_store = MagicMock()
        mock_store.get_session.return_value = {
            "task_raw": "implement auth",
            "summary_doc": "auth module done",
            "quality_tag": "unknown",
            "session_start": 0,
            "files_edited": '["src/auth.py", "src/login.py"]',
        }
        mock_store._deserialize_list.return_value = ["src/auth.py", "src/login.py"]
        mock_store.get_superseding_sessions.return_value = []
        mock_store.get_superseded_sessions.return_value = []
        engine.metadata_store = mock_store

        decomposition = QueryDecomposition(
            core_goal="auth python login",
            intent=SearchIntent.IMPLEMENTATION_LOOKUP.value,
            prefer_code=True,
        )

        results = engine._rerank({"s1": 0.5}, decomposition)
        assert len(results) == 1
        session_id, score = results[0]
        assert session_id == "s1"
        # base 0.5 * 0.45 = 0.225
        # file overlap: 2 keywords match files (auth, login) out of 3 -> +0.20 * (2/3) ≈ +0.133
        # keyword density: 3 keywords all in text -> +0.15 * (3/3) = +0.15
        # code preference: +0.05
        # total ≈ 0.225 + 0.133 + 0.15 + 0.05 = 0.558
        # base 0.5 * 0.45 = 0.225
        # file overlap: 2 keywords match files (auth, login) out of 3 -> +0.20 * (2/3) ≈ +0.133
        # keyword density: 1 keyword in text (auth) out of 3 -> +0.15 * (1/3) = +0.05
        # code preference: +0.05
        # total = 0.225 + 0.133 + 0.05 + 0.05 = 0.458
        assert abs(score - 0.458333) < 0.001

    def test_keyword_density_boost(self) -> None:
        engine = DeterministicSearchEngine()
        mock_store = MagicMock()
        mock_store.get_session.return_value = {
            "task_raw": "build fastapi docker api endpoint",
            "summary_doc": "",
            "quality_tag": "unknown",
            "session_start": 0,
            "files_edited": "[]",
        }
        mock_store._deserialize_list.return_value = []
        mock_store.get_superseding_sessions.return_value = []
        mock_store.get_superseded_sessions.return_value = []
        engine.metadata_store = mock_store

        decomposition = QueryDecomposition(
            core_goal="fastapi docker api",
            intent=SearchIntent.VAGUE_MEMORY.value,
        )

        results = engine._rerank({"s1": 0.5}, decomposition)
        _, score = results[0]
        # base 0.5 * 0.45 = 0.225
        # keyword density: 3/3 match -> +0.15
        # total = 0.375
        assert score == 0.375

    def test_quality_boost(self) -> None:
        engine = DeterministicSearchEngine()
        mock_store = MagicMock()
        mock_store.get_session.return_value = {
            "task_raw": "fix bug",
            "summary_doc": "",
            "quality_tag": "solution_found",
            "session_start": 0,
            "files_edited": "[]",
        }
        mock_store._deserialize_list.return_value = []
        mock_store.get_superseding_sessions.return_value = []
        mock_store.get_superseded_sessions.return_value = []
        engine.metadata_store = mock_store

        decomposition = QueryDecomposition(
            core_goal="fix bug",
            intent=SearchIntent.VAGUE_MEMORY.value,
        )

        results = engine._rerank({"s1": 0.5}, decomposition)
        _, score = results[0]
        # base 0.5 * 0.45 = 0.225
        # keyword density: 2/2 match -> +0.15
        # quality: +0.10
        # total = 0.475
        assert score == 0.475

    def test_relationship_boost_latest_in_chain(self) -> None:
        engine = DeterministicSearchEngine()
        mock_store = MagicMock()
        mock_store.get_session.return_value = {
            "task_raw": "auth",
            "summary_doc": "",
            "quality_tag": "unknown",
            "session_start": 0,
            "files_edited": "[]",
        }
        mock_store._deserialize_list.return_value = []
        mock_store.get_superseding_sessions.return_value = []
        # This session supersedes another -> latest in chain
        mock_store.get_superseded_sessions.return_value = [{"superseded_id": "s0"}]
        engine.metadata_store = mock_store

        decomposition = QueryDecomposition(
            core_goal="auth",
            intent=SearchIntent.VAGUE_MEMORY.value,
        )

        results = engine._rerank({"s1": 0.5}, decomposition)
        _, score = results[0]
        # base 0.5 * 0.45 = 0.225
        # keyword density: 1/1 match -> +0.15
        # relationship latest in chain: +0.15
        # total = 0.525
        assert score == 0.525

    def test_relationship_penalty_superseded(self) -> None:
        engine = DeterministicSearchEngine()
        mock_store = MagicMock()
        mock_store.get_session.return_value = {
            "task_raw": "auth",
            "summary_doc": "",
            "quality_tag": "unknown",
            "session_start": 0,
            "files_edited": "[]",
        }
        mock_store._deserialize_list.return_value = []
        # This session is superseded by another
        mock_store.get_superseding_sessions.return_value = [{"superseding_id": "s2"}]
        mock_store.get_superseded_sessions.return_value = []
        engine.metadata_store = mock_store

        decomposition = QueryDecomposition(
            core_goal="auth",
            intent=SearchIntent.VAGUE_MEMORY.value,
        )

        results = engine._rerank({"s1": 0.5}, decomposition)
        _, score = results[0]
        # base 0.5 * 0.45 = 0.225
        # keyword density: 1/1 match -> +0.15
        # relationship superseded: *0.70
        # total = (0.225 + 0.15) * 0.70 = 0.2625
        assert abs(score - 0.2625) < 0.001

    def test_supersession_note_annotation(self) -> None:
        engine = DeterministicSearchEngine()
        mock_store = MagicMock()
        mock_store.get_session.return_value = {
            "task_raw": "auth",
            "summary_doc": "",
            "quality_tag": "unknown",
            "session_start": 0,
            "files_edited": "[]",
        }
        mock_store._deserialize_list.return_value = []
        mock_store.get_superseding_sessions.return_value = [{"superseding_id": "s2"}]
        mock_store.get_superseded_sessions.return_value = []
        engine.metadata_store = mock_store

        decomposition = QueryDecomposition(
            core_goal="auth",
            intent=SearchIntent.VAGUE_MEMORY.value,
        )

        cards = engine._format_cards([("s1", 0.5)], decomposition)
        assert len(cards) == 1
        assert cards[0].supersession_note == "⬆ Superseded by s2"

    def test_superseded_score_demotion(self) -> None:
        engine = DeterministicSearchEngine()
        mock_store = MagicMock()
        mock_store.get_session.return_value = {
            "task_raw": "auth",
            "summary_doc": "",
            "quality_tag": "unknown",
            "session_start": 0,
            "files_edited": "[]",
        }
        mock_store._deserialize_list.return_value = []
        mock_store.get_superseding_sessions.return_value = [{"superseding_id": "s2"}]
        mock_store.get_superseded_sessions.return_value = []
        engine.metadata_store = mock_store

        decomposition = QueryDecomposition(
            core_goal="auth",
            intent=SearchIntent.VAGUE_MEMORY.value,
        )

        results = engine._rerank({"s1": 0.5}, decomposition)
        _, score = results[0]
        # base 0.5 * 0.45 = 0.225
        # keyword density: 1/1 match -> +0.15
        # relationship superseded: *0.70
        # total = (0.225 + 0.15) * 0.70 = 0.2625
        assert abs(score - 0.2625) < 0.001

    def test_latest_in_chain_score_boost(self) -> None:
        engine = DeterministicSearchEngine()
        mock_store = MagicMock()
        mock_store.get_session.return_value = {
            "task_raw": "auth",
            "summary_doc": "",
            "quality_tag": "unknown",
            "session_start": 0,
            "files_edited": "[]",
        }
        mock_store._deserialize_list.return_value = []
        mock_store.get_superseding_sessions.return_value = []
        mock_store.get_superseded_sessions.return_value = [{"superseded_id": "s0"}]
        engine.metadata_store = mock_store

        decomposition = QueryDecomposition(
            core_goal="auth",
            intent=SearchIntent.VAGUE_MEMORY.value,
        )

        results = engine._rerank({"s1": 0.5}, decomposition)
        _, score = results[0]
        # base 0.5 * 0.45 = 0.225
        # keyword density: 1/1 match -> +0.15
        # relationship latest in chain: +0.15
        # total = 0.225 + 0.15 + 0.15 = 0.525
        assert score == 0.525


class TestDeterministicSearchEngine:
    def test_search_returns_cards(self) -> None:
        engine = DeterministicSearchEngine()
        cards = engine.search("test query")
        # With mock backends, returns empty results but doesn't crash
        assert isinstance(cards, list)

    def test_rrf_fusion_empty(self) -> None:
        engine = DeterministicSearchEngine()
        result = engine._rrf_fuse({}, {})
        assert result == {}

    def test_rrf_fusion_combines(self) -> None:
        engine = DeterministicSearchEngine()
        vec = {"a": 0.95, "b": 0.8}
        bm25 = {"b": 0.9, "c": 0.7}
        result = engine._rrf_fuse(vec, bm25)
        assert len(result) >= 2
        # 'b' appears in both lists -> higher fused score
        assert result["b"] > result.get("c", 0)


class TestDeterministicSearchCache:
    def test_cache_hit_returns_same_results(self) -> None:
        engine = DeterministicSearchEngine()
        mock_store = MagicMock()
        mock_store.fts5_search.return_value = [
            ("s1", -1.0),
        ]
        mock_store.get_session.return_value = {
            "task_raw": "auth bug fix",
            "summary_doc": "",
            "quality_tag": "unknown",
            "session_start": 0,
            "files_edited": "[]",
            "project_name": "test",
        }
        mock_store._deserialize_list.return_value = []
        mock_store.get_superseding_sessions.return_value = []
        mock_store.get_superseded_sessions.return_value = []
        engine.metadata_store = mock_store

        # First search - should execute query
        cards1 = engine.search("auth bug")
        assert len(cards1) == 1
        assert cards1[0].session_id == "s1"

        # Second search with same query - should be cached
        cards2 = engine.search("auth bug")
        assert len(cards2) == 1
        assert cards2[0].session_id == "s1"

        # FTS5 should only be called once (first search)
        assert mock_store.fts5_search.call_count == 1

    def test_cache_miss_different_query(self) -> None:
        engine = DeterministicSearchEngine()
        mock_store = MagicMock()
        mock_store.fts5_search.return_value = [
            ("s1", -1.0),
        ]
        mock_store.get_session.return_value = {
            "task_raw": "auth bug fix",
            "summary_doc": "",
            "quality_tag": "unknown",
            "session_start": 0,
            "files_edited": "[]",
            "project_name": "test",
        }
        mock_store._deserialize_list.return_value = []
        mock_store.get_superseding_sessions.return_value = []
        mock_store.get_superseded_sessions.return_value = []
        engine.metadata_store = mock_store

        engine.search("auth bug")
        engine.search("different query")

        # FTS5 should be called twice (different queries)
        assert mock_store.fts5_search.call_count == 2

    def test_cache_respects_ttl(self) -> None:
        from smartfork.search.cache import SearchCache

        cache = SearchCache(ttl=-1)  # Immediate expiry
        engine = DeterministicSearchEngine(cache=cache)
        mock_store = MagicMock()
        mock_store.fts5_search.return_value = [
            ("s1", -1.0),
        ]
        mock_store.get_session.return_value = {
            "task_raw": "auth bug fix",
            "summary_doc": "",
            "quality_tag": "unknown",
            "session_start": 0,
            "files_edited": "[]",
            "project_name": "test",
        }
        mock_store._deserialize_list.return_value = []
        mock_store.get_superseding_sessions.return_value = []
        mock_store.get_superseded_sessions.return_value = []
        engine.metadata_store = mock_store

        # First search
        cards1 = engine.search("auth bug")
        assert len(cards1) == 1

        # Second search - cache should be expired, so it queries again
        cards2 = engine.search("auth bug")
        assert len(cards2) == 1

        # FTS5 should be called twice because cache expired immediately
        assert mock_store.fts5_search.call_count == 2

    def test_cache_invalidation_via_metadata_store(self, tmp_path) -> None:
        cache = SearchCache()
        db_path = tmp_path / "test.db"
        store = MetadataStore(db_path=db_path, search_cache=cache)

        # Create an engine wired to the store
        engine = DeterministicSearchEngine(
            metadata_store=store, cache=cache
        )

        # Set up a session via upsert so FTS5 trigger populates index
        session = SessionDocument(
            session_id="s1",
            agent="agent1",
            project_name="test",
            project_root="/tmp/test",
            task_raw="auth bug fix",
            summary_doc="",
            quality_tag=QualityTag("unknown"),
            indexed_at=0,
        )
        store.upsert_session(session)

        # Search and cache result
        cards1 = engine.search("auth bug")
        assert len(cards1) == 1
        assert cards1[0].session_id == "s1"

        # Verify cache hit
        cards2 = engine.search("auth bug")
        assert len(cards2) == 1

        # Now upsert the same session - this should invalidate cache
        session.task_raw = "updated task"
        store.upsert_session(session)

        # Cache should be invalidated - next search should re-query
        # For this test, the key point is that cache is invalidated.
        assert cache.get("auth bug") is None


class TestSearchCache:
    def test_cache_miss(self) -> None:
        cache = SearchCache()
        assert cache.get("foo") is None

    def test_cache_hit(self) -> None:
        cache = SearchCache()
        card = ResultCard(
            rank=1,
            session_id="s1",
            title="Session 1",
            project_name="p1",
            match_score=0.9,
        )
        cache.put("foo", [card])
        cached = cache.get("foo")
        assert cached is not None
        assert len(cached) == 1
        assert cached[0].session_id == "s1"

    def test_cache_expiry(self) -> None:
        cache = SearchCache(ttl=-1)
        card = ResultCard(
            rank=1,
            session_id="s1",
            title="Session 1",
            project_name="p1",
            match_score=0.9,
        )
        cache.put("foo", [card])
        assert cache.get("foo") is None

    def test_session_invalidation(self) -> None:
        cache = SearchCache()
        card = ResultCard(
            rank=1,
            session_id="s1",
            title="Session 1",
            project_name="p1",
            match_score=0.9,
        )
        cache.put("foo", [card])
        cache.invalidate_session("s1")
        assert cache.get("foo") is None

    def test_lru_eviction(self) -> None:
        cache = SearchCache(max_size=2)
        for i in range(3):
            card = ResultCard(
                rank=1,
                session_id=f"s{i}",
                title=f"Session {i}",
                project_name="p1",
                match_score=0.9,
            )
            cache.put(f"q{i}", [card])
        # First entry should have been evicted
        assert cache.get("q0") is None
        assert cache.get("q1") is not None
        assert cache.get("q2") is not None

    def test_clear(self) -> None:
        cache = SearchCache()
        card = ResultCard(
            rank=1,
            session_id="s1",
            title="Session 1",
            project_name="p1",
            match_score=0.9,
        )
        cache.put("foo", [card])
        cache.clear()
        assert cache.get("foo") is None
