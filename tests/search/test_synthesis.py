"""Tests for SynthesisAgent."""

import pytest

from smartfork.models.search import JudgeOutput, QueryDecomposition, ResultCard
from smartfork.search.synthesis import SynthesisAgent


def _make_judge_output(
    session_id: str,
    relevance_score: float,
    reason: str = "",
    key_snippet: str = "",
    matches_query: bool = True,
) -> JudgeOutput:
    return JudgeOutput(
        session_id=session_id,
        relevance_score=relevance_score,
        matches_query=matches_query,
        reason=reason,
        key_snippet=key_snippet,
    )


def _make_candidate(
    session_id: str,
    title: str = "",
    project_name: str = "",
    time_ago: str = "",
    duration: str = "",
    files_summary: str = "",
    tags: list[str] | None = None,
    fork_command: str = "",
) -> dict:
    return {
        "session_id": session_id,
        "title": title or session_id,
        "project_name": project_name or "default_project",
        "time_ago": time_ago,
        "duration": duration,
        "files_summary": files_summary,
        "tags": tags or [],
        "fork_command": fork_command,
    }


@pytest.fixture
def agent() -> SynthesisAgent:
    return SynthesisAgent()


@pytest.fixture
def qd() -> QueryDecomposition:
    return QueryDecomposition(core_goal="test goal")


class TestBadgeMapping:
    def test_strong_badge_is_green(self, agent: SynthesisAgent, qd: QueryDecomposition) -> None:
        judgments = [_make_judge_output("s1", 0.81)]
        candidates = [_make_candidate("s1")]
        result = agent.synthesize(judgments, candidates, qd)

        assert len(result) == 1
        assert result[0].quality_badge == "[green]Strong match[/green]"

    def test_moderate_badge_is_yellow(self, agent: SynthesisAgent, qd: QueryDecomposition) -> None:
        judgments = [_make_judge_output("s1", 0.6)]
        candidates = [_make_candidate("s1")]
        result = agent.synthesize(judgments, candidates, qd)

        assert len(result) == 1
        assert result[0].quality_badge == "[yellow]Moderate match[/yellow]"

    def test_exactly_0_8_is_strong(self, agent: SynthesisAgent, qd: QueryDecomposition) -> None:
        judgments = [_make_judge_output("s1", 0.8)]
        candidates = [_make_candidate("s1")]
        result = agent.synthesize(judgments, candidates, qd)

        assert result[0].quality_badge == "[green]Strong match[/green]"

    def test_exactly_0_5_is_moderate(self, agent: SynthesisAgent, qd: QueryDecomposition) -> None:
        judgments = [_make_judge_output("s1", 0.5)]
        candidates = [_make_candidate("s1")]
        result = agent.synthesize(judgments, candidates, qd)

        assert result[0].quality_badge == "[yellow]Moderate match[/yellow]"

    def test_weak_badge_is_dropped(self, agent: SynthesisAgent, qd: QueryDecomposition) -> None:
        judgments = [_make_judge_output("s1", 0.49)]
        candidates = [_make_candidate("s1")]
        result = agent.synthesize(judgments, candidates, qd)

        assert result == []

    def test_zero_score_is_dropped(self, agent: SynthesisAgent, qd: QueryDecomposition) -> None:
        judgments = [_make_judge_output("s1", 0.0)]
        candidates = [_make_candidate("s1")]
        result = agent.synthesize(judgments, candidates, qd)

        assert result == []


class TestFieldPopulation:
    def test_excerpt_comes_from_key_snippet(self, agent: SynthesisAgent, qd: QueryDecomposition) -> None:
        judgments = [_make_judge_output("s1", 0.9, key_snippet="the quick snippet")]
        candidates = [_make_candidate("s1")]
        result = agent.synthesize(judgments, candidates, qd)

        assert len(result) == 1
        assert result[0].excerpt == "the quick snippet"

    def test_relevance_explanation_comes_from_reason(self, agent: SynthesisAgent, qd: QueryDecomposition) -> None:
        judgments = [_make_judge_output("s1", 0.9, reason="it matches well")]
        candidates = [_make_candidate("s1")]
        result = agent.synthesize(judgments, candidates, qd)

        assert result[0].relevance_explanation == "it matches well"

    def test_match_score_comes_from_relevance_score(self, agent: SynthesisAgent, qd: QueryDecomposition) -> None:
        judgments = [_make_judge_output("s1", 0.85)]
        candidates = [_make_candidate("s1")]
        result = agent.synthesize(judgments, candidates, qd)

        assert result[0].match_score == pytest.approx(0.85)

    def test_rank_assignment(self, agent: SynthesisAgent, qd: QueryDecomposition) -> None:
        judgments = [
            _make_judge_output("s1", 0.9),
            _make_judge_output("s2", 0.7),
            _make_judge_output("s3", 0.6),
        ]
        candidates = [
            _make_candidate("s1"),
            _make_candidate("s2"),
            _make_candidate("s3"),
        ]
        result = agent.synthesize(judgments, candidates, qd)

        assert [c.rank for c in result] == [1, 2, 3]

    def test_all_candidate_fields_mapped(self, agent: SynthesisAgent, qd: QueryDecomposition) -> None:
        judgments = [
            _make_judge_output(
                "s1",
                0.9,
                reason="great match",
                key_snippet="excerpt here",
            )
        ]
        candidates = [
            _make_candidate(
                "s1",
                title="My Session",
                project_name="alpha",
                time_ago="2 hours ago",
                duration="45 min",
                files_summary="3 files edited",
                tags=["python", "auth"],
                fork_command="smartfork fork s1",
            )
        ]
        result = agent.synthesize(judgments, candidates, qd)

        assert len(result) == 1
        card = result[0]
        assert card.session_id == "s1"
        assert card.title == "My Session"
        assert card.project_name == "alpha"
        assert card.match_score == pytest.approx(0.9)
        assert card.relevance_explanation == "great match"
        assert card.quality_badge == "[green]Strong match[/green]"
        assert card.time_ago == "2 hours ago"
        assert card.duration == "45 min"
        assert card.files_summary == "3 files edited"
        assert card.excerpt == "excerpt here"
        assert card.tags == ["python", "auth"]
        assert card.fork_command == "smartfork fork s1"


class TestEdgeCases:
    def test_empty_judgments_returns_empty(self, agent: SynthesisAgent, qd: QueryDecomposition) -> None:
        result = agent.synthesize([], [], qd)
        assert result == []

    def test_missing_candidate_falls_back_gracefully(self, agent: SynthesisAgent, qd: QueryDecomposition) -> None:
        judgments = [_make_judge_output("missing", 0.9)]
        candidates = []
        result = agent.synthesize(judgments, candidates, qd)

        assert len(result) == 1
        assert result[0].title == ""
        assert result[0].project_name == ""
        assert result[0].tags == []

    def test_candidate_without_session_id_is_ignored(self, agent: SynthesisAgent, qd: QueryDecomposition) -> None:
        judgments = [_make_judge_output("s1", 0.9)]
        candidates = [{"title": "no id"}]
        result = agent.synthesize(judgments, candidates, qd)

        assert len(result) == 1
        assert result[0].title == ""

    def test_mixed_scores_drop_weak_and_keep_strong(self, agent: SynthesisAgent, qd: QueryDecomposition) -> None:
        judgments = [
            _make_judge_output("s1", 0.9),
            _make_judge_output("s2", 0.4),
            _make_judge_output("s3", 0.75),
            _make_judge_output("s4", 0.3),
        ]
        candidates = [
            _make_candidate("s1"),
            _make_candidate("s2"),
            _make_candidate("s3"),
            _make_candidate("s4"),
        ]
        result = agent.synthesize(judgments, candidates, qd)

        assert len(result) == 2
        assert result[0].session_id == "s1"
        assert result[0].rank == 1
        assert result[1].session_id == "s3"
        assert result[1].rank == 2

    def test_preserves_judgment_order(self, agent: SynthesisAgent, qd: QueryDecomposition) -> None:
        judgments = [
            _make_judge_output("s2", 0.7),
            _make_judge_output("s1", 0.9),
        ]
        candidates = [
            _make_candidate("s2"),
            _make_candidate("s1"),
        ]
        result = agent.synthesize(judgments, candidates, qd)

        assert result[0].session_id == "s2"
        assert result[0].rank == 1
        assert result[1].session_id == "s1"
        assert result[1].rank == 2
