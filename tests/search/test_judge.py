"""Tests for BatchJudgeAgent."""

from unittest.mock import MagicMock

import pytest

from smartfork.models.search import BatchJudgeResult, JudgeOutput, QueryDecomposition
from smartfork.search.legacy.judge import BatchJudgeAgent, _build_batch_prompt


def _make_candidate(
    session_id: str,
    match_score: float,
    title: str = "",
    task_raw: str = "",
    summary_doc: str = "",
    reasoning_docs: list[str] | None = None,
    files_edited: list[str] | None = None,
) -> dict:
    return {
        "session_id": session_id,
        "title": title or session_id,
        "match_score": match_score,
        "project_name": "test",
        "task_raw": task_raw,
        "summary_doc": summary_doc,
        "reasoning_docs": reasoning_docs or [],
        "files_edited": files_edited or [],
    }


@pytest.fixture
def qd() -> QueryDecomposition:
    return QueryDecomposition(
        core_goal="fix authentication bug",
        intent="implementation_lookup",
        entities={"tech": "jwt", "file": "auth.py"},
    )


class TestBatchJudgeAgent:
    def test_drops_false_positives(self, mock_llm: MagicMock, qd: QueryDecomposition) -> None:
        mock_llm.complete_structured.return_value = BatchJudgeResult(
            judgments=[
                JudgeOutput(
                    session_id="s1",
                    relevance_score=0.9,
                    matches_query=True,
                    reason="Direct match",
                    key_snippet="fix auth",
                ),
                JudgeOutput(
                    session_id="s2",
                    relevance_score=0.8,
                    matches_query=False,
                    reason="Not relevant",
                    key_snippet="",
                ),
                JudgeOutput(
                    session_id="s3",
                    relevance_score=0.7,
                    matches_query=True,
                    reason="Related",
                    key_snippet="auth flow",
                ),
            ]
        )
        agent = BatchJudgeAgent(llm=mock_llm)
        candidates = [
            _make_candidate("s1", 0.5),
            _make_candidate("s2", 0.5),
            _make_candidate("s3", 0.5),
        ]
        result = agent.judge(candidates, "fix auth", qd)

        assert len(result) == 2
        assert result[0].session_id == "s1"
        assert result[1].session_id == "s3"

    def test_sorts_by_relevance_score(self, mock_llm: MagicMock, qd: QueryDecomposition) -> None:
        mock_llm.complete_structured.return_value = BatchJudgeResult(
            judgments=[
                JudgeOutput(
                    session_id="s1",
                    relevance_score=0.5,
                    matches_query=True,
                    reason="",
                    key_snippet="",
                ),
                JudgeOutput(
                    session_id="s2",
                    relevance_score=0.95,
                    matches_query=True,
                    reason="",
                    key_snippet="",
                ),
                JudgeOutput(
                    session_id="s3",
                    relevance_score=0.7,
                    matches_query=True,
                    reason="",
                    key_snippet="",
                ),
            ]
        )
        agent = BatchJudgeAgent(llm=mock_llm)
        candidates = [
            _make_candidate("s1", 0.5),
            _make_candidate("s2", 0.5),
            _make_candidate("s3", 0.5),
        ]
        result = agent.judge(candidates, "query", qd)

        scores = [j.relevance_score for j in result]
        assert scores == [0.95, 0.7, 0.5]

    def test_top_five_slicing(self, mock_llm: MagicMock, qd: QueryDecomposition) -> None:
        judgments = [
            JudgeOutput(
                session_id=f"s{i}",
                relevance_score=0.1 * (10 - i),
                matches_query=True,
                reason="",
                key_snippet="",
            )
            for i in range(7)
        ]
        mock_llm.complete_structured.return_value = BatchJudgeResult(judgments=judgments)
        agent = BatchJudgeAgent(llm=mock_llm)
        candidates = [_make_candidate(f"s{i}", 0.5) for i in range(7)]
        result = agent.judge(candidates, "query", qd)

        assert len(result) == 5
        assert result[0].session_id == "s0"
        assert result[4].session_id == "s4"

    def test_fallback_on_llm_failure(self, mock_llm: MagicMock, qd: QueryDecomposition) -> None:
        mock_llm.complete_structured.side_effect = RuntimeError("LLM down")
        agent = BatchJudgeAgent(llm=mock_llm)
        candidates = [
            _make_candidate("s1", 0.3),
            _make_candidate("s2", 0.9),
            _make_candidate("s3", 0.6),
        ]
        result = agent.judge(candidates, "query", qd)

        assert len(result) == 3
        assert result[0].session_id == "s2"
        assert result[0].relevance_score == 0.9
        assert result[0].matches_query is True
        assert result[0].reason == ""
        assert result[0].key_snippet == ""
        assert result[1].session_id == "s3"
        assert result[2].session_id == "s1"

    def test_prompt_contains_query_core_goal_intent(
        self, mock_llm: MagicMock, qd: QueryDecomposition
    ) -> None:
        mock_llm.complete_structured.return_value = BatchJudgeResult(
            judgments=[
                JudgeOutput(
                    session_id="s1",
                    relevance_score=0.9,
                    matches_query=True,
                    reason="",
                    key_snippet="",
                )
            ]
        )
        agent = BatchJudgeAgent(llm=mock_llm)
        candidates = [_make_candidate("s1", 0.5, task_raw="fix auth")]
        agent.judge(candidates, "how did I fix auth", qd)

        call_kwargs = mock_llm.complete_structured.call_args.kwargs
        prompt = call_kwargs.get("prompt", "")
        assert "how did I fix auth" in prompt
        assert "fix authentication bug" in prompt
        assert "implementation_lookup" in prompt

    def test_batched_into_groups_of_five(self, mock_llm: MagicMock, qd: QueryDecomposition) -> None:
        """11 candidates should result in 3 LLM calls (5 + 5 + 1)."""
        judgments = []
        for i in range(11):
            judgments.append(
                JudgeOutput(
                    session_id=f"s{i:02d}",
                    relevance_score=0.1 * i,
                    matches_query=True,
                    reason="",
                    key_snippet="",
                )
            )
        mock_llm.complete_structured.return_value = BatchJudgeResult(judgments=judgments)
        agent = BatchJudgeAgent(llm=mock_llm)
        candidates = [_make_candidate(f"s{i:02d}", 0.5) for i in range(11)]
        result = agent.judge(candidates, "query", qd)

        assert mock_llm.complete_structured.call_count == 3
        # Top 5 should be returned after deduplication and slicing
        assert len(result) == 5
        assert result[0].session_id == "s10"
        assert result[0].relevance_score == pytest.approx(1.0)

    def test_empty_candidates_returns_empty(
        self, mock_llm: MagicMock, qd: QueryDecomposition
    ) -> None:
        agent = BatchJudgeAgent(llm=mock_llm)
        result = agent.judge([], "query", qd)
        assert result == []
        mock_llm.complete_structured.assert_not_called()

    def test_fallback_on_none_response(self, mock_llm: MagicMock, qd: QueryDecomposition) -> None:
        mock_llm.complete_structured.return_value = None
        agent = BatchJudgeAgent(llm=mock_llm)
        candidates = [
            _make_candidate("s1", 0.4),
            _make_candidate("s2", 0.8),
        ]
        result = agent.judge(candidates, "query", qd)

        assert len(result) == 2
        assert result[0].session_id == "s2"
        assert result[0].relevance_score == 0.8

    def test_fallback_on_empty_judgments(self, mock_llm: MagicMock, qd: QueryDecomposition) -> None:
        mock_llm.complete_structured.return_value = BatchJudgeResult(judgments=[])
        agent = BatchJudgeAgent(llm=mock_llm)
        candidates = [
            _make_candidate("s1", 0.4),
            _make_candidate("s2", 0.8),
        ]
        result = agent.judge(candidates, "query", qd)

        assert len(result) == 2
        assert result[0].session_id == "s2"

    def test_ignores_unknown_session_ids(self, mock_llm: MagicMock, qd: QueryDecomposition) -> None:
        mock_llm.complete_structured.return_value = BatchJudgeResult(
            judgments=[
                JudgeOutput(
                    session_id="s1",
                    relevance_score=0.9,
                    matches_query=True,
                    reason="",
                    key_snippet="",
                ),
                JudgeOutput(
                    session_id="unknown",
                    relevance_score=0.8,
                    matches_query=True,
                    reason="",
                    key_snippet="",
                ),
            ]
        )
        agent = BatchJudgeAgent(llm=mock_llm)
        candidates = [_make_candidate("s1", 0.5)]
        result = agent.judge(candidates, "query", qd)

        assert len(result) == 1
        assert result[0].session_id == "s1"

    def test_candidates_without_session_id(
        self, mock_llm: MagicMock, qd: QueryDecomposition
    ) -> None:
        agent = BatchJudgeAgent(llm=mock_llm)
        candidates = [{"match_score": 0.5, "title": "no id"}]
        result = agent.judge(candidates, "query", qd)

        assert result == []
        mock_llm.complete_structured.assert_not_called()

    def test_rejected_judgments_stored(self, mock_llm: MagicMock, qd: QueryDecomposition) -> None:
        mock_llm.complete_structured.return_value = BatchJudgeResult(
            judgments=[
                JudgeOutput(
                    session_id="s1",
                    relevance_score=0.9,
                    matches_query=True,
                    reason="Direct match",
                    key_snippet="fix auth",
                ),
                JudgeOutput(
                    session_id="s2",
                    relevance_score=0.8,
                    matches_query=False,
                    reason="Not relevant",
                    key_snippet="",
                ),
                JudgeOutput(
                    session_id="s3",
                    relevance_score=0.7,
                    matches_query=False,
                    reason="Wrong topic",
                    key_snippet="",
                ),
            ]
        )
        agent = BatchJudgeAgent(llm=mock_llm)
        candidates = [
            _make_candidate("s1", 0.5),
            _make_candidate("s2", 0.5),
            _make_candidate("s3", 0.5),
        ]
        result = agent.judge(candidates, "fix auth", qd)

        assert len(result) == 1
        assert result[0].session_id == "s1"
        assert len(agent.rejected_judgments) == 2
        assert agent.rejected_judgments[0].session_id == "s2"
        assert agent.rejected_judgments[0].reason == "Not relevant"
        assert agent.rejected_judgments[1].session_id == "s3"
        assert agent.rejected_judgments[1].reason == "Wrong topic"

    def test_prompt_includes_matching_content(
        self, mock_llm: MagicMock, qd: QueryDecomposition
    ) -> None:
        mock_llm.complete_structured.return_value = BatchJudgeResult(
            judgments=[
                JudgeOutput(
                    session_id="s1",
                    relevance_score=0.9,
                    matches_query=True,
                    reason="",
                    key_snippet="",
                )
            ]
        )
        agent = BatchJudgeAgent(llm=mock_llm)
        candidates = [
            _make_candidate(
                "s1",
                0.5,
                task_raw="fix auth",
                reasoning_docs=["auth flow analysis", "database schema"],
                files_edited=["src/auth.py", "src/db.py"],
            )
        ]
        agent.judge(candidates, "fix auth", qd)

        call_kwargs = mock_llm.complete_structured.call_args.kwargs
        prompt = call_kwargs.get("prompt", "")
        assert "auth flow analysis" in prompt
        assert "src/auth.py" in prompt
        assert "src/db.py" not in prompt
        # database schema is included as fallback because only 2 items matched
        assert "database schema" in prompt

    def test_prompt_fallback_truncates_docs(
        self, mock_llm: MagicMock, qd: QueryDecomposition
    ) -> None:
        long_doc = "a" * 2000
        mock_llm.complete_structured.return_value = BatchJudgeResult(
            judgments=[
                JudgeOutput(
                    session_id="s1",
                    relevance_score=0.9,
                    matches_query=True,
                    reason="",
                    key_snippet="",
                )
            ]
        )
        agent = BatchJudgeAgent(llm=mock_llm)
        candidates = [
            _make_candidate(
                "s1",
                0.5,
                reasoning_docs=[long_doc, "b" * 2000],
            )
        ]
        agent.judge(candidates, "xyz_unmatched_query", qd)

        call_kwargs = mock_llm.complete_structured.call_args.kwargs
        prompt = call_kwargs.get("prompt", "")
        assert "a" * 1000 in prompt
        assert "a" * 1001 not in prompt


class TestBuildBatchPrompt:
    def test_includes_query(self, qd: QueryDecomposition) -> None:
        candidates = [_make_candidate("s1", 0.5, task_raw="task")]
        prompt = _build_batch_prompt(candidates, "my query", qd)
        assert "ORIGINAL QUERY: my query" in prompt

    def test_includes_core_goal(self, qd: QueryDecomposition) -> None:
        candidates = [_make_candidate("s1", 0.5)]
        prompt = _build_batch_prompt(candidates, "query", qd)
        assert "CORE GOAL: fix authentication bug" in prompt

    def test_includes_intent(self, qd: QueryDecomposition) -> None:
        candidates = [_make_candidate("s1", 0.5)]
        prompt = _build_batch_prompt(candidates, "query", qd)
        assert "INTENT CLASSIFICATION: implementation_lookup" in prompt
