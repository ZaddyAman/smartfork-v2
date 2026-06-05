"""Tests for agentic search engine."""

from unittest.mock import MagicMock

from smartfork.search.legacy.agentic import AgenticSearchEngine


class MockLLM:
    """Mock LLM for testing agentic search."""

    def complete(self, prompt: str, max_tokens: int = 500, temperature: float = 0.1) -> str:
        return ""

    def complete_structured(
        self,
        prompt: str,
        output_schema: type,
        max_tokens: int = 500,
        temperature: float = 0.1,
    ) -> object:
        from smartfork.models.search import QueryDecomposition
        return QueryDecomposition(
            core_goal="fix auth bug",
            search_variants=["fix auth bug", "jwt authentication error", "login 401 fix"],
            entities={"technologies": ["auth", "jwt"]},
            intent="error_recall",
        )


class TestAgenticSearchEngine:
    def test_falls_back_to_deterministic_when_no_llm(self) -> None:
        engine = AgenticSearchEngine(llm=None)
        cards = engine.search("test query")
        assert isinstance(cards, list)

    def test_search_with_mock_llm(self) -> None:
        mock_llm = MockLLM()
        engine = AgenticSearchEngine(llm=mock_llm)
        cards = engine.search("how did I fix the auth error")
        assert isinstance(cards, list)

    def test_deduplicate_results(self) -> None:
        engine = AgenticSearchEngine(llm=None)
        results = [
            {"session_id": "a", "match_score": 0.8},
            {"session_id": "a", "match_score": 0.6},
            {"session_id": "b", "match_score": 0.9},
        ]
        deduped = engine._deduplicate(results)
        assert len(deduped) == 2
        scores = {r["session_id"]: r["match_score"] for r in deduped}
        assert scores["a"] == 0.8

    def test_any_above_threshold_true(self) -> None:
        engine = AgenticSearchEngine(llm=None)
        results = [{"relevance": 0.7}, {"relevance": 0.3}]
        assert engine._any_above_threshold(results) is True

    def test_any_above_threshold_false(self) -> None:
        engine = AgenticSearchEngine(llm=None)
        results = [{"relevance": 0.5}, {"relevance": 0.3}]
        assert engine._any_above_threshold(results) is False

    def test_evaluate_results_fallback(self) -> None:
        engine = AgenticSearchEngine(llm=None)
        results = [{"session_id": "s1", "match_score": 0.8}]
        evaluated = engine._evaluate_results(results, MagicMock(core_goal="test"))
        assert len(evaluated) == 1
        assert "relevance" in evaluated[0]

    def test_pipeline_does_not_crash(self) -> None:
        mock_llm = MockLLM()
        engine = AgenticSearchEngine(llm=mock_llm)
        # Should complete without exceptions
        cards = engine.search("test", top_k=5)
        assert isinstance(cards, list)
