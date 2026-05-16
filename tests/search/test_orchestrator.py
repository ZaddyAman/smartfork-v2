"""Tests for SearchOrchestrator."""

from unittest.mock import MagicMock

import pytest

from smartfork.models.search import (
    JudgeOutput,
    QueryDecomposition,
    ResultCard,
)
from smartfork.search.orchestrator import SearchOrchestrator


def _make_qd(variants: list[str] | None = None) -> QueryDecomposition:
    return QueryDecomposition(
        core_goal="test query",
        search_variants=variants if variants is not None else ["test query"],
    )


def _make_candidate(
    session_id: str,
    match_score: float = 0.5,
    relevance_score: float | None = None,
    title: str = "",
) -> dict:
    cand: dict = {
        "session_id": session_id,
        "title": title or session_id,
        "match_score": match_score,
        "project_name": "test_project",
        "content": f"content for {session_id}",
        "time_ago": "2 hours ago",
        "duration": "30 min",
        "files_summary": "1 file edited",
        "tags": ["python"],
        "fork_command": f"smartfork fork {session_id}",
    }
    if relevance_score is not None:
        cand["relevance_score"] = relevance_score
    return cand


def _make_judgment(
    session_id: str,
    relevance_score: float = 0.9,
    matches_query: bool = True,
    reason: str = "good match",
    key_snippet: str = "snippet",
) -> JudgeOutput:
    return JudgeOutput(
        session_id=session_id,
        relevance_score=relevance_score,
        matches_query=matches_query,
        reason=reason,
        key_snippet=key_snippet,
    )


def _make_result_card(session_id: str, rank: int = 1) -> ResultCard:
    return ResultCard(
        rank=rank,
        session_id=session_id,
        title=session_id,
        project_name="test_project",
        match_score=0.9,
        fork_command=f"smartfork fork {session_id}",
    )


@pytest.fixture
def orchestrator() -> SearchOrchestrator:
    return SearchOrchestrator(
        decomposer=MagicMock(),
        retriever=MagicMock(),
        reranker=MagicMock(),
        judge=MagicMock(),
        synthesis=MagicMock(),
    )


class TestHappyPath:
    def test_stages_called_in_order(self, orchestrator: SearchOrchestrator) -> None:
        qd = _make_qd(["v1", "v2"])
        orchestrator.decomposer.decompose.return_value = qd
        orchestrator.retriever.retrieve.return_value = [
            _make_candidate("s1"),
            _make_candidate("s2"),
        ]
        orchestrator.reranker.rerank.return_value = [
            _make_candidate("s2", relevance_score=0.9),
            _make_candidate("s1", relevance_score=0.8),
        ]
        orchestrator.judge.judge.return_value = [
            _make_judgment("s2"),
            _make_judgment("s1"),
        ]
        orchestrator.synthesis.synthesize.return_value = [
            _make_result_card("s2", rank=1),
            _make_result_card("s1", rank=2),
        ]

        result = orchestrator.search("test query", top_k=2)

        assert len(result) == 2
        assert result[0].session_id == "s2"
        assert result[1].session_id == "s1"

        orchestrator.decomposer.decompose.assert_called_once_with("test query")
        orchestrator.retriever.retrieve.assert_called_once_with(
            qd, top_k=2, project_filter=None, quality_filter=None
        )
        orchestrator.reranker.rerank.assert_called_once()
        orchestrator.judge.judge.assert_called_once()
        orchestrator.synthesis.synthesize.assert_called_once()

    def test_returns_result_cards(self, orchestrator: SearchOrchestrator) -> None:
        orchestrator.decomposer.decompose.return_value = _make_qd()
        orchestrator.retriever.retrieve.return_value = [_make_candidate("s1")]
        orchestrator.reranker.rerank.return_value = [_make_candidate("s1", relevance_score=0.9)]
        orchestrator.judge.judge.return_value = [_make_judgment("s1")]
        orchestrator.synthesis.synthesize.return_value = [_make_result_card("s1")]

        result = orchestrator.search("test query")

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], ResultCard)


class TestTopKSlicing:
    def test_sliced_to_top_k(self, orchestrator: SearchOrchestrator) -> None:
        orchestrator.decomposer.decompose.return_value = _make_qd()
        orchestrator.retriever.retrieve.return_value = [
            _make_candidate(f"s{i}") for i in range(10)
        ]
        orchestrator.reranker.rerank.return_value = [
            _make_candidate(f"s{i}", relevance_score=1.0 - i * 0.05)
            for i in range(10)
        ]
        orchestrator.judge.judge.return_value = [
            _make_judgment(f"s{i}") for i in range(10)
        ]
        orchestrator.synthesis.synthesize.return_value = [
            _make_result_card(f"s{i}", rank=i + 1) for i in range(10)
        ]

        result = orchestrator.search("test query", top_k=3)

        assert len(result) == 3


class TestFilterPassThrough:
    def test_project_and_quality_filters(
        self, orchestrator: SearchOrchestrator
    ) -> None:
        qd = _make_qd()
        orchestrator.decomposer.decompose.return_value = qd
        orchestrator.retriever.retrieve.return_value = [_make_candidate("s1")]
        orchestrator.reranker.rerank.return_value = [_make_candidate("s1", relevance_score=0.9)]
        orchestrator.judge.judge.return_value = [_make_judgment("s1")]
        orchestrator.synthesis.synthesize.return_value = [_make_result_card("s1")]

        orchestrator.search(
            "test query",
            top_k=5,
            project_filter="alpha",
            quality_filter="solution_found",
        )

        orchestrator.retriever.retrieve.assert_called_once_with(
            qd,
            top_k=5,
            project_filter="alpha",
            quality_filter="solution_found",
        )


class TestDecomposerFallback:
    def test_exception_uses_original_query(
        self, orchestrator: SearchOrchestrator
    ) -> None:
        orchestrator.decomposer.decompose.side_effect = RuntimeError("LLM down")
        orchestrator.retriever.retrieve.return_value = [_make_candidate("s1")]
        orchestrator.reranker.rerank.return_value = [_make_candidate("s1", relevance_score=0.9)]
        orchestrator.judge.judge.return_value = [_make_judgment("s1")]
        orchestrator.synthesis.synthesize.return_value = [_make_result_card("s1")]

        result = orchestrator.search("original query")

        assert len(result) == 1
        call_args = orchestrator.retriever.retrieve.call_args
        qd_passed = call_args.args[0]
        assert isinstance(qd_passed, QueryDecomposition)
        assert qd_passed.core_goal == "original query"
        assert qd_passed.search_variants == ["original query"]


class TestRerankerFallback:
    def test_exception_falls_back_to_match_score_sorting(
        self, orchestrator: SearchOrchestrator
    ) -> None:
        orchestrator.decomposer.decompose.return_value = _make_qd()
        orchestrator.retriever.retrieve.return_value = [
            _make_candidate("s1", match_score=0.3),
            _make_candidate("s2", match_score=0.9),
            _make_candidate("s3", match_score=0.6),
        ]
        orchestrator.reranker.rerank.side_effect = RuntimeError("LLM down")
        orchestrator.judge.judge.return_value = [
            _make_judgment("s2"),
            _make_judgment("s3"),
            _make_judgment("s1"),
        ]
        orchestrator.synthesis.synthesize.return_value = [
            _make_result_card("s2", rank=1),
            _make_result_card("s3", rank=2),
            _make_result_card("s1", rank=3),
        ]

        result = orchestrator.search("test query", top_k=3)

        assert len(result) == 3
        # Verify judge received candidates sorted by match_score descending
        judge_call_args = orchestrator.judge.judge.call_args
        reranked_passed = judge_call_args.args[0]
        assert [c["session_id"] for c in reranked_passed] == ["s2", "s3", "s1"]


class TestJudgeFallback:
    def test_exception_returns_warning_badge_cards(
        self, orchestrator: SearchOrchestrator
    ) -> None:
        orchestrator.decomposer.decompose.return_value = _make_qd()
        orchestrator.retriever.retrieve.return_value = [
            _make_candidate("s1", match_score=0.8),
        ]
        orchestrator.reranker.rerank.return_value = [
            _make_candidate("s1", relevance_score=0.85),
        ]
        orchestrator.judge.judge.side_effect = RuntimeError("LLM down")

        result = orchestrator.search("test query", top_k=1)

        assert len(result) == 1
        assert result[0].session_id == "s1"
        assert result[0].quality_badge == "[yellow]Unverified match[/yellow]"
        orchestrator.synthesis.synthesize.assert_not_called()


class TestSynthesisFallback:
    def test_exception_returns_raw_cards(
        self, orchestrator: SearchOrchestrator
    ) -> None:
        orchestrator.decomposer.decompose.return_value = _make_qd()
        orchestrator.retriever.retrieve.return_value = [
            _make_candidate("s1", match_score=0.8),
        ]
        orchestrator.reranker.rerank.return_value = [
            _make_candidate("s1", relevance_score=0.85),
        ]
        orchestrator.judge.judge.return_value = [_make_judgment("s1", relevance_score=0.85)]
        orchestrator.synthesis.synthesize.side_effect = RuntimeError("synthesis failed")

        result = orchestrator.search("test query", top_k=1)

        assert len(result) == 1
        assert result[0].session_id == "s1"
        assert result[0].match_score == pytest.approx(0.85)
        assert result[0].quality_badge == "[green]Strong match[/green]"


class TestJudgeDropsAll:
    def test_returns_empty_list(self, orchestrator: SearchOrchestrator) -> None:
        orchestrator.decomposer.decompose.return_value = _make_qd()
        orchestrator.retriever.retrieve.return_value = [_make_candidate("s1")]
        orchestrator.reranker.rerank.return_value = [_make_candidate("s1", relevance_score=0.9)]
        orchestrator.judge.judge.return_value = []

        result = orchestrator.search("test query")

        assert result == []
        orchestrator.synthesis.synthesize.assert_not_called()

    def test_last_empty_reasoning_populated(self, orchestrator: SearchOrchestrator) -> None:
        from smartfork.models.search import JudgeOutput

        orchestrator.decomposer.decompose.return_value = _make_qd()
        orchestrator.retriever.retrieve.return_value = [_make_candidate("s1")]
        orchestrator.reranker.rerank.return_value = [_make_candidate("s1", relevance_score=0.9)]
        orchestrator.judge.judge.return_value = []
        orchestrator.judge.rejected_judgments = [
            JudgeOutput(
                session_id="s1",
                relevance_score=0.3,
                matches_query=False,
                reason="Not about the query topic",
                key_snippet="",
            )
        ]

        result = orchestrator.search("test query")

        assert result == []
        assert orchestrator.last_empty_reasoning != ""
        assert "s1" in orchestrator.last_empty_reasoning
        assert "Not about the query topic" in orchestrator.last_empty_reasoning


class TestEmptyCandidates:
    def test_returns_empty_list(self, orchestrator: SearchOrchestrator) -> None:
        orchestrator.decomposer.decompose.return_value = _make_qd()
        orchestrator.retriever.retrieve.return_value = []

        result = orchestrator.search("test query")

        assert result == []
        orchestrator.reranker.rerank.assert_not_called()
        orchestrator.judge.judge.assert_not_called()
        orchestrator.synthesis.synthesize.assert_not_called()


class TestProgressOutput:
    def test_prints_stage_messages(
        self, orchestrator: SearchOrchestrator, capsys: pytest.CaptureFixture
    ) -> None:
        orchestrator.decomposer.decompose.return_value = _make_qd(["v1", "v2", "v3"])
        orchestrator.retriever.retrieve.return_value = [
            _make_candidate(f"s{i}") for i in range(6)
        ]
        orchestrator.reranker.rerank.return_value = [
            _make_candidate(f"s{i}", relevance_score=0.9) for i in range(6)
        ]
        orchestrator.judge.judge.return_value = [
            _make_judgment(f"s{i}") for i in range(6)
        ]
        orchestrator.synthesis.synthesize.return_value = [
            _make_result_card(f"s{i}", rank=i + 1) for i in range(6)
        ]

        orchestrator.search("test query", top_k=2)

        captured = capsys.readouterr()
        assert "Decomposing query..." in captured.out
        assert "Searching 3 variants..." in captured.out
        assert "Reranking 6 candidates..." in captured.out
        assert "Judging relevance..." in captured.out
        assert "Synthesizing results..." in captured.out

    def test_no_searching_when_no_variants(
        self, orchestrator: SearchOrchestrator, capsys: pytest.CaptureFixture
    ) -> None:
        orchestrator.decomposer.decompose.return_value = _make_qd([])
        orchestrator.retriever.retrieve.return_value = []

        result = orchestrator.search("test query")

        captured = capsys.readouterr()
        assert "Searching 0 variants..." in captured.out
        assert result == []
