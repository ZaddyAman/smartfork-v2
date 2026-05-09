"""Tests for deterministic search engine."""

from smartfork.models.search import ResultCard, SearchIntent
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
        assert result.intent == SearchIntent.ERROR_RECALL

    def test_detects_implementation_intent(self) -> None:
        parser = QueryParser()
        result = parser.parse("how did I implement the auth system")
        assert result.intent == SearchIntent.IMPLEMENTATION_LOOKUP

    def test_detects_decision_intent(self) -> None:
        parser = QueryParser()
        result = parser.parse("why did I choose postgresql over mongodb")
        assert result.intent == SearchIntent.DECISION_HUNTING

    def test_detects_temporal_intent(self) -> None:
        parser = QueryParser()
        result = parser.parse("what was I working on last week")
        assert result.intent == SearchIntent.TEMPORAL_LOOKUP

    def test_defaults_to_vague_memory(self) -> None:
        parser = QueryParser()
        result = parser.parse("something about that thing")
        assert result.intent == SearchIntent.VAGUE_MEMORY

    def test_extracts_tech_entities(self) -> None:
        parser = QueryParser()
        result = parser.parse("fix python fastapi jwt docker error")
        assert "python" in result.entities
        assert "fastapi" in result.entities
        assert "jwt" in result.entities
        assert "docker" in result.entities

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
