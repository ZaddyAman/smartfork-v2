"""Tests for eval report generation."""

from pathlib import Path

from smartfork.eval.evaluator import EvalRun, ModeResult
from smartfork.eval.judge import JudgeOutput
from smartfork.eval.report import EvalReport


class TestEvalReport:
    def test_render_json(self, tmp_path: Path) -> None:
        run = EvalRun(
            sampled_session_ids=["s1"],
            queries=[],
            mode_results=[
                ModeResult(
                    mode="fast",
                    query="q1",
                    query_type="specific",
                    source_session_id="s1",
                    judgments=[JudgeOutput(score=3, reason="")],
                    latency_ms=100,
                    llm_calls=0,
                )
            ],
            overall_metrics={
                "fast": {
                    "precision_at_5": 1.0,
                    "ndcg_at_5": 1.0,
                    "mrr": 1.0,
                    "map": 1.0,
                    "avg_latency_ms": 100,
                    "avg_llm_calls": 0,
                }
            },
            per_query_type_metrics={},
        )
        report = EvalReport(run)
        json_path = report.render_json(tmp_path)
        assert json_path.exists()
        content = json_path.read_text(encoding="utf-8")
        assert '"overall"' in content
        assert '"fast"' in content

    def test_render_html(self, tmp_path: Path) -> None:
        run = EvalRun(
            sampled_session_ids=["s1"],
            queries=[],
            mode_results=[
                ModeResult(
                    mode="fast",
                    query="q1",
                    query_type="specific",
                    source_session_id="s1",
                    judgments=[
                        JudgeOutput(score=3, reason="direct hit"),
                        JudgeOutput(score=0, reason="miss"),
                    ],
                    latency_ms=100,
                    llm_calls=0,
                )
            ],
            overall_metrics={
                "fast": {
                    "precision_at_5": 0.5,
                    "ndcg_at_5": 0.8,
                    "mrr": 1.0,
                    "map": 1.0,
                    "avg_latency_ms": 100,
                    "avg_llm_calls": 0,
                }
            },
            per_query_type_metrics={
                "fast_specific": {
                    "precision_at_5": 0.5,
                    "ndcg_at_5": 0.8,
                    "mrr": 1.0,
                    "map": 1.0,
                    "avg_latency_ms": 100,
                }
            },
        )
        report = EvalReport(run)
        html_path = report.render_html(tmp_path)
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert "SmartFork Search Evaluation" in content
        assert "fast" in content
        assert "specific" in content
