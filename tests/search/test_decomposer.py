"""Tests for QueryDecomposer agent."""

from unittest.mock import MagicMock

from smartfork.models.search import QueryDecomposition
from smartfork.search.decomposer import _QUERY_DECOMPOSITION_PROMPT, QueryDecomposer


class TestQueryDecomposer:
    def test_decompose_returns_query_decomposition(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = QueryDecomposition(
            core_goal="fix auth bug",
            search_variants=["fix auth bug", "auth error resolution", "login bug fix"],
            entities={"technologies": ["auth", "jwt"]},
            intent="error_recall",
            prefer_code=True,
            prefer_recent=False,
        )
        decomposer = QueryDecomposer(llm=mock_llm)
        result = decomposer.decompose("fix auth bug")
        assert isinstance(result, QueryDecomposition)
        assert result.core_goal == "fix auth bug"
        assert len(result.search_variants) == 3

    def test_decompose_prompt_contains_user_query(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = QueryDecomposition(
            core_goal="implement jwt middleware",
            search_variants=["variant1", "variant2", "variant3"],
        )
        decomposer = QueryDecomposer(llm=mock_llm)
        decomposer.decompose("implement jwt middleware")
        call_args = mock_llm.complete_structured.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "implement jwt middleware" in prompt

    def test_decompose_uses_temperature_0_1(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = QueryDecomposition(
            core_goal="test",
            search_variants=["test"],
        )
        decomposer = QueryDecomposer(llm=mock_llm)
        decomposer.decompose("test")
        call_kwargs = mock_llm.complete_structured.call_args.kwargs
        assert call_kwargs.get("temperature") == 0.1

    def test_decompose_fallback_on_llm_failure(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.side_effect = RuntimeError("LLM unavailable")
        decomposer = QueryDecomposer(llm=mock_llm)
        result = decomposer.decompose("original query")
        assert isinstance(result, QueryDecomposition)
        assert result.core_goal == "original query"
        assert result.search_variants == ["original query"]

    def test_decompose_fallback_on_none_result(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = None
        decomposer = QueryDecomposer(llm=mock_llm)
        result = decomposer.decompose("original query")
        assert isinstance(result, QueryDecomposition)
        assert result.search_variants == ["original query"]

    def test_decompose_ensures_original_query_in_variants(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = QueryDecomposition(
            core_goal="original query",
            search_variants=[],
        )
        decomposer = QueryDecomposer(llm=mock_llm)
        result = decomposer.decompose("original query")
        assert result.search_variants == ["original query"]

    def test_decompose_passes_output_schema(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = QueryDecomposition(
            core_goal="test",
            search_variants=["test"],
        )
        decomposer = QueryDecomposer(llm=mock_llm)
        decomposer.decompose("test")
        call_kwargs = mock_llm.complete_structured.call_args.kwargs
        assert call_kwargs.get("output_schema") is QueryDecomposition

    def test_prompt_template_includes_examples(self) -> None:
        assert "GOOD search variants" in _QUERY_DECOMPOSITION_PROMPT
        assert "BAD search variants" in _QUERY_DECOMPOSITION_PROMPT
        assert "diverse search variants" in _QUERY_DECOMPOSITION_PROMPT

    def test_decompose_returns_at_least_one_variant(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = QueryDecomposition(
            core_goal="find session",
            search_variants=["find session", "search session", "locate session"],
        )
        decomposer = QueryDecomposer(llm=mock_llm)
        result = decomposer.decompose("find session")
        assert len(result.search_variants) >= 1
