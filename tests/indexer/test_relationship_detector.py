"""Tests for RelationshipDetector."""

from typing import Any

import pytest

from smartfork.indexer.relationship_detector import RelationshipDetector
from smartfork.models.session import QualityTag, SessionDocument


def _make_session(**kwargs: Any) -> SessionDocument:
    defaults = {
        "session_id": "s1",
        "agent": "kilocode",
        "project_name": "proj",
        "project_root": "/tmp/proj",
        "session_start": 1_700_000_000_000,
        "session_end": 1_700_000_001_000,
        "task_raw": "Fix auth bug",
        "files_edited": ["src/auth.py"],
        "domains": ["backend", "auth"],
        "quality_tag": QualityTag.UNKNOWN,
    }
    defaults.update(kwargs)
    return SessionDocument(**defaults)


class TestExplicitDetection:
    def test_detect_explicit_from_parent_id(self) -> None:
        detector = RelationshipDetector()
        child = _make_session(session_id="child-1", parent_id="parent-1")
        results = detector._detect_explicit([child])
        assert len(results) == 1
        rel = results[0]
        assert rel.from_session == "parent-1"
        assert rel.to_session == "child-1"
        assert rel.relationship_type == "continuation"
        assert rel.confidence == 1.0
        assert rel.detected_by == "explicit"
        assert rel.reasons == ["explicit_parent_link"]
        assert rel.created_at > 0

    def test_detect_explicit_no_parent_id(self) -> None:
        detector = RelationshipDetector()
        orphan = _make_session(session_id="orphan-1", parent_id=None)
        results = detector._detect_explicit([orphan])
        assert results == []


class TestHeuristicDetection:
    def test_detect_heuristic_temporal_proximity(self) -> None:
        detector = RelationshipDetector()
        older = _make_session(session_id="s1", session_start=1_700_000_000_000)
        # 12 hours later
        newer = _make_session(
            session_id="s2",
            session_start=1_700_000_000_000 + 12 * 3600 * 1000,
        )
        results = detector._detect_heuristic([older, newer])
        assert len(results) >= 1
        rel = results[0]
        assert "temporal_proximity" in rel.reasons
        assert rel.confidence >= 0.40

    def test_detect_heuristic_file_overlap(self) -> None:
        detector = RelationshipDetector()
        older = _make_session(
            session_id="s1",
            session_start=1_700_000_000_000,
            files_edited=["a.py", "b.py"],
        )
        # 48 hours later to avoid temporal boost
        newer = _make_session(
            session_id="s2",
            session_start=1_700_000_000_000 + 48 * 3600 * 1000,
            files_edited=["a.py", "c.py"],
        )
        results = detector._detect_heuristic([older, newer])
        assert len(results) >= 1
        rel = results[0]
        assert "file_overlap" in rel.reasons
        assert rel.confidence >= 0.40

    def test_detect_heuristic_hard_filter_30_days(self) -> None:
        detector = RelationshipDetector()
        older = _make_session(session_id="s1", session_start=1_700_000_000_000)
        newer = _make_session(
            session_id="s2",
            session_start=1_700_000_000_000 + 31 * 24 * 3600 * 1000,
        )
        results = detector._detect_heuristic([older, newer])
        assert results == []

    def test_detect_heuristic_hard_filter_cross_project(self) -> None:
        detector = RelationshipDetector()
        older = _make_session(
            session_id="s1", session_start=1_700_000_000_000, project_name="proj-a"
        )
        newer = _make_session(
            session_id="s2",
            session_start=1_700_000_000_000 + 12 * 3600 * 1000,
            project_name="proj-b",
        )
        results = detector._detect_heuristic([older, newer])
        assert results == []

    def test_detect_heuristic_hard_filter_no_domain_overlap(self) -> None:
        detector = RelationshipDetector()
        older = _make_session(
            session_id="s1",
            session_start=1_700_000_000_000,
            domains=["auth"],
        )
        newer = _make_session(
            session_id="s2",
            session_start=1_700_000_000_000 + 12 * 3600 * 1000,
            domains=["frontend"],
        )
        results = detector._detect_heuristic([older, newer])
        assert results == []

    def test_forward_only_optimization(self) -> None:
        detector = RelationshipDetector()
        s1 = _make_session(session_id="s1", session_start=1_700_000_000_000)
        s2 = _make_session(
            session_id="s2", session_start=1_700_000_000_000 + 10 * 3600 * 1000
        )
        s3 = _make_session(
            session_id="s3", session_start=1_700_000_000_000 + 20 * 3600 * 1000
        )
        results = detector._detect_heuristic([s1, s2, s3])
        # All forward pairs should be present (s1->s2, s1->s3, s2->s3)
        pairs = {(rel.from_session, rel.to_session) for rel in results}
        assert ("s1", "s2") in pairs
        assert ("s1", "s3") in pairs
        assert ("s2", "s3") in pairs
        # No reverse pairs
        assert ("s2", "s1") not in pairs
        assert ("s3", "s1") not in pairs
        assert ("s3", "s2") not in pairs


class TestClassification:
    def test_classify_supersession(self) -> None:
        detector = RelationshipDetector()
        older = _make_session(
            session_id="s1",
            quality_tag=QualityTag.SOLUTION_FOUND,
            task_raw="fix the auth bug",
        )
        newer = _make_session(session_id="s2", task_raw="fix auth bug again")
        result = detector._classify_relationship(older, newer, score=0.9)
        assert result == "supersession"

    def test_classify_continuation(self) -> None:
        detector = RelationshipDetector()
        older = _make_session(
            session_id="s1",
            task_raw="fix the auth bug",
            files_edited=["src/auth.py"],
        )
        newer = _make_session(
            session_id="s2",
            task_raw="fix auth bug again",
            files_edited=["src/auth.py"],
        )
        result = detector._classify_relationship(older, newer, score=0.9)
        assert result == "continuation"

    def test_classify_branch(self) -> None:
        detector = RelationshipDetector()
        older = _make_session(
            session_id="s1",
            task_raw="implement login page",
            project_name="proj",
        )
        newer = _make_session(
            session_id="s2",
            task_raw="refactor database layer",
            project_name="proj",
        )
        result = detector._classify_relationship(older, newer, score=0.9)
        assert result == "branch"

    def test_classify_related(self) -> None:
        detector = RelationshipDetector()
        older = _make_session(
            session_id="s1", task_raw="task a", project_name="proj-a"
        )
        newer = _make_session(
            session_id="s2", task_raw="task b", project_name="proj-b"
        )
        result = detector._classify_relationship(older, newer, score=0.4)
        assert result == "related"


class TestHelpers:
    def test_cosine_similarity_identical(self) -> None:
        v = [1.0, 2.0, 3.0]
        assert RelationshipDetector._cosine_similarity(v, v) == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self) -> None:
        assert RelationshipDetector._cosine_similarity(
            [1.0, 0.0], [0.0, 1.0]
        ) == pytest.approx(0.0)

    def test_cosine_similarity_empty(self) -> None:
        assert RelationshipDetector._cosine_similarity([], []) == 0.0

    def test_cosine_similarity_different_lengths(self) -> None:
        assert RelationshipDetector._cosine_similarity([1.0, 2.0], [1.0]) == 0.0

    def test_significant_task_overlap_true(self) -> None:
        detector = RelationshipDetector()
        assert detector._significant_task_overlap(
            "fix the authentication bug", "fix authentication bug again"
        )

    def test_significant_task_overlap_false(self) -> None:
        detector = RelationshipDetector()
        assert not detector._significant_task_overlap(
            "implement login page", "refactor database layer"
        )

    def test_is_resolved_true(self) -> None:
        detector = RelationshipDetector()
        session = _make_session(quality_tag=QualityTag.SOLUTION_FOUND)
        assert detector._is_resolved(session) is True

    def test_is_resolved_false(self) -> None:
        detector = RelationshipDetector()
        session = _make_session(quality_tag=QualityTag.UNKNOWN)
        assert detector._is_resolved(session) is False


class TestDetectAll:
    def test_detect_all_combines_tiers(self) -> None:
        detector = RelationshipDetector()
        s1 = _make_session(
            session_id="s1",
            session_start=1_700_000_000_000,
            parent_id="parent-0",
        )
        s2 = _make_session(
            session_id="s2",
            session_start=1_700_000_000_000 + 12 * 3600 * 1000,
        )
        results = detector.detect_all([s1, s2])
        explicit = [r for r in results if r.detected_by == "explicit"]
        heuristic = [r for r in results if r.detected_by == "heuristic"]
        assert len(explicit) == 1
        assert len(heuristic) == 1
        assert explicit[0].from_session == "parent-0"
        assert heuristic[0].from_session == "s1"
        assert heuristic[0].to_session == "s2"
