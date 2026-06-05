"""Tests for SessionGraphEngine."""

from unittest.mock import MagicMock

import pytest

from smartfork.models.relationship import Chain, SessionRelationship, TimelineEntry
from smartfork.models.session import QualityTag, SessionDocument
from smartfork.search.session_graph_engine import SessionGraphEngine


def _make_session(
    session_id: str,
    session_start: int = 0,
    task_raw: str = "",
    summary_doc: str = "",
    quality_tag: QualityTag = QualityTag.UNKNOWN,
    project_name: str = "proj",
) -> SessionDocument:
    return SessionDocument(
        session_id=session_id,
        agent="test",
        project_name=project_name,
        project_root="/tmp",
        session_start=session_start,
        task_raw=task_raw,
        summary_doc=summary_doc,
        quality_tag=quality_tag,
    )


class TestFindChainForward:
    def test_follows_continuation_links(self) -> None:
        store = MagicMock()
        s1 = _make_session("s1", session_start=1000, task_raw="task1")
        s2 = _make_session("s2", session_start=2000, task_raw="task2")
        s3 = _make_session("s3", session_start=3000, task_raw="task3")

        def get_session_document(sid: str) -> SessionDocument | None:
            mapping = {"s1": s1, "s2": s2, "s3": s3}
            return mapping.get(sid)

        store.get_session_document.side_effect = get_session_document
        store.get_relationships.side_effect = lambda sid, direction: {
            ("s1", "from"): [
                SessionRelationship(
                    from_session="s1",
                    to_session="s2",
                    relationship_type="continuation",
                    confidence=0.9,
                    detected_by="explicit",
                )
            ],
            ("s2", "from"): [
                SessionRelationship(
                    from_session="s2",
                    to_session="s3",
                    relationship_type="continuation",
                    confidence=0.9,
                    detected_by="explicit",
                )
            ],
            ("s3", "from"): [],
        }.get((sid, direction), [])

        engine = SessionGraphEngine(store)
        chain = engine.find_chain("s1", direction="forward")

        assert len(chain) == 3
        assert chain[0].session_id == "s1"
        assert chain[1].session_id == "s2"
        assert chain[2].session_id == "s3"


class TestFindChainBackward:
    def test_follows_backward_to_find_chain_start(self) -> None:
        store = MagicMock()
        s1 = _make_session("s1", session_start=1000, task_raw="task1")
        s2 = _make_session("s2", session_start=2000, task_raw="task2")
        s3 = _make_session("s3", session_start=3000, task_raw="task3")

        def get_session_document(sid: str) -> SessionDocument | None:
            mapping = {"s1": s1, "s2": s2, "s3": s3}
            return mapping.get(sid)

        store.get_session_document.side_effect = get_session_document
        store.get_relationships.side_effect = lambda sid, direction: {
            ("s3", "to"): [
                SessionRelationship(
                    from_session="s2",
                    to_session="s3",
                    relationship_type="continuation",
                    confidence=0.9,
                    detected_by="explicit",
                )
            ],
            ("s2", "to"): [
                SessionRelationship(
                    from_session="s1",
                    to_session="s2",
                    relationship_type="continuation",
                    confidence=0.9,
                    detected_by="explicit",
                )
            ],
            ("s1", "to"): [],
        }.get((sid, direction), [])

        engine = SessionGraphEngine(store)
        chain = engine.find_chain("s3", direction="backward")

        assert len(chain) == 3
        assert chain[0].session_id == "s1"
        assert chain[1].session_id == "s2"
        assert chain[2].session_id == "s3"


class TestFindChainSingleSession:
    def test_no_relationships_returns_just_itself(self) -> None:
        store = MagicMock()
        s1 = _make_session("s1", session_start=1000)
        store.get_session_document.return_value = s1
        store.get_relationships.return_value = []

        engine = SessionGraphEngine(store)
        chain = engine.find_chain("s1", direction="forward")

        assert len(chain) == 1
        assert chain[0].session_id == "s1"


class TestGetLatestInChain:
    def test_returns_most_recent(self) -> None:
        store = MagicMock()
        s1 = _make_session("s1", session_start=1000)
        s2 = _make_session("s2", session_start=5000)
        s3 = _make_session("s3", session_start=3000)

        chain = Chain(sessions=[s1, s2, s3])
        engine = SessionGraphEngine(store)
        latest = engine.get_latest_in_chain(chain)

        assert latest.session_id == "s2"


class TestFindBranches:
    def test_finds_divergent_paths(self) -> None:
        store = MagicMock()
        s1 = _make_session("s1", session_start=1000)
        s2 = _make_session("s2", session_start=2000)
        s3 = _make_session("s3", session_start=3000)
        s4 = _make_session("s4", session_start=4000)
        s5 = _make_session("s5", session_start=5000)

        def get_session_document(sid: str) -> SessionDocument | None:
            mapping = {"s1": s1, "s2": s2, "s3": s3, "s4": s4, "s5": s5}
            return mapping.get(sid)

        store.get_session_document.side_effect = get_session_document
        # s1 -> s2 (continuation), s1 -> s3 (branch)
        # s2 -> s4 (continuation)
        # s3 -> s5 (continuation)
        store.get_relationships.side_effect = lambda sid, direction: {
            ("s1", "from"): [
                SessionRelationship(
                    from_session="s1",
                    to_session="s2",
                    relationship_type="continuation",
                    confidence=0.9,
                    detected_by="explicit",
                ),
                SessionRelationship(
                    from_session="s1",
                    to_session="s3",
                    relationship_type="branch",
                    confidence=0.8,
                    detected_by="heuristic",
                ),
            ],
            ("s2", "from"): [
                SessionRelationship(
                    from_session="s2",
                    to_session="s4",
                    relationship_type="continuation",
                    confidence=0.9,
                    detected_by="explicit",
                )
            ],
            ("s3", "from"): [
                SessionRelationship(
                    from_session="s3",
                    to_session="s5",
                    relationship_type="continuation",
                    confidence=0.9,
                    detected_by="explicit",
                )
            ],
            ("s4", "from"): [],
            ("s5", "from"): [],
        }.get((sid, direction), [])

        engine = SessionGraphEngine(store)
        branches = engine.find_branches("s1")

        assert len(branches) == 2
        # Branch via s2 -> s4
        assert any(len(b) == 2 and b[0].session_id == "s2" and b[1].session_id == "s4" for b in branches)
        # Branch via s3 -> s5
        assert any(len(b) == 2 and b[0].session_id == "s3" and b[1].session_id == "s5" for b in branches)

    def test_no_branches_returns_empty(self) -> None:
        store = MagicMock()
        s1 = _make_session("s1", session_start=1000)
        store.get_session_document.return_value = s1
        store.get_relationships.return_value = []

        engine = SessionGraphEngine(store)
        branches = engine.find_branches("s1")

        assert branches == []


class TestBuildTimeline:
    def test_produces_correct_timeline_entries(self) -> None:
        store = MagicMock()
        s1 = _make_session(
            "s1",
            session_start=1000,
            task_raw="Implement auth module",
            summary_doc="Added JWT auth",
            quality_tag=QualityTag.SOLUTION_FOUND,
        )
        s2 = _make_session(
            "s2",
            session_start=2000,
            task_raw="Fix auth bug",
            summary_doc="Fixed token expiry",
            quality_tag=QualityTag.PARTIAL,
        )

        chain = Chain(sessions=[s1, s2])
        engine = SessionGraphEngine(store)
        timeline = engine.build_timeline(chain)

        assert len(timeline) == 2
        assert isinstance(timeline[0], TimelineEntry)
        assert timeline[0].session_id == "s1"
        assert timeline[0].timestamp == 1000
        assert timeline[0].task == "Implement auth module"
        assert timeline[0].quality_tag == QualityTag.SOLUTION_FOUND
        assert timeline[0].summary == "Added JWT auth"

        assert timeline[1].session_id == "s2"
        assert timeline[1].timestamp == 2000
        assert timeline[1].task == "Fix auth bug"

    def test_relationship_labels(self) -> None:
        store = MagicMock()
        s1 = _make_session("s1", session_start=1000)
        s2 = _make_session("s2", session_start=2000)
        s3 = _make_session("s3", session_start=3000)

        chain = Chain(sessions=[s1, s2, s3])
        engine = SessionGraphEngine(store)
        timeline = engine.build_timeline(chain)

        assert timeline[0].relationship_to_next == "continued_in"
        assert timeline[1].relationship_to_next == "continued_in"
        assert timeline[2].relationship_to_next is None

    def test_truncates_long_fields(self) -> None:
        store = MagicMock()
        long_task = "x" * 100
        long_summary = "y" * 250
        s1 = _make_session(
            "s1",
            session_start=1000,
            task_raw=long_task,
            summary_doc=long_summary,
        )

        chain = Chain(sessions=[s1])
        engine = SessionGraphEngine(store)
        timeline = engine.build_timeline(chain)

        assert len(timeline[0].task) == 80
        assert timeline[0].task.endswith("...")
        assert len(timeline[0].summary) == 200
        assert timeline[0].summary.endswith("...")


class TestChainCache:
    def test_repeated_calls_use_cache(self) -> None:
        store = MagicMock()
        s1 = _make_session("s1", session_start=1000)
        s2 = _make_session("s2", session_start=2000)

        def get_session_document(sid: str) -> SessionDocument | None:
            mapping = {"s1": s1, "s2": s2}
            return mapping.get(sid)

        store.get_session_document.side_effect = get_session_document
        store.get_relationships.side_effect = lambda sid, direction: {
            ("s1", "from"): [
                SessionRelationship(
                    from_session="s1",
                    to_session="s2",
                    relationship_type="continuation",
                    confidence=0.9,
                    detected_by="explicit",
                )
            ],
            ("s2", "from"): [],
        }.get((sid, direction), [])

        engine = SessionGraphEngine(store)
        chain1 = engine.find_chain("s1", direction="forward")
        chain2 = engine.find_chain("s1", direction="forward")

        assert chain1 == chain2
        # get_session_document should only be called twice (s1 and s2 on first call)
        assert store.get_session_document.call_count == 2


class TestFindRelatedSessions:
    def test_groups_related_into_chains(self) -> None:
        store = MagicMock()
        s1 = _make_session("s1", session_start=1000)
        s2 = _make_session("s2", session_start=2000)
        s3 = _make_session("s3", session_start=3000)

        def get_session_document(sid: str) -> SessionDocument | None:
            mapping = {"s1": s1, "s2": s2, "s3": s3}
            return mapping.get(sid)

        store.get_session_document.side_effect = get_session_document
        # s1 -> s2 (continuation), s1 -> s3 (related)
        store.get_relationships.side_effect = lambda sid, direction: {
            ("s1", "both"): [
                SessionRelationship(
                    from_session="s1",
                    to_session="s2",
                    relationship_type="continuation",
                    confidence=0.9,
                    detected_by="explicit",
                ),
                SessionRelationship(
                    from_session="s1",
                    to_session="s3",
                    relationship_type="related",
                    confidence=0.7,
                    detected_by="heuristic",
                ),
            ],
            ("s2", "to"): [
                SessionRelationship(
                    from_session="s1",
                    to_session="s2",
                    relationship_type="continuation",
                    confidence=0.9,
                    detected_by="explicit",
                )
            ],
            ("s3", "to"): [],
            ("s1", "from"): [
                SessionRelationship(
                    from_session="s1",
                    to_session="s2",
                    relationship_type="continuation",
                    confidence=0.9,
                    detected_by="explicit",
                )
            ],
            ("s2", "from"): [],
            ("s3", "from"): [],
        }.get((sid, direction), [])

        engine = SessionGraphEngine(store)
        chains = engine.find_related_sessions("s1", max_chains=5)

        assert len(chains) == 2
        # Chain via s2 should include s1 and s2
        chain_ids = [c.head_session_id for c in chains]
        assert "s1" in chain_ids
        assert "s3" in chain_ids

    def test_respects_project_filter(self) -> None:
        store = MagicMock()
        s1 = _make_session("s1", session_start=1000, project_name="proj-a")
        s2 = _make_session("s2", session_start=2000, project_name="proj-b")

        def get_session_document(sid: str) -> SessionDocument | None:
            mapping = {"s1": s1, "s2": s2}
            return mapping.get(sid)

        store.get_session_document.side_effect = get_session_document
        store.get_relationships.side_effect = lambda sid, direction: {
            ("s1", "both"): [
                SessionRelationship(
                    from_session="s1",
                    to_session="s2",
                    relationship_type="related",
                    confidence=0.7,
                    detected_by="heuristic",
                )
            ],
            ("s2", "to"): [],
            ("s2", "from"): [],
            ("s1", "from"): [],
        }.get((sid, direction), [])

        engine = SessionGraphEngine(store)
        chains = engine.find_related_sessions("s1", project="proj-b", max_chains=5)

        assert len(chains) == 1
        assert chains[0].head_session_id == "s2"
