"""Tests for IndexIntelligence (fallback mode — no LLM required)."""

from smartfork.indexer.intelligence import (
    IndexIntelligence,
    _classify_quality,
    _extract_propositions,
    _extract_summary_fallback,
    _extract_tech_tags,
    _extract_title_fallback,
)
from smartfork.models.session import QualityTag, SessionDocument


def _make_session(**kwargs) -> SessionDocument:
    defaults = {
        "session_id": "test",
        "agent": "kilocode",
        "project_name": "test",
        "project_root": "/tmp",
        "task_raw": "Fix authentication bug in login endpoint",
        "reasoning_docs": [
            "The JWT token was expired because of a timezone mismatch.",
            "Fixed by using UTC timestamps consistently.",
            "Also added better error messages for expired tokens.",
        ],
        "files_edited": ["src/auth.py"],
        "files_read": ["src/middleware.py"],
        "files_mentioned": ["src/config.py"],
    }
    defaults.update(kwargs)
    return SessionDocument(**defaults)


class TestFallbackHelpers:
    def test_title_fallback(self) -> None:
        title = _extract_title_fallback("Fix authentication bug. Needs investigation.")
        assert "Fix authentication bug" in title

    def test_title_fallback_empty(self) -> None:
        title = _extract_title_fallback("")
        assert title == "Untitled Session"

    def test_summary_fallback(self) -> None:
        summary = _extract_summary_fallback(
            ["The JWT token was expired. Fixed it."],
            "Fix auth bug"
        )
        assert "Fix auth bug" in summary

    def test_quality_solution_found(self) -> None:
        tag = _classify_quality("Fixed the auth bug", ["Implemented the fix"])
        assert tag == QualityTag.SOLUTION_FOUND

    def test_quality_dead_end(self) -> None:
        tag = _classify_quality("Could not resolve the issue", ["Gave up"])
        assert tag == QualityTag.DEAD_END

    def test_tech_tags_extraction(self) -> None:
        tags = _extract_tech_tags(
            "Fix FastAPI JWT authentication in PostgreSQL",
            ["src/auth.py", "docker-compose.yml"]
        )
        assert "FastAPI" in tags
        assert "JWT" in tags
        assert "PostgreSQL" in tags
        assert "Docker" in tags

    def test_propositions_extraction(self) -> None:
        docs = [
            "The JWT token was expired due to timezone mismatch.",
            "Fixed by using UTC timestamps.",
        ]
        props = _extract_propositions(docs)
        assert len(props) >= 1
        assert "JWT" in props[0]


class TestIndexIntelligence:
    def test_enrich_without_llm(self) -> None:
        intelligence = IndexIntelligence(llm=None)
        session = _make_session()
        result = intelligence.enrich(session)

        # Title should be set
        assert len(result.task_raw) > 0
        # Summary should be set
        assert len(result.summary_doc) > 0
        # Quality should be classified
        assert result.quality_tag != QualityTag.UNKNOWN
        # Tech tags may have detected FastAPI/JWT
        assert isinstance(result.tech_tags, list)
        # Propositions extracted
        assert len(result.propositions) > 0

    def test_enrich_batch(self) -> None:
        intelligence = IndexIntelligence(llm=None)
        sessions = [
            _make_session(session_id="s1", task_raw="Fix auth bug"),
            _make_session(session_id="s2", task_raw="Setup Docker config"),
        ]
        from smartfork.indexer.indexer import ProgressEvent
        progress: list[ProgressEvent] = []
        def track(event: ProgressEvent) -> None:
            progress.append(event)

        result = intelligence.enrich_batch(sessions, progress_callback=track)
        assert len(result) == 2
        assert len(progress) >= 12
        assert result[0].session_id == "s1"
        assert result[1].session_id == "s2"

    def test_enrich_sets_title(self) -> None:
        intelligence = IndexIntelligence(llm=None)
        session = _make_session(task_raw="Setup project configuration and install dependencies")
        result = intelligence.enrich(session)
        assert len(result.task_raw) <= 80 or "..." in result.task_raw
