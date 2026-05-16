"""Tests for RerankerAgent."""

from unittest.mock import MagicMock

import pytest

from smartfork.models.search import BatchRerankResult, RerankResult
from smartfork.search.reranker import RerankerAgent, _build_batch_prompt, _filter_reasoning_docs


def _make_candidate(
    session_id: str,
    match_score: float,
    title: str = "",
    task_raw: str = "",
    summary_doc: str = "",
    reasoning_docs: list[str] | None = None,
) -> dict:
    return {
        "session_id": session_id,
        "title": title or session_id,
        "match_score": match_score,
        "project_name": "test",
        "content": summary_doc or task_raw,
        "task_raw": task_raw,
        "summary_doc": summary_doc,
        "reasoning_docs": reasoning_docs or [],
        "tags": [],
        "files_summary": "",
        "time_ago": "",
        "duration": "",
        "fork_command": f"smartfork fork {session_id}",
    }


class TestRerankerAgent:
    def test_rerank_returns_enriched_candidates(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = BatchRerankResult(
            rankings=[
                RerankResult(session_id="s1", relevance_score=0.9, reason="Direct match"),
                RerankResult(session_id="s2", relevance_score=0.7, reason="Related"),
            ]
        )
        agent = RerankerAgent(llm=mock_llm)
        candidates = [
            _make_candidate("s1", 0.5, task_raw="fix auth bug"),
            _make_candidate("s2", 0.8, task_raw="implement jwt"),
        ]
        result = agent.rerank(candidates, "how did I fix auth", top_n=2)

        assert len(result) == 2
        assert result[0]["session_id"] == "s1"
        assert result[0]["relevance_score"] == 0.9
        assert result[0]["reason"] == "Direct match"
        assert result[1]["session_id"] == "s2"
        assert result[1]["relevance_score"] == 0.7

    def test_rerank_sorts_by_relevance_score_descending(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = BatchRerankResult(
            rankings=[
                RerankResult(session_id="s1", relevance_score=0.5),
                RerankResult(session_id="s2", relevance_score=0.95),
                RerankResult(session_id="s3", relevance_score=0.7),
            ]
        )
        agent = RerankerAgent(llm=mock_llm)
        candidates = [
            _make_candidate("s1", 0.9),
            _make_candidate("s2", 0.5),
            _make_candidate("s3", 0.8),
        ]
        result = agent.rerank(candidates, "query", top_n=3)

        scores = [r["relevance_score"] for r in result]
        assert scores == [0.95, 0.7, 0.5]

    def test_rerank_respects_top_n(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = BatchRerankResult(
            rankings=[
                RerankResult(session_id="s1", relevance_score=0.9),
                RerankResult(session_id="s2", relevance_score=0.8),
                RerankResult(session_id="s3", relevance_score=0.7),
            ]
        )
        agent = RerankerAgent(llm=mock_llm)
        candidates = [
            _make_candidate("s1", 0.5),
            _make_candidate("s2", 0.5),
            _make_candidate("s3", 0.5),
        ]
        result = agent.rerank(candidates, "query", top_n=2)

        assert len(result) == 2
        assert {r["session_id"] for r in result} == {"s1", "s2"}

    def test_rerank_batched_into_groups_of_five(self, mock_llm: MagicMock) -> None:
        """11 candidates should result in 3 LLM calls (5 + 5 + 1)."""
        rankings = []
        for i in range(11):
            rankings.append(
                RerankResult(session_id=f"s{i:02d}", relevance_score=0.1 * i)
            )

        # Return all rankings in a single batch response for simplicity
        mock_llm.complete_structured.return_value = BatchRerankResult(
            rankings=rankings
        )
        agent = RerankerAgent(llm=mock_llm)
        candidates = [_make_candidate(f"s{i:02d}", 0.5) for i in range(11)]
        result = agent.rerank(candidates, "query", top_n=15)

        assert mock_llm.complete_structured.call_count == 3
        assert len(result) == 11

    def test_rerank_prompt_contains_query(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = BatchRerankResult(
            rankings=[RerankResult(session_id="s1", relevance_score=0.9)]
        )
        agent = RerankerAgent(llm=mock_llm)
        candidates = [_make_candidate("s1", 0.5, task_raw="fix auth")]
        agent.rerank(candidates, "how did I fix auth", top_n=1)

        call_kwargs = mock_llm.complete_structured.call_args.kwargs
        prompt = call_kwargs.get("prompt", "")
        assert "how did I fix auth" in prompt

    def test_rerank_prompt_contains_candidate_content(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = BatchRerankResult(
            rankings=[RerankResult(session_id="s1", relevance_score=0.9)]
        )
        agent = RerankerAgent(llm=mock_llm)
        candidates = [
            _make_candidate(
                "s1",
                0.5,
                task_raw="fix authentication bug",
                summary_doc="Summary of auth fix",
                reasoning_docs=["reasoning A", "reasoning B"],
            )
        ]
        agent.rerank(candidates, "fix auth", top_n=1)

        call_kwargs = mock_llm.complete_structured.call_args.kwargs
        prompt = call_kwargs.get("prompt", "")
        assert "fix authentication bug" in prompt
        assert "Summary of auth fix" in prompt

    def test_rerank_uses_complete_structured_with_batch_result(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = BatchRerankResult(
            rankings=[RerankResult(session_id="s1", relevance_score=0.9)]
        )
        agent = RerankerAgent(llm=mock_llm)
        candidates = [_make_candidate("s1", 0.5)]
        agent.rerank(candidates, "query", top_n=1)

        call_kwargs = mock_llm.complete_structured.call_args.kwargs
        assert call_kwargs.get("output_schema") is BatchRerankResult
        assert call_kwargs.get("max_tokens") == 800
        assert call_kwargs.get("temperature") == 0.1

    def test_rerank_fallback_on_llm_failure(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.side_effect = RuntimeError("LLM unavailable")
        agent = RerankerAgent(llm=mock_llm)
        candidates = [
            _make_candidate("s1", 0.3),
            _make_candidate("s2", 0.9),
            _make_candidate("s3", 0.6),
        ]
        result = agent.rerank(candidates, "query", top_n=2)

        # Should fall back to match_score sorting
        assert len(result) == 2
        assert result[0]["session_id"] == "s2"
        assert result[1]["session_id"] == "s3"
        assert "relevance_score" not in result[0]

    def test_rerank_fallback_on_none_response(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = None
        agent = RerankerAgent(llm=mock_llm)
        candidates = [
            _make_candidate("s1", 0.4),
            _make_candidate("s2", 0.8),
        ]
        result = agent.rerank(candidates, "query", top_n=2)

        assert len(result) == 2
        assert result[0]["session_id"] == "s2"

    def test_rerank_fallback_on_empty_rankings(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = BatchRerankResult(rankings=[])
        agent = RerankerAgent(llm=mock_llm)
        candidates = [
            _make_candidate("s1", 0.4),
            _make_candidate("s2", 0.8),
        ]
        result = agent.rerank(candidates, "query", top_n=2)

        assert len(result) == 2
        assert result[0]["session_id"] == "s2"

    def test_rerank_empty_candidates_returns_empty(self, mock_llm: MagicMock) -> None:
        agent = RerankerAgent(llm=mock_llm)
        result = agent.rerank([], "query", top_n=5)
        assert result == []
        mock_llm.complete_structured.assert_not_called()

    def test_rerank_ignores_unknown_session_ids(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = BatchRerankResult(
            rankings=[
                RerankResult(session_id="s1", relevance_score=0.9),
                RerankResult(session_id="unknown", relevance_score=0.8),
            ]
        )
        agent = RerankerAgent(llm=mock_llm)
        candidates = [_make_candidate("s1", 0.5)]
        result = agent.rerank(candidates, "query", top_n=5)

        assert len(result) == 1
        assert result[0]["session_id"] == "s1"

    def test_rerank_includes_missed_candidates_with_zero_score(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = BatchRerankResult(
            rankings=[RerankResult(session_id="s1", relevance_score=0.9)]
        )
        agent = RerankerAgent(llm=mock_llm)
        candidates = [
            _make_candidate("s1", 0.5),
            _make_candidate("s2", 0.8),
        ]
        result = agent.rerank(candidates, "query", top_n=5)

        assert len(result) == 2
        # s1 should be first because it got a high score
        assert result[0]["session_id"] == "s1"
        assert result[0]["relevance_score"] == 0.9
        # s2 should be included with 0.0
        assert result[1]["session_id"] == "s2"
        assert result[1]["relevance_score"] == 0.0
        assert result[1]["reason"] == ""

    def test_rerank_candidates_without_session_id(self, mock_llm: MagicMock) -> None:
        agent = RerankerAgent(llm=mock_llm)
        candidates = [{"match_score": 0.5, "title": "no id"}]
        result = agent.rerank(candidates, "query", top_n=5)

        # Should fall back to returning original candidates
        assert result == candidates
        mock_llm.complete_structured.assert_not_called()


class TestFilterReasoningDocs:
    def test_filters_by_keywords(self) -> None:
        docs = [
            "authentication flow analysis",
            "database schema design",
            "auth token validation",
            "frontend styling",
        ]
        filtered = _filter_reasoning_docs(docs, "how did I fix auth")
        assert len(filtered) == 2
        assert "authentication flow analysis" in filtered
        assert "auth token validation" in filtered

    def test_returns_up_to_three(self) -> None:
        docs = [f"doc {i}" for i in range(10)]
        filtered = _filter_reasoning_docs(docs, "doc")
        assert len(filtered) == 3

    def test_returns_original_if_no_keywords(self) -> None:
        docs = ["doc one", "doc two"]
        # Query with only stop words / short words produces no keywords
        filtered = _filter_reasoning_docs(docs, "a an the")
        assert filtered == ["doc one", "doc two"]

    def test_returns_empty_for_empty_docs(self) -> None:
        assert _filter_reasoning_docs([], "query") == []


class TestBuildBatchPrompt:
    def test_includes_query(self) -> None:
        candidates = [_make_candidate("s1", 0.5, task_raw="task")]
        prompt = _build_batch_prompt(candidates, "my query")
        assert "ORIGINAL QUERY: my query" in prompt

    def test_includes_candidate_fields(self) -> None:
        candidates = [
            _make_candidate(
                "s1",
                0.5,
                title="Title",
                task_raw="Task text",
                summary_doc="Summary text",
                reasoning_docs=["Reasoning about query details", "Another query point"],
            )
        ]
        prompt = _build_batch_prompt(candidates, "query details")
        assert "--- Candidate s1 ---" in prompt
        assert "Title: Title" in prompt
        assert "Task: Task text" in prompt
        assert "Summary: Summary text" in prompt
        assert "Reasoning 1: Reasoning about query details" in prompt
        assert "Reasoning 2: Another query point" in prompt

    def test_omits_empty_fields(self) -> None:
        candidates = [_make_candidate("s1", 0.5, title="Title")]
        prompt = _build_batch_prompt(candidates, "query")
        assert "Task:" not in prompt
        assert "Summary:" not in prompt
        assert "Reasoning" not in prompt

    def test_filters_reasoning_docs_by_query(self) -> None:
        candidates = [
            _make_candidate(
                "s1",
                0.5,
                reasoning_docs=[
                    "authentication bug analysis",
                    "database migration plan",
                    "auth token refresh logic",
                ],
            )
        ]
        prompt = _build_batch_prompt(candidates, "fix auth")
        assert "authentication bug analysis" in prompt
        assert "auth token refresh logic" in prompt
        assert "database migration plan" not in prompt
