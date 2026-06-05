"""Tests for MultiSessionSynthesizer."""

from smartfork.models.relationship import Chain, TimelineSummary
from smartfork.models.session import QualityTag, SessionDocument
from smartfork.search.multi_session_synthesizer import MultiSessionSynthesizer


def _make_session(
    session_id: str,
    session_start: int = 0,
    task_raw: str = "",
    summary_doc: str = "",
    quality_tag: QualityTag = QualityTag.UNKNOWN,
) -> SessionDocument:
    return SessionDocument(
        session_id=session_id,
        agent="test",
        project_name="proj",
        project_root="/tmp",
        session_start=session_start,
        task_raw=task_raw,
        summary_doc=summary_doc,
        quality_tag=quality_tag,
    )


class _MockLLM:
    """Configurable mock LLM for testing structured synthesis."""

    def __init__(
        self,
        return_value: object | None = None,
        raise_on_structured: bool = False,
        raise_on_complete: bool = False,
    ) -> None:
        self.return_value = return_value
        self.raise_on_structured = raise_on_structured
        self.raise_on_complete = raise_on_complete

    def complete_structured(
        self,
        prompt: str,
        output_schema: type,
        max_tokens: int = 500,
        temperature: float = 0.1,
    ) -> object:
        if self.raise_on_structured:
            raise RuntimeError("structured LLM failure")
        return self.return_value

    def complete(
        self,
        prompt: str,
        max_tokens: int = 500,
        temperature: float = 0.1,
    ) -> str:
        if self.raise_on_complete:
            raise RuntimeError("text LLM failure")
        return ""


class TestSynthesizeWithLLM:
    def test_synthesize_with_llm(self) -> None:
        s1 = _make_session(
            "s1",
            session_start=1000,
            task_raw="Auth setup",
            quality_tag=QualityTag.PARTIAL,
        )
        s2 = _make_session(
            "s2",
            session_start=2000,
            task_raw="Auth fix",
            quality_tag=QualityTag.SOLUTION_FOUND,
        )
        chain = Chain(sessions=[s1, s2])

        llm_result = TimelineSummary(
            narrative="Worked on auth and fixed it.",
            timeline=[],
            suggested_fork_session_id="s2",
            resolution_status="solved",
        )
        mock_llm = _MockLLM(return_value=llm_result)
        synthesizer = MultiSessionSynthesizer(llm=mock_llm)

        result = synthesizer.synthesize_timeline("auth work", [chain])

        assert result.narrative == "Worked on auth and fixed it."
        assert len(result.timeline) == 2
        assert result.timeline[0].session_id == "s1"
        assert result.timeline[1].session_id == "s2"
        assert result.suggested_fork_session_id == "s2"
        assert result.resolution_status == "solved"

    def test_synthesize_llm_returns_dict(self) -> None:
        s1 = _make_session(
            "s1",
            session_start=1000,
            task_raw="Auth setup",
            quality_tag=QualityTag.PARTIAL,
        )
        chain = Chain(sessions=[s1])

        mock_llm = _MockLLM(
            return_value={
                "narrative": "Dict narrative",
                "resolution_status": "ongoing",
                "suggested_fork_session_id": "s1",
            }
        )
        synthesizer = MultiSessionSynthesizer(llm=mock_llm)

        result = synthesizer.synthesize_timeline("auth", [chain])
        assert result.narrative == "Dict narrative"
        assert result.resolution_status == "ongoing"
        assert result.suggested_fork_session_id == "s1"
        assert len(result.timeline) == 1


class TestSynthesizeFallback:
    def test_synthesize_llm_failure_fallback(self) -> None:
        s1 = _make_session(
            "s1",
            session_start=1000,
            task_raw="Auth setup",
            quality_tag=QualityTag.PARTIAL,
        )
        s2 = _make_session(
            "s2",
            session_start=2000,
            task_raw="Auth fix",
            quality_tag=QualityTag.SOLUTION_FOUND,
        )
        chain = Chain(sessions=[s1, s2])

        mock_llm = _MockLLM(raise_on_structured=True)
        synthesizer = MultiSessionSynthesizer(llm=mock_llm)

        result = synthesizer.synthesize_timeline("auth work", [chain])

        # Fallback returns raw chain info without LLM narrative
        assert "Query:" in result.narrative
        assert "s1" in result.narrative
        assert "s2" in result.narrative
        assert len(result.timeline) == 2
        assert result.suggested_fork_session_id == "s2"
        assert result.resolution_status == "solved"

    def test_synthesize_no_llm(self) -> None:
        s1 = _make_session("s1", session_start=1000, task_raw="Auth setup")
        chain = Chain(sessions=[s1])

        synthesizer = MultiSessionSynthesizer(llm=None)
        result = synthesizer.synthesize_timeline("auth", [chain])

        assert "Query:" in result.narrative
        assert len(result.timeline) == 1
        assert result.suggested_fork_session_id == "s1"


class TestEdgeCases:
    def test_synthesize_empty_chains(self) -> None:
        synthesizer = MultiSessionSynthesizer(llm=None)
        result = synthesizer.synthesize_timeline("auth", [])

        assert result.narrative == "No related sessions found."
        assert result.timeline == []
        assert result.suggested_fork_session_id == ""
        assert result.resolution_status == "unknown"

    def test_suggested_fork_points_to_latest(self) -> None:
        s1 = _make_session("s1", session_start=1000, task_raw="First")
        s2 = _make_session("s2", session_start=5000, task_raw="Latest")
        s3 = _make_session("s3", session_start=3000, task_raw="Middle")
        chain = Chain(sessions=[s1, s2, s3])

        synthesizer = MultiSessionSynthesizer(llm=None)
        result = synthesizer.synthesize_timeline("test", [chain])

        # Latest by session_start is s2
        assert result.suggested_fork_session_id == "s2"

    def test_resolution_status_solved(self) -> None:
        s1 = _make_session("s1", session_start=1000, quality_tag=QualityTag.PARTIAL)
        s2 = _make_session(
            "s2", session_start=2000, quality_tag=QualityTag.SOLUTION_FOUND
        )
        chain = Chain(sessions=[s1, s2])

        synthesizer = MultiSessionSynthesizer(llm=None)
        result = synthesizer.synthesize_timeline("test", [chain])
        assert result.resolution_status == "solved"

    def test_resolution_status_ongoing(self) -> None:
        s1 = _make_session("s1", session_start=1000, quality_tag=QualityTag.UNKNOWN)
        s2 = _make_session("s2", session_start=2000, quality_tag=QualityTag.PARTIAL)
        chain = Chain(sessions=[s1, s2])

        synthesizer = MultiSessionSynthesizer(llm=None)
        result = synthesizer.synthesize_timeline("test", [chain])
        assert result.resolution_status == "ongoing"

    def test_resolution_status_dead_end(self) -> None:
        s1 = _make_session("s1", session_start=1000, quality_tag=QualityTag.DEAD_END)
        s2 = _make_session("s2", session_start=2000, quality_tag=QualityTag.DEAD_END)
        chain = Chain(sessions=[s1, s2])

        synthesizer = MultiSessionSynthesizer(llm=None)
        result = synthesizer.synthesize_timeline("test", [chain])
        assert result.resolution_status == "dead_end"

    def test_resolution_status_mixed(self) -> None:
        s1 = _make_session(
            "s1", session_start=1000, quality_tag=QualityTag.SOLUTION_FOUND
        )
        s2 = _make_session("s2", session_start=2000, quality_tag=QualityTag.DEAD_END)
        chain = Chain(sessions=[s1, s2])

        synthesizer = MultiSessionSynthesizer(llm=None)
        result = synthesizer.synthesize_timeline("test", [chain])
        assert result.resolution_status == "mixed"

    def test_llm_returns_invalid_status(self) -> None:
        s1 = _make_session("s1", session_start=1000, quality_tag=QualityTag.SOLUTION_FOUND)
        chain = Chain(sessions=[s1])

        mock_llm = _MockLLM(
            return_value={
                "narrative": "Narrative",
                "resolution_status": "bogus",
                "suggested_fork_session_id": "s1",
            }
        )
        synthesizer = MultiSessionSynthesizer(llm=mock_llm)
        result = synthesizer.synthesize_timeline("test", [chain])

        # Invalid status should be normalised to "unknown" by _dict_to_timeline_summary,
        # then overridden by the deterministic logic because it's not in the allowed set.
        # Deterministic logic for SOLUTION_FOUND -> "solved".
        assert result.resolution_status == "solved"
        assert result.narrative == "Narrative"

    def test_fallback_narrative_includes_multiple_chains(self) -> None:
        s1 = _make_session("s1", session_start=1000, task_raw="Task A")
        s2 = _make_session("s2", session_start=2000, task_raw="Task B")
        chain1 = Chain(sessions=[s1])
        chain2 = Chain(sessions=[s2])

        synthesizer = MultiSessionSynthesizer(llm=None)
        result = synthesizer.synthesize_timeline("query", [chain1, chain2])

        assert "Chain 1:" in result.narrative
        assert "Chain 2:" in result.narrative
        assert "Task A" in result.narrative
        assert "Task B" in result.narrative
