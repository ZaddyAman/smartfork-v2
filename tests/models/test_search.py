"""Tests for search models."""

from smartfork.models.search import (
    QueryDecomposition,
    ResultCard,
    SearchIntent,
    SearchResult,
)


class TestSearchIntent:
    def test_enum_values(self) -> None:
        assert SearchIntent.ERROR_RECALL == "error_recall"
        assert SearchIntent.CONTINUATION == "continuation"
        assert SearchIntent.IMPLEMENTATION_LOOKUP == "implementation_lookup"
        assert SearchIntent.DECISION_HUNTING == "decision_hunting"
        assert SearchIntent.PATTERN_HUNTING == "pattern_hunting"
        assert SearchIntent.VAGUE_MEMORY == "vague_memory"
        assert SearchIntent.TEMPORAL_LOOKUP == "temporal_lookup"


class TestQueryDecomposition:
    def test_defaults(self) -> None:
        qd = QueryDecomposition(core_goal="find that thing")
        assert qd.prefer_code is False
        assert qd.prefer_recent is False
        assert qd.entities == {}
        assert qd.search_variants == []
        assert qd.intent == "vague_memory"
        assert qd.metadata_filters == {}

    def test_full_instantiation(self) -> None:
        qd = QueryDecomposition(
            core_goal="fix import error",
            search_variants=["python import error fix", "ModuleNotFoundError resolution"],
            entities={"technologies": ["python"], "concepts": ["import", "ModuleNotFoundError"]},
            intent="error_recall",
            metadata_filters={"project": "myproject"},
            prefer_code=True,
            prefer_recent=True,
        )
        assert qd.intent == "error_recall"
        assert len(qd.entities) == 2
        assert len(qd.search_variants) == 2
        assert qd.prefer_code is True
        assert qd.metadata_filters == {"project": "myproject"}


class TestSearchResult:
    def test_defaults(self) -> None:
        sr = SearchResult(
            session_id="abc",
            title="Title",
            project_name="proj",
            match_score=0.95,
        )
        assert sr.match_score == 0.95
        assert sr.relevance_explanation == ""
        assert sr.supersession_status == "none"
        assert sr.files_edited == []

    def test_full_instantiation(self) -> None:
        sr = SearchResult(
            session_id="abc",
            title="Fixed the auth bug",
            project_name="myproject",
            match_score=0.95,
            relevance_explanation="matched on error pattern",
            quality_tag="solution_found",
            supersession_status="superseding",
            duration_minutes=12.5,
            session_start=1_700_000_000_000,
            files_edited=["auth.py"],
            domains=["backend", "auth"],
            languages=["python"],
            summary_preview="summary...",
            task_preview="task...",
        )
        assert sr.match_score == 0.95
        assert sr.supersession_status == "superseding"
        assert len(sr.domains) == 2


class TestResultCard:
    def test_defaults(self) -> None:
        rc = ResultCard(
            rank=1,
            session_id="abc",
            title="Title",
            project_name="proj",
            match_score=0.9,
        )
        assert rc.rank == 1
        assert rc.quality_badge == ""
        assert rc.supersession_note == ""

    def test_full_instantiation(self) -> None:
        rc = ResultCard(
            rank=1,
            session_id="abc",
            title="Fixed auth bug",
            project_name="myproject",
            match_score=0.9,
            relevance_explanation="good match",
            quality_badge="✓ Solved",
            supersession_note="Fixes earlier attempt",
            time_ago="2 days ago",
            duration="15 min",
            files_summary="auth.py",
            excerpt="excerpt text",
            fork_command="smartfork fork abc",
        )
        assert rc.rank == 1
        assert rc.quality_badge == "✓ Solved"
