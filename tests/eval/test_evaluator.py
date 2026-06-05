"""Tests for evaluator orchestrator."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from smartfork.eval.cache import EvalCache
from smartfork.eval.evaluator import EvalOrchestrator


class TestEvalOrchestrator:
    @pytest.fixture
    def mock_store(self, tmp_path: Path) -> MagicMock:
        store = MagicMock()
        store.get_all_sessions.return_value = [
            {
                "session_id": f"sess_{i}",
                "project_name": "proj_a" if i < 3 else "proj_b",
                "domains": ["auth"] if i % 2 == 0 else ["frontend"],
                "indexed_at": 1000,
                "task_raw": f"task {i}",
                "summary_doc": f"summary {i}",
                "tech_tags": ["tag1"],
                "files_edited": ["file.py"],
                "quality_tag": "solution_found",
                "duration_minutes": 10.0,
            }
            for i in range(6)
        ]
        store.get_session.return_value = {
            "session_id": "sess_0",
            "task_raw": "task 0",
            "summary_doc": "summary 0",
            "domains": ["auth"],
            "tech_tags": ["tag1"],
            "files_edited": ["file.py"],
            "quality_tag": "solution_found",
            "duration_minutes": 10.0,
        }
        return store

    def test_sample_sessions(self, mock_store: MagicMock, tmp_path: Path) -> None:
        cache = EvalCache(tmp_path / "cache.json")
        orch = EvalOrchestrator(
            store=mock_store,
            cache=cache,
            sample_size=4,
        )
        sessions = orch.sample_sessions()
        assert len(sessions) == 4
        # Should be stratified across projects
        projects = {s["project_name"] for s in sessions}
        assert len(projects) >= 1

    def test_generate_queries_uses_cache(self, mock_store: MagicMock, tmp_path: Path) -> None:
        cache = EvalCache(tmp_path / "cache.json")
        orch = EvalOrchestrator(
            store=mock_store,
            cache=cache,
            sample_size=2,
        )
        sessions = orch.sample_sessions()
        queries1 = orch.generate_queries(sessions)
        assert len(queries1) == 6  # 2 sessions × 3 queries

        # Second call should use cache
        queries2 = orch.generate_queries(sessions)
        assert len(queries2) == 6
        for i in range(len(queries1)):
            assert queries1[i].query == queries2[i].query

    def test_compute_metrics(self, mock_store: MagicMock, tmp_path: Path) -> None:
        from smartfork.eval.evaluator import EvalRun, ModeResult
        from smartfork.eval.judge import JudgeOutput

        cache = EvalCache(tmp_path / "cache.json")
        orch = EvalOrchestrator(store=mock_store, cache=cache, sample_size=2)

        run = EvalRun(
            sampled_session_ids=["s1", "s2"],
            queries=[],
            mode_results=[
                ModeResult(
                    mode="fast",
                    query="q1",
                    query_type="specific",
                    source_session_id="s1",
                    judgments=[
                        JudgeOutput(score=3, reason=""),
                        JudgeOutput(score=2, reason=""),
                        JudgeOutput(score=0, reason=""),
                        JudgeOutput(score=1, reason=""),
                        JudgeOutput(score=0, reason=""),
                    ],
                    latency_ms=100,
                    llm_calls=0,
                ),
                ModeResult(
                    mode="default",
                    query="q1",
                    query_type="specific",
                    source_session_id="s1",
                    judgments=[
                        JudgeOutput(score=3, reason=""),
                        JudgeOutput(score=3, reason=""),
                        JudgeOutput(score=2, reason=""),
                        JudgeOutput(score=0, reason=""),
                        JudgeOutput(score=0, reason=""),
                    ],
                    latency_ms=2000,
                    llm_calls=1,
                ),
            ],
        )
        orch._compute_metrics(run)

        assert "fast" in run.overall_metrics
        assert "default" in run.overall_metrics

        fast = run.overall_metrics["fast"]
        # P@5 = 2/5 = 0.4 (scores 3 and 2 are >= 2)
        assert fast["precision_at_5"] == pytest.approx(0.4, 0.01)
        assert fast["avg_latency_ms"] == 100.0
        assert fast["avg_llm_calls"] == 0.0

    def test_avg_helper(self) -> None:
        assert EvalOrchestrator._avg(x for x in [1.0, 2.0, 3.0]) == 2.0
        assert EvalOrchestrator._avg(x for x in []) == 0.0
