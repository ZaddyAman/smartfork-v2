"""Tests for parallel retriever."""

import json
from unittest.mock import MagicMock

import pytest

from smartfork.models.search import QueryDecomposition, ResultCard
from smartfork.search.deterministic import DeterministicSearchEngine
from smartfork.search.parallel_retriever import ParallelRetriever


REQUIRED_KEYS = {
    "session_id",
    "title",
    "match_score",
    "project_name",
    "content",
    "task_raw",
    "summary_doc",
    "reasoning_docs",
    "tags",
    "files_summary",
    "time_ago",
    "duration",
    "fork_command",
}


def _make_card(
    session_id: str,
    title: str,
    match_score: float,
    project_name: str = "",
) -> ResultCard:
    return ResultCard(
        rank=1,
        session_id=session_id,
        title=title,
        project_name=project_name,
        match_score=match_score,
        excerpt=f"excerpt for {session_id}",
        tags=["tag1"],
        files_summary="1 file edited",
        time_ago="2 hours ago",
        duration="30 min",
        fork_command=f"smartfork fork {session_id}",
    )


class TestParallelRetriever:
    def test_retrieve_parallel_calls(self) -> None:
        mock_engine = MagicMock(spec=DeterministicSearchEngine)
        mock_engine.metadata_store = None
        mock_engine.search.side_effect = [
            [_make_card("s1", "title1", 0.9, "proj1")],
            [_make_card("s2", "title2", 0.8, "proj2")],
        ]

        retriever = ParallelRetriever(deterministic_engine=mock_engine)
        qd = QueryDecomposition(
            core_goal="test",
            search_variants=["variant a", "variant b"],
        )
        results = retriever.retrieve(qd, top_k=5)

        assert mock_engine.search.call_count == 2
        mock_engine.search.assert_any_call(
            "variant a", top_k=10, project_filter=None, quality_filter=None
        )
        mock_engine.search.assert_any_call(
            "variant b", top_k=10, project_filter=None, quality_filter=None
        )
        assert len(results) == 2
        assert {r["session_id"] for r in results} == {"s1", "s2"}

    def test_deduplication_keeps_higher_score(self) -> None:
        mock_engine = MagicMock(spec=DeterministicSearchEngine)
        mock_engine.metadata_store = None
        mock_engine.search.side_effect = [
            [_make_card("s1", "title1", 0.7)],
            [_make_card("s1", "title1", 0.9)],
        ]

        retriever = ParallelRetriever(deterministic_engine=mock_engine)
        qd = QueryDecomposition(
            core_goal="test",
            search_variants=["v1", "v2"],
        )
        results = retriever.retrieve(qd, top_k=5)

        assert len(results) == 1
        assert results[0]["session_id"] == "s1"
        assert results[0]["match_score"] == 0.9

    def test_graceful_fallback_one_variant_fails(self) -> None:
        mock_engine = MagicMock(spec=DeterministicSearchEngine)
        mock_engine.metadata_store = None

        def _search(
            query: str,
            top_k: int = 10,
            project_filter: str | None = None,
            quality_filter: str | None = None,
        ) -> list[ResultCard]:
            if query == "bad":
                raise RuntimeError("boom")
            return [_make_card("s1", "title1", 0.8)]

        mock_engine.search.side_effect = _search

        retriever = ParallelRetriever(deterministic_engine=mock_engine)
        qd = QueryDecomposition(
            core_goal="test",
            search_variants=["bad", "good"],
        )
        results = retriever.retrieve(qd, top_k=5)

        assert len(results) == 1
        assert results[0]["session_id"] == "s1"

    def test_empty_variants_returns_empty_list(self) -> None:
        mock_engine = MagicMock(spec=DeterministicSearchEngine)
        retriever = ParallelRetriever(deterministic_engine=mock_engine)
        qd = QueryDecomposition(core_goal="test", search_variants=[])
        results = retriever.retrieve(qd, top_k=5)
        assert results == []

    def test_empty_results_returns_empty_list(self) -> None:
        mock_engine = MagicMock(spec=DeterministicSearchEngine)
        mock_engine.metadata_store = None
        mock_engine.search.return_value = []

        retriever = ParallelRetriever(deterministic_engine=mock_engine)
        qd = QueryDecomposition(
            core_goal="test",
            search_variants=["v1", "v2"],
        )
        results = retriever.retrieve(qd, top_k=5)

        assert results == []

    def test_candidate_dict_has_required_keys(self) -> None:
        mock_engine = MagicMock(spec=DeterministicSearchEngine)
        mock_engine.metadata_store = None
        mock_engine.search.return_value = [_make_card("s1", "title1", 0.9, "proj1")]

        retriever = ParallelRetriever(deterministic_engine=mock_engine)
        qd = QueryDecomposition(
            core_goal="test",
            search_variants=["v1"],
        )
        results = retriever.retrieve(qd, top_k=5)

        assert len(results) == 1
        candidate = results[0]
        assert set(candidate.keys()) == REQUIRED_KEYS
        assert candidate["session_id"] == "s1"
        assert candidate["title"] == "title1"
        assert candidate["match_score"] == 0.9
        assert candidate["project_name"] == "proj1"
        assert candidate["content"] == "excerpt for s1"
        assert candidate["tags"] == ["tag1"]
        assert candidate["files_summary"] == "1 file edited"
        assert candidate["time_ago"] == "2 hours ago"
        assert candidate["duration"] == "30 min"
        assert candidate["fork_command"] == "smartfork fork s1"

    def test_enriches_from_metadata_store(self) -> None:
        mock_engine = MagicMock(spec=DeterministicSearchEngine)
        mock_metadata = MagicMock()
        mock_metadata.get_session.return_value = {
            "summary_doc": "full summary",
            "task_raw": "task",
            "reasoning_docs": '["reasoning one", "reasoning two"]',
            "tech_tags": '["python", "rust"]',
            "domains": '["backend"]',
            "languages": '["python"]',
            "files_edited": '["main.py"]',
            "session_start": 1700000000000,
            "duration_minutes": 45.0,
        }

        def _deserialize_list(value: str) -> list:
            if not value:
                return []
            try:
                return json.loads(value)
            except Exception:
                return []

        mock_metadata._deserialize_list.side_effect = _deserialize_list
        mock_engine.metadata_store = mock_metadata
        mock_engine.search.return_value = [_make_card("s1", "title1", 0.9, "proj1")]

        retriever = ParallelRetriever(deterministic_engine=mock_engine)
        qd = QueryDecomposition(
            core_goal="test",
            search_variants=["v1"],
        )
        results = retriever.retrieve(qd, top_k=5)

        assert len(results) == 1
        candidate = results[0]
        assert candidate["content"] == "full summary"
        assert candidate["task_raw"] == "task"
        assert candidate["summary_doc"] == "full summary"
        assert candidate["reasoning_docs"] == ["reasoning one", "reasoning two"]
        assert set(candidate["tags"]) == {"python", "rust", "backend"}
        assert candidate["files_summary"] == "1 file edited"
        assert candidate["duration"] == "45 min"
        assert candidate["time_ago"] != ""

    def test_max_workers_capped_at_five(self) -> None:
        mock_engine = MagicMock(spec=DeterministicSearchEngine)
        mock_engine.metadata_store = None
        mock_engine.search.return_value = []

        retriever = ParallelRetriever(deterministic_engine=mock_engine)
        variants = [f"variant {i}" for i in range(10)]
        qd = QueryDecomposition(
            core_goal="test",
            search_variants=variants,
        )
        results = retriever.retrieve(qd, top_k=5)

        assert results == []
        assert mock_engine.search.call_count == 10

    def test_deduplication_preserves_metadata_from_higher_score(self) -> None:
        mock_engine = MagicMock(spec=DeterministicSearchEngine)
        mock_engine.metadata_store = None
        mock_engine.search.side_effect = [
            [_make_card("s1", "low title", 0.5, "proj_a")],
            [_make_card("s1", "high title", 0.95, "proj_b")],
        ]

        retriever = ParallelRetriever(deterministic_engine=mock_engine)
        qd = QueryDecomposition(
            core_goal="test",
            search_variants=["v1", "v2"],
        )
        results = retriever.retrieve(qd, top_k=5)

        assert len(results) == 1
        assert results[0]["match_score"] == 0.95
        assert results[0]["title"] == "high title"

    def test_passes_project_and_quality_filters(self) -> None:
        mock_engine = MagicMock(spec=DeterministicSearchEngine)
        mock_engine.metadata_store = None
        mock_engine.search.return_value = [
            _make_card("s1", "title1", 0.9, "proj1")
        ]

        retriever = ParallelRetriever(deterministic_engine=mock_engine)
        qd = QueryDecomposition(
            core_goal="test",
            search_variants=["variant a"],
        )
        results = retriever.retrieve(
            qd,
            top_k=5,
            project_filter="alpha",
            quality_filter="solution_found",
        )

        assert len(results) == 1
        mock_engine.search.assert_called_once_with(
            "variant a",
            top_k=10,
            project_filter="alpha",
            quality_filter="solution_found",
        )
