"""Tests for MetadataStore."""

from pathlib import Path

import pytest

from smartfork.indexer.metadata_store import MetadataStore
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
        "propositions": ["JWT token was expired", "Fixed validation logic"],
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
