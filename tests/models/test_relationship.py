"""Tests for relationship models."""

import pytest

from smartfork.models.relationship import (
    Chain,
    SessionRelationship,
    TimelineEntry,
    TimelineSummary,
)
from smartfork.models.session import QualityTag, SessionDocument


class TestSessionRelationship:
    def test_basic_creation(self) -> None:
        rel = SessionRelationship(
            from_session="sess_A",
            to_session="sess_B",
            relationship_type="supersession",
            confidence=0.92,
            detected_by="heuristic",
            reasons=["file_overlap", "temporal_proximity"],
            created_at=1_716_480_000_000,
        )
        assert rel.from_session == "sess_A"
        assert rel.to_session == "sess_B"
        assert rel.relationship_type == "supersession"
        assert rel.confidence == 0.92
        assert rel.detected_by == "heuristic"
        assert rel.reasons == ["file_overlap", "temporal_proximity"]
        assert rel.created_at == 1_716_480_000_000

    def test_invalid_relationship_type(self) -> None:
        with pytest.raises(ValueError, match="relationship_type must be one of"):
            SessionRelationship(
                from_session="sess_A",
                to_session="sess_B",
                relationship_type="invalid_type",
                confidence=0.5,
                detected_by="heuristic",
                reasons=[],
            )

    def test_confidence_range_low(self) -> None:
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            SessionRelationship(
                from_session="sess_A",
                to_session="sess_B",
                relationship_type="continuation",
                confidence=-0.1,
                detected_by="explicit",
                reasons=[],
            )

    def test_confidence_range_high(self) -> None:
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            SessionRelationship(
                from_session="sess_A",
                to_session="sess_B",
                relationship_type="continuation",
                confidence=1.5,
                detected_by="explicit",
                reasons=[],
            )

    def test_detected_by_validation(self) -> None:
        with pytest.raises(ValueError, match="detected_by must be one of"):
            SessionRelationship(
                from_session="sess_A",
                to_session="sess_B",
                relationship_type="continuation",
                confidence=0.5,
                detected_by="magic",
                reasons=[],
            )

    def test_no_self_relationships(self) -> None:
        with pytest.raises(ValueError, match="from_session must not equal to_session"):
            SessionRelationship(
                from_session="sess_A",
                to_session="sess_A",
                relationship_type="continuation",
                confidence=1.0,
                detected_by="explicit",
                reasons=[],
            )


class TestChain:
    def test_basic_creation(self) -> None:
        doc1 = SessionDocument(
            session_id="s1", agent="test", project_name="p1", project_root="/tmp"
        )
        doc2 = SessionDocument(
            session_id="s2", agent="test", project_name="p1", project_root="/tmp"
        )
        chain = Chain(
            sessions=[doc1, doc2],
            chain_type="linear",
        )
        assert chain.sessions == [doc1, doc2]
        assert chain.chain_type == "linear"
        assert chain.head_session_id == "s1"
        assert chain.tail_session_id == "s2"

    def test_chain_type_validation(self) -> None:
        doc = SessionDocument(
            session_id="s1", agent="test", project_name="p1", project_root="/tmp"
        )
        with pytest.raises(ValueError, match="chain_type must be one of"):
            Chain(sessions=[doc], chain_type="invalid")

    def test_sessions_must_have_at_least_one(self) -> None:
        with pytest.raises(ValueError, match="sessions must have at least 1 element"):
            Chain(sessions=[], chain_type="linear")

    def test_head_tail_point_to_correct_sessions(self) -> None:
        doc1 = SessionDocument(
            session_id="s1", agent="test", project_name="p1", project_root="/tmp"
        )
        doc2 = SessionDocument(
            session_id="s2", agent="test", project_name="p1", project_root="/tmp"
        )
        doc3 = SessionDocument(
            session_id="s3", agent="test", project_name="p1", project_root="/tmp"
        )
        chain = Chain(
            sessions=[doc1, doc2, doc3],
            chain_type="linear",
            head_session_id="s1",
            tail_session_id="s3",
        )
        assert chain.head_session_id == "s1"
        assert chain.tail_session_id == "s3"

    def test_head_mismatch_raises(self) -> None:
        doc = SessionDocument(
            session_id="s1", agent="test", project_name="p1", project_root="/tmp"
        )
        with pytest.raises(ValueError, match="head_session_id must match first session"):
            Chain(sessions=[doc], chain_type="linear", head_session_id="wrong")

    def test_tail_mismatch_raises(self) -> None:
        doc = SessionDocument(
            session_id="s1", agent="test", project_name="p1", project_root="/tmp"
        )
        with pytest.raises(ValueError, match="tail_session_id must match last session"):
            Chain(sessions=[doc], chain_type="linear", tail_session_id="wrong")


class TestTimelineEntry:
    def test_basic_creation(self) -> None:
        entry = TimelineEntry(
            session_id="s1",
            timestamp=1_700_000_000_000,
            task="Fix auth bug",
            quality_tag=QualityTag.SOLUTION_FOUND,
            summary="Resolved the authentication issue.",
            relationship_to_next="superseded_by",
        )
        assert entry.session_id == "s1"
        assert entry.timestamp == 1_700_000_000_000
        assert entry.task == "Fix auth bug"
        assert entry.quality_tag == QualityTag.SOLUTION_FOUND
        assert entry.summary == "Resolved the authentication issue."
        assert entry.relationship_to_next == "superseded_by"

    def test_relationship_to_next_can_be_none(self) -> None:
        entry = TimelineEntry(
            session_id="s1",
            timestamp=1_700_000_000_000,
            task="Fix auth bug",
        )
        assert entry.relationship_to_next is None


class TestTimelineSummary:
    def test_basic_creation(self) -> None:
        entry = TimelineEntry(
            session_id="s1",
            timestamp=1_700_000_000_000,
            task="Fix auth bug",
        )
        summary = TimelineSummary(
            narrative="A story of debugging.",
            timeline=[entry],
            suggested_fork_session_id="s1",
            resolution_status="solved",
        )
        assert summary.narrative == "A story of debugging."
        assert summary.timeline == [entry]
        assert summary.suggested_fork_session_id == "s1"
        assert summary.resolution_status == "solved"

    def test_default_resolution_status(self) -> None:
        summary = TimelineSummary(narrative="empty")
        assert summary.resolution_status == "unknown"

    def test_resolution_status_validation(self) -> None:
        with pytest.raises(ValueError, match="resolution_status must be one of"):
            TimelineSummary(resolution_status="invalid_status")
