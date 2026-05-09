"""Tests for supersession detection."""

import pytest

from smartfork.indexer.supersession import (
    SupersessionAnnotator,
    SupersessionDetector,
    _cosine_similarity,
    _has_negation,
)
from smartfork.models.session import QualityTag, SessionDocument


def _make_session(**kwargs) -> SessionDocument:
    defaults = {
        "session_id": "s1",
        "agent": "kilocode",
        "project_name": "myproject",
        "project_root": "/tmp",
        "session_start": 1000000,
        "session_end": 2000000,
        "task_raw": "Fix authentication bug",
        "summary_doc": "",
        "domains": ["auth"],
        "quality_tag": QualityTag.UNKNOWN,
    }
    defaults.update(kwargs)
    return SessionDocument(**defaults)


class TestHelpers:
    def test_cosine_similarity_identical(self) -> None:
        v = [1.0, 2.0, 3.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self) -> None:
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_cosine_similarity_empty(self) -> None:
        assert _cosine_similarity([], []) == 0.0

    def test_has_negation_true(self) -> None:
        assert _has_negation("The bug is not fixed yet", 15) is True

    def test_has_negation_false(self) -> None:
        assert _has_negation("The bug is fixed now", 12) is False


class TestSupersessionDetector:
    def test_self_supersession_returns_zero(self) -> None:
        detector = SupersessionDetector()
        session = _make_session(session_id="s1")
        score = detector.detect_supersession(session, session)
        assert score == 0.0

    def test_different_projects_returns_zero(self) -> None:
        detector = SupersessionDetector()
        older = _make_session(session_id="old", project_name="proj-a", session_start=1000)
        newer = _make_session(session_id="new", project_name="proj-b", session_start=2000)
        score = detector.detect_supersession(older, newer)
        assert score == 0.0

    def test_older_is_newer_returns_zero(self) -> None:
        detector = SupersessionDetector()
        older = _make_session(session_id="old", session_start=2000)
        newer = _make_session(session_id="new", session_start=1000)
        score = detector.detect_supersession(older, newer)
        assert score == 0.0

    def test_no_domain_overlap_returns_zero(self) -> None:
        detector = SupersessionDetector()
        older = _make_session(session_id="old", session_start=1000, domains=["auth"])
        newer = _make_session(session_id="new", session_start=2000, domains=["frontend"])
        score = detector.detect_supersession(older, newer)
        assert score == 0.0

    def test_valid_supersession_positive_score(self) -> None:
        detector = SupersessionDetector()
        older = _make_session(
            session_id="old",
            session_start=1000,
            domains=["auth"],
            task_raw="Fix authentication bug in login",
            summary_doc="Need to fix JWT validation",
        )
        newer = _make_session(
            session_id="new",
            session_start=2000,
            domains=["auth"],
            task_raw="Fixed the auth bug completely",
            summary_doc="Applied fix and deployed",
        )
        score = detector.detect_supersession(older, newer)
        assert score > 0.0

    def test_find_supersessions(self) -> None:
        detector = SupersessionDetector()
        sessions = [
            _make_session(
                session_id="s1", session_start=1000, domains=["auth"],
                task_raw="Fix authentication bug in the login module",
            ),
            _make_session(
                session_id="s2", session_start=2000, domains=["auth"],
                task_raw="Fixed the auth issue completely",
            ),
        ]
        vectors = {"s1": [1.0, 0.0], "s2": [1.0, 0.0]}
        results = detector.find_supersessions(sessions, vectors=vectors)
        assert len(results) >= 1
        superseded, superseding, confidence = results[0]
        assert superseded == "s1"
        assert superseding == "s2"


class TestSupersessionAnnotator:
    def test_annotate_superseded(self) -> None:
        s_map = {"s1": ("s2", 0.9)}
        result = SupersessionAnnotator.annotate("s1", s_map)
        assert result["status"] == "superseded"
        assert result["superseded_by"] == "s2"

    def test_annotate_superseding(self) -> None:
        s_map = {"s1": ("s2", 0.9)}
        result = SupersessionAnnotator.annotate("s2", s_map)
        assert result["status"] == "superseding"
        assert result["boost"] == 0.15

    def test_annotate_none(self) -> None:
        result = SupersessionAnnotator.annotate("s3", {})
        assert result["status"] == "none"
