"""Tests for IndexIntelligence (fallback mode — no LLM required)."""

from unittest.mock import MagicMock

from smartfork.indexer.intelligence import (
    IndexIntelligence,
    _classify_quality,
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

    def test_enrich_batch(self) -> None:
        intelligence = IndexIntelligence(llm=None)
        sessions = [
            _make_session(session_id="s1", task_raw="Fix auth bug"),
            _make_session(session_id="s2", task_raw="Setup Docker config"),
        ]
        from smartfork.models.progress import ProgressEvent
        progress: list[ProgressEvent] = []
        def track(event: ProgressEvent) -> None:
            progress.append(event)

        result = intelligence.enrich_batch(sessions, progress_callback=track)
        assert len(result) == 2
        # Each session reports 2 progress events (start + done) = 4 total,
        # plus 1 extra "done" callback per session from enrich method = 4
        # Actually enrich() fires 2 callbacks per session: structured and done
        # So 2 sessions * 2 = 4 total
        assert len(progress) == 4
        assert result[0].session_id == "s1"
        assert result[1].session_id == "s2"

    def test_enrich_sets_title(self) -> None:
        intelligence = IndexIntelligence(llm=None)
        session = _make_session(task_raw="Setup project configuration and install dependencies")
        result = intelligence.enrich(session)
        assert len(result.task_raw) <= 80 or "..." in result.task_raw

    def test_enrich_with_llm_structured_call(self) -> None:
        from smartfork.models.enrichment import SessionEnrichment

        mock_llm = MagicMock()
        mock_llm.complete_structured.return_value = SessionEnrichment(
            title="Auth Bug Fix",
            summary="Fixed JWT auth bug by updating timestamps.",
            quality_tag=QualityTag.SOLUTION_FOUND,
            tech_tags=["JWT", "FastAPI"],
        )
        intelligence = IndexIntelligence(llm=mock_llm)
        session = _make_session()
        result = intelligence.enrich(session)

        assert mock_llm.complete_structured.call_count == 1
        assert result.task_raw == "Auth Bug Fix"
        assert result.summary_doc == "Fixed JWT auth bug by updating timestamps."
        assert result.quality_tag == QualityTag.SOLUTION_FOUND
        assert result.tech_tags == ["FastAPI", "JWT"]

    def test_enrich_with_llm_text_fallback(self) -> None:
        mock_llm = MagicMock()
        mock_llm.complete_structured.side_effect = AttributeError("no structured")
        mock_llm.complete.return_value = (
            '{"title": "Fallback Title", "summary": "Fallback summary.", '
            '"quality_tag": "partial", "tech_tags": ["Python"]}'
        )
        intelligence = IndexIntelligence(llm=mock_llm)
        session = _make_session()
        result = intelligence.enrich(session)

        assert mock_llm.complete_structured.call_count == 1
        assert mock_llm.complete.call_count == 1
        assert result.task_raw == "Fallback Title"
        assert result.summary_doc == "Fallback summary."
        assert result.quality_tag == QualityTag.PARTIAL
        assert result.tech_tags == ["Python"]

    def test_enrich_fallback_heuristics(self) -> None:
        intelligence = IndexIntelligence(llm=None)
        session = _make_session(task_raw="Implement OAuth2 flow")
        result = intelligence.enrich(session)

        assert len(result.task_raw) > 0
        assert "OAuth2" in result.task_raw
        assert len(result.summary_doc) > 0
        assert result.quality_tag != QualityTag.UNKNOWN
        assert isinstance(result.tech_tags, list)

    def test_enrich_batch_uses_structured(self) -> None:
        from smartfork.models.enrichment import SessionEnrichment

        mock_llm = MagicMock()
        mock_llm.complete_structured.return_value = SessionEnrichment(
            title="Batch Title",
            summary="Batch summary.",
            quality_tag=QualityTag.REFERENCE,
            tech_tags=["Docker"],
        )
        intelligence = IndexIntelligence(llm=mock_llm)
        sessions = [
            _make_session(session_id="s1"),
            _make_session(session_id="s2"),
        ]
        result = intelligence.enrich_batch(sessions)

        assert mock_llm.complete_structured.call_count == 2
        assert result[0].task_raw == "Batch Title"
        assert result[1].task_raw == "Batch Title"
