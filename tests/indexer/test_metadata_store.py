"""Tests for MetadataStore."""

import sqlite3
from pathlib import Path

import pytest

from smartfork.indexer.metadata_store import MetadataStore
from smartfork.models.relationship import SessionRelationship
from smartfork.models.session import QualityTag, SessionDocument


def _make_session(**kwargs) -> SessionDocument:
    """Create a test SessionDocument."""
    defaults = {
        "session_id": "test-sess-1",
        "agent": "kilocode",
        "project_name": "myproject",
        "project_root": "/home/dev",
        "session_start": 1700000000000,
        "session_end": 1700000001000,
        "duration_minutes": 1.0,
        "model_used": "claude-sonnet-4",
        "files_edited": ["src/auth.py"],
        "files_read": ["README.md"],
        "files_mentioned": ["tests/test_auth.py"],
        "domains": ["auth", "backend"],
        "languages": ["python"],
        "layers": ["backend"],
        "session_pattern": "bug_fix",
        "task_raw": "Fix authentication bug",
        "summary_doc": "Fixed the auth bug by updating JWT validation.",
        "reasoning_docs": ["Analyzed auth flow", "Identified JWT bug"],
        "quality_tag": QualityTag.SOLUTION_FOUND,
        "tech_tags": ["JWT", "FastAPI"],
        "indexed_at": 1700000100000,
    }
    defaults.update(kwargs)
    return SessionDocument(**defaults)


class TestMetadataStore:
    @pytest.fixture
    def store(self, tmp_path: Path) -> MetadataStore:
        return MetadataStore(tmp_path / "test_metadata.db")

    def test_upsert_and_get_session(self, store: MetadataStore) -> None:
        session = _make_session()
        store.upsert_session(session)

        result = store.get_session("test-sess-1")
        assert result is not None
        assert result["session_id"] == "test-sess-1"
        assert result["agent"] == "kilocode"
        assert result["project_name"] == "myproject"

    def test_upsert_is_idempotent(self, store: MetadataStore) -> None:
        session = _make_session()
        store.upsert_session(session)

        # Update and re-upsert
        session2 = _make_session(quality_tag=QualityTag.DEAD_END)
        store.upsert_session(session2)

        result = store.get_session("test-sess-1")
        assert result is not None
        assert result["quality_tag"] == "dead_end"

    def test_delete_session(self, store: MetadataStore) -> None:
        session = _make_session()
        store.upsert_session(session)

        assert store.delete_session("test-sess-1") is True
        assert store.get_session("test-sess-1") is None
        assert store.delete_session("nonexistent") is False

    def test_query_by_project(self, store: MetadataStore) -> None:
        store.upsert_session(_make_session(session_id="s1", project_name="proj-a"))
        store.upsert_session(_make_session(session_id="s2", project_name="proj-b"))
        results = store.get_sessions_by_project("proj-a")
        assert len(results) == 1
        assert results[0]["session_id"] == "s1"

    def test_query_by_domain(self, store: MetadataStore) -> None:
        store.upsert_session(_make_session(session_id="s1", domains=["auth"]))
        store.upsert_session(_make_session(session_id="s2", domains=["testing"]))
        results = store.get_sessions_by_domain("auth")
        assert len(results) == 1

    def test_query_by_quality(self, store: MetadataStore) -> None:
        store.upsert_session(_make_session(session_id="s1", quality_tag=QualityTag.SOLUTION_FOUND))
        store.upsert_session(_make_session(session_id="s2", quality_tag=QualityTag.PARTIAL))
        results = store.get_sessions_by_quality("solution_found")
        assert len(results) == 1

    def test_query_by_agent(self, store: MetadataStore) -> None:
        store.upsert_session(_make_session(session_id="s1", agent="kilocode"))
        store.upsert_session(_make_session(session_id="s2", agent="claudecode"))
        results = store.get_sessions_by_agent("kilocode")
        assert len(results) == 1

    def test_supersession_links(self, store: MetadataStore) -> None:
        store.upsert_session(_make_session(session_id="old-sess"))
        store.upsert_session(_make_session(session_id="new-sess"))

        store.add_supersession_link("old-sess", "new-sess", confidence=0.95, reason="same task")
        superseding = store.get_superseding_sessions("old-sess")
        assert len(superseding) == 1
        assert superseding[0]["superseding_id"] == "new-sess"

        superseded = store.get_superseded_sessions("new-sess")
        assert len(superseded) == 1
        assert superseded[0]["superseded_id"] == "old-sess"

    def test_get_stats(self, store: MetadataStore) -> None:
        store.upsert_session(
            _make_session(session_id="s1", project_name="proj-a", agent="kilocode")
        )
        store.upsert_session(
            _make_session(session_id="s2", project_name="proj-b", agent="claudecode")
        )
        stats = store.get_stats()
        assert stats["total_sessions"] == 2
        assert "proj-a" in stats["by_project"]

    def test_get_filtered_ids(self, store: MetadataStore) -> None:
        store.upsert_session(
            _make_session(
                session_id="s1",
                project_name="proj-a",
                quality_tag=QualityTag.SOLUTION_FOUND,
            )
        )
        store.upsert_session(
            _make_session(
                session_id="s2", project_name="proj-b", quality_tag=QualityTag.DEAD_END
            )
        )

        ids = store.get_filtered_ids(project="proj-a")
        assert ids == ["s1"]

        ids = store.get_filtered_ids(quality="solution_found")
        assert ids == ["s1"]

    def test_domain_filter_with_json(self, store: MetadataStore) -> None:
        store.upsert_session(_make_session(session_id="s1", domains=["auth", "backend"]))
        store.upsert_session(_make_session(session_id="s2", domains=["frontend"]))

        ids = store.get_filtered_ids(domain="auth")
        assert "s1" in ids

    def test_get_session_document(self, store: MetadataStore) -> None:
        session = _make_session()
        store.upsert_session(session)

        doc = store.get_session_document("test-sess-1")
        assert doc is not None
        assert doc.session_id == "test-sess-1"
        assert doc.agent == "kilocode"
        assert doc.project_name == "myproject"
        assert doc.files_edited == ["src/auth.py"]
        assert doc.quality_tag == QualityTag.SOLUTION_FOUND

    def test_get_session_document_missing(self, store: MetadataStore) -> None:
        assert store.get_session_document("nonexistent") is None

    def test_reasoning_docs_round_trip(self, store: MetadataStore) -> None:
        session = _make_session(
            session_id="sess-reasoning",
            reasoning_docs=["Step 1: identify bug", "Step 2: fix bug"],
        )
        store.upsert_session(session)

        raw = store.get_session("sess-reasoning")
        assert raw is not None
        assert raw["reasoning_docs"] == '["Step 1: identify bug", "Step 2: fix bug"]'

        doc = store.get_session_document("sess-reasoning")
        assert doc is not None
        assert doc.reasoning_docs == ["Step 1: identify bug", "Step 2: fix bug"]

    def test_get_all_session_documents(self, store: MetadataStore) -> None:
        store.upsert_session(_make_session(session_id="s1", project_name="proj-a"))
        store.upsert_session(_make_session(session_id="s2", project_name="proj-b"))

        docs = store.get_all_session_documents()
        assert len(docs) == 2
        assert {d.session_id for d in docs} == {"s1", "s2"}

    def test_get_all_session_documents_with_filter(self, store: MetadataStore) -> None:
        store.upsert_session(_make_session(session_id="s1", agent="kilocode"))
        store.upsert_session(_make_session(session_id="s2", agent="claudecode"))

        docs = store.get_all_session_documents(agent="kilocode")
        assert len(docs) == 1
        assert docs[0].session_id == "s1"


# Module-level fixture for new test classes
@pytest.fixture
def store(tmp_path: Path) -> MetadataStore:
    return MetadataStore(tmp_path / "test_metadata.db")


def _make_vector(value: float, dim: int = 1024) -> list[float]:
    vec = [0.0] * dim
    vec[0] = value
    return vec


class TestRelationships:
    def test_add_and_get_relationship(self, store: MetadataStore) -> None:
        store.upsert_session(_make_session(session_id="s1"))
        store.upsert_session(_make_session(session_id="s2"))

        rel = SessionRelationship(
            from_session="s1",
            to_session="s2",
            relationship_type="continuation",
            confidence=0.85,
            detected_by="heuristic",
            reasons=["file overlap", "temporal proximity"],
            created_at=1700000000000,
        )
        store.add_relationship(rel)

        results = store.get_relationships("s1", direction="from")
        assert len(results) == 1
        assert results[0].from_session == "s1"
        assert results[0].to_session == "s2"
        assert results[0].relationship_type == "continuation"
        assert results[0].confidence == 0.85
        assert results[0].reasons == ["file overlap", "temporal proximity"]

    def test_get_relationships_by_type(self, store: MetadataStore) -> None:
        store.upsert_session(_make_session(session_id="s1"))
        store.upsert_session(_make_session(session_id="s2"))
        store.upsert_session(_make_session(session_id="s3"))

        store.add_relationship(
            SessionRelationship(
                from_session="s1",
                to_session="s2",
                relationship_type="continuation",
                confidence=0.8,
                detected_by="heuristic",
                reasons=["overlap"],
            )
        )
        store.add_relationship(
            SessionRelationship(
                from_session="s1",
                to_session="s3",
                relationship_type="related",
                confidence=0.6,
                detected_by="heuristic",
                reasons=["similar domain"],
            )
        )

        conts = store.get_relationships_by_type("s1", "continuation", direction="from")
        assert len(conts) == 1
        assert conts[0].to_session == "s2"

        related = store.get_relationships_by_type("s1", "related", direction="from")
        assert len(related) == 1
        assert related[0].to_session == "s3"

    def test_get_relationships_direction(self, store: MetadataStore) -> None:
        store.upsert_session(_make_session(session_id="s1"))
        store.upsert_session(_make_session(session_id="s2"))
        store.upsert_session(_make_session(session_id="s3"))

        store.add_relationship(
            SessionRelationship(
                from_session="s1",
                to_session="s2",
                relationship_type="continuation",
                confidence=0.8,
                detected_by="heuristic",
                reasons=[],
            )
        )
        store.add_relationship(
            SessionRelationship(
                from_session="s3",
                to_session="s1",
                relationship_type="supersession",
                confidence=0.9,
                detected_by="heuristic",
                reasons=[],
            )
        )

        from_rels = store.get_relationships("s1", direction="from")
        assert len(from_rels) == 1
        assert from_rels[0].to_session == "s2"

        to_rels = store.get_relationships("s1", direction="to")
        assert len(to_rels) == 1
        assert to_rels[0].from_session == "s3"

        both_rels = store.get_relationships("s1", direction="both")
        assert len(both_rels) == 2

    def test_delete_relationships_for_session(self, store: MetadataStore) -> None:
        store.upsert_session(_make_session(session_id="s1"))
        store.upsert_session(_make_session(session_id="s2"))
        store.upsert_session(_make_session(session_id="s3"))

        store.add_relationship(
            SessionRelationship(
                from_session="s1",
                to_session="s2",
                relationship_type="continuation",
                confidence=0.8,
                detected_by="heuristic",
                reasons=[],
            )
        )
        store.add_relationship(
            SessionRelationship(
                from_session="s3",
                to_session="s1",
                relationship_type="related",
                confidence=0.5,
                detected_by="heuristic",
                reasons=[],
            )
        )

        count = store.delete_relationships_for_session("s1")
        assert count == 2

        assert store.get_relationships("s1", direction="both") == []

    def test_relationships_are_sessions(self, store: MetadataStore) -> None:
        rel = SessionRelationship(
            from_session="nonexistent",
            to_session="also-nonexistent",
            relationship_type="related",
            confidence=0.5,
            detected_by="heuristic",
            reasons=["test"],
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.add_relationship(rel)


class TestFTS5Search:
    def test_fts5_search_basic(self, store: MetadataStore) -> None:
        store.upsert_session(_make_session(session_id="s1", task_raw="hello world test"))
        store.upsert_session(_make_session(session_id="s2", task_raw="something else entirely"))

        results = store.fts5_search("hello")
        assert len(results) == 1
        assert results[0][0] == "s1"

    def test_fts5_search_relevance(self, store: MetadataStore) -> None:
        store.upsert_session(
            _make_session(session_id="s1", task_raw="hello world test foo bar baz")
        )
        store.upsert_session(_make_session(session_id="s2", task_raw="hello world"))
        store.upsert_session(
            _make_session(session_id="s3", task_raw="completely unrelated")
        )

        results = store.fts5_search("hello world")
        assert len(results) == 2
        ids = {r[0] for r in results}
        assert ids == {"s1", "s2"}

    def test_fts5_search_empty_db(self, store: MetadataStore) -> None:
        results = store.fts5_search("test")
        assert results == []

    def test_fts5_syncs_on_update(self, store: MetadataStore) -> None:
        store.upsert_session(_make_session(session_id="s1", task_raw="old text here"))

        results = store.fts5_search("old")
        assert len(results) == 1
        assert results[0][0] == "s1"

        store.upsert_session(_make_session(session_id="s1", task_raw="new text here"))

        results = store.fts5_search("new")
        assert len(results) == 1
        assert results[0][0] == "s1"

        results = store.fts5_search("old")
        assert results == []


SQLITE_VEC_AVAILABLE = False


def _sqlite_vec_available() -> bool:
    try:
        import sqlite_vec  # type: ignore[import-untyped]
        conn = sqlite3.connect(":memory:")
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.execute(
            "CREATE VIRTUAL TABLE test USING vec0(id text primary key, v float[1])"
        )
        conn.close()
        return True
    except Exception:
        return False


SQLITE_VEC_AVAILABLE = _sqlite_vec_available()


class TestVectorStore:
    @pytest.mark.skipif(
        not SQLITE_VEC_AVAILABLE,
        reason="sqlite-vec extension not available",
    )
    def test_store_and_get_vector(self, store: MetadataStore) -> None:
        vec = _make_vector(1.0)
        store.store_vector("s1", vec)
        result = store.get_vector("s1")
        assert result is not None
        assert len(result) == 1024
        assert result[0] == 1.0
        assert result[1] == 0.0

    @pytest.mark.skipif(
        not SQLITE_VEC_AVAILABLE,
        reason="sqlite-vec extension not available",
    )
    def test_get_vector_nonexistent(self, store: MetadataStore) -> None:
        assert store.get_vector("nonexistent") is None

    @pytest.mark.skipif(
        not SQLITE_VEC_AVAILABLE,
        reason="sqlite-vec extension not available",
    )
    def test_vector_search(self, store: MetadataStore) -> None:
        store.store_vector("s1", _make_vector(1.0))
        store.store_vector("s2", _make_vector(0.9))
        store.store_vector("s3", _make_vector(0.1))

        results = store.vector_search(_make_vector(1.0), limit=2)
        assert len(results) == 2
        ids = [r[0] for r in results]
        assert "s1" in ids
        assert "s2" in ids
        # s1 should be more similar than s2
        s1_score = next(r[1] for r in results if r[0] == "s1")
        s2_score = next(r[1] for r in results if r[0] == "s2")
        assert s1_score >= s2_score

    @pytest.mark.skipif(
        not SQLITE_VEC_AVAILABLE,
        reason="sqlite-vec extension not available",
    )
    def test_delete_vector(self, store: MetadataStore) -> None:
        store.store_vector("s1", _make_vector(1.0))
        assert store.get_vector("s1") is not None

        store.delete_vector("s1")
        assert store.get_vector("s1") is None
