"""Tests for relevance judge."""

from smartfork.eval.judge import RelevanceJudge


class TestRelevanceJudge:
    def test_no_llm_returns_neutral(self) -> None:
        judge = RelevanceJudge(llm=None)
        sess = {
            "task_raw": "Fix OAuth",
            "summary_doc": "Fixed OAuth bug",
            "files_edited": ["auth.py"],
            "domains": ["auth"],
            "tech_tags": ["OAuth"],
            "quality_tag": "solution_found",
            "duration_minutes": 10.0,
        }
        result = judge.judge("oauth issue", sess)
        assert result.score == 1
        assert "No LLM" in result.reason

    def test_batch_judging(self) -> None:
        judge = RelevanceJudge(llm=None)
        sessions = [
            {
                "task_raw": "A",
                "summary_doc": "",
                "files_edited": [],
                "domains": [],
                "tech_tags": [],
                "quality_tag": "",
                "duration_minutes": 0.0,
            },
            {
                "task_raw": "B",
                "summary_doc": "",
                "files_edited": [],
                "domains": [],
                "tech_tags": [],
                "quality_tag": "",
                "duration_minutes": 0.0,
            },
        ]
        results = judge.judge_batch("query", sessions)
        assert len(results) == 2
        assert all(r.score == 1 for r in results)
