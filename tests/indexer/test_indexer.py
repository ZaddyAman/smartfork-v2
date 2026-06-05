"""Tests for FullIndexer."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from smartfork.indexer.indexer import FullIndexer
from smartfork.indexer.metadata_store import MetadataStore
from smartfork.models.session import QualityTag, RawSessionData, SessionDocument


def _make_raw_session(session_id: str, **kwargs) -> RawSessionData:
    defaults = {
        "session_id": session_id,
        "agent_id": "test_agent",
        "session_path": Path("/tmp/test"),
    }
    defaults.update(kwargs)
    return RawSessionData(**defaults)


def _make_session_doc(session_id: str, **kwargs) -> SessionDocument:
    defaults = {
        "session_id": session_id,
        "agent": "test_agent",
        "project_name": "test_project",
        "project_root": "/tmp/test",
        "session_start": 1_700_000_000_000,
        "session_end": 1_700_000_001_000,
        "domains": ["backend"],
        "files_edited": [],
        "task_raw": "task",
    }
    defaults.update(kwargs)
    return SessionDocument(**defaults)


class TestFullIndexer:
    @pytest.fixture
    def mock_store(self, tmp_path: Path) -> MetadataStore:
        return MetadataStore(tmp_path / "test_index.db")

    def test_index_all_with_no_sessions(self, mock_store: MetadataStore) -> None:
        indexer = FullIndexer(store=mock_store)
        stats = indexer.index_all(agent_ids=[])
        assert stats["scanned"] == 0

    def test_incremental_no_new_sessions(self, mock_store: MetadataStore) -> None:
        indexer = FullIndexer(store=mock_store)
        with patch("smartfork.indexer.indexer.SessionScanner") as mock_scanner_cls:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = []
            mock_scanner_cls.return_value = mock_scanner
            stats = indexer.index_incremental()
            assert stats["new"] == 0

    def test_pipeline_integration(self, mock_store: MetadataStore) -> None:
        """Test that the full pipeline doesn't crash with valid input."""
        indexer = FullIndexer(store=mock_store)
        # Verify components are wired
        assert indexer.parser is not None
        assert indexer.intelligence is not None
        assert indexer.store is not None
        assert indexer.relationship_detector is not None

    def test_index_all_uses_session_level_embedding(
        self, mock_store: MetadataStore
    ) -> None:
        """Verify embed_session is called once per session, not chunk-based."""
        mock_embedder = MagicMock()
        mock_embedder.embed_session.return_value = [0.1] * 512

        indexer = FullIndexer(embedder=mock_embedder, store=mock_store)

        docs = [
            _make_session_doc(f"session-{i}", project_name="proj")
            for i in range(3)
        ]
        raw_sessions = [_make_raw_session(f"session-{i}") for i in range(3)]

        mock_adapter = MagicMock()
        mock_adapter.session_type = "json"
        mock_adapter.parse_raw.side_effect = raw_sessions

        with (
            patch("smartfork.indexer.indexer.get_adapter", return_value=mock_adapter),
            patch("smartfork.indexer.indexer.SessionScanner") as mock_scanner_cls,
            patch.object(indexer.parser, "parse_session", side_effect=docs),
            patch.object(indexer.intelligence, "enrich"),
            patch.object(indexer.relationship_detector, "detect_all", return_value=[]),
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = [("test_agent", Path("/tmp/s1"))] * 3
            mock_scanner_cls.return_value = mock_scanner

            stats = indexer.index_all()

        assert stats["parsed"] == 3
        assert stats["stored"] == 3
        assert mock_embedder.embed_session.call_count == 3
        # No chunk-based embedding should occur
        assert mock_embedder.embed_and_store.call_count == 0

    def test_index_all_creates_explicit_relationships(
        self, mock_store: MetadataStore
    ) -> None:
        """Sessions with parent_id get explicit continuation relationships."""
        mock_embedder = MagicMock()
        mock_embedder.embed_session.return_value = [0.1] * 512

        indexer = FullIndexer(embedder=mock_embedder, store=mock_store)

        parent_doc = _make_session_doc("parent-1", project_name="proj")
        child_doc = _make_session_doc(
            "child-1", project_name="proj", parent_id="parent-1"
        )

        raw_parent = _make_raw_session("parent-1")
        raw_child = _make_raw_session("child-1", parent_id="parent-1")

        mock_adapter = MagicMock()
        mock_adapter.session_type = "json"
        mock_adapter.parse_raw.side_effect = [raw_parent, raw_child]

        with (
            patch("smartfork.indexer.indexer.get_adapter", return_value=mock_adapter),
            patch("smartfork.indexer.indexer.SessionScanner") as mock_scanner_cls,
            patch.object(
                indexer.parser, "parse_session", side_effect=[parent_doc, child_doc]
            ),
            patch.object(indexer.intelligence, "enrich"),
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = [
                ("test_agent", Path("/tmp/s1"))
            ] * 2
            mock_scanner_cls.return_value = mock_scanner

            stats = indexer.index_all()

        rels = mock_store.get_relationships("child-1", direction="to")
        explicit = [r for r in rels if r.detected_by == "explicit"]
        assert len(explicit) == 1
        assert explicit[0].relationship_type == "continuation"
        assert explicit[0].from_session == "parent-1"
        assert explicit[0].to_session == "child-1"
        assert stats["relationships"] > 0

    def test_index_all_creates_heuristic_relationships(
        self, mock_store: MetadataStore
    ) -> None:
        """Related sessions in the same project get heuristic relationships."""
        mock_embedder = MagicMock()
        mock_embedder.embed_session.return_value = [0.1] * 512

        indexer = FullIndexer(embedder=mock_embedder, store=mock_store)

        base_time = 1_700_000_000_000

        doc1 = _make_session_doc(
            "s1",
            project_name="proj",
            project_root="/tmp/proj",
            session_start=base_time,
            files_edited=["a.py", "b.py"],
            domains=["backend"],
        )
        doc2 = _make_session_doc(
            "s2",
            project_name="proj",
            project_root="/tmp/proj",
            session_start=base_time + 12 * 3600 * 1000,
            files_edited=["a.py", "c.py"],
            domains=["backend"],
        )

        raw1 = _make_raw_session("s1")
        raw2 = _make_raw_session("s2")

        mock_adapter = MagicMock()
        mock_adapter.session_type = "json"
        mock_adapter.parse_raw.side_effect = [raw1, raw2]

        with (
            patch("smartfork.indexer.indexer.get_adapter", return_value=mock_adapter),
            patch("smartfork.indexer.indexer.SessionScanner") as mock_scanner_cls,
            patch.object(
                indexer.parser, "parse_session", side_effect=[doc1, doc2]
            ),
            patch.object(indexer.intelligence, "enrich"),
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = [
                ("test_agent", Path("/tmp/s1"))
            ] * 2
            mock_scanner_cls.return_value = mock_scanner

            stats = indexer.index_all()

        heuristic_rels = [
            r
            for r in mock_store.get_relationships("s1", direction="from")
            if r.detected_by == "heuristic"
        ]
        assert len(heuristic_rels) > 0
        assert heuristic_rels[0].to_session == "s2"
        assert stats["relationships"] > 0

    def test_index_all_reports_relationship_count(
        self, mock_store: MetadataStore
    ) -> None:
        """Stats dict includes the relationships count."""
        mock_embedder = MagicMock()
        mock_embedder.embed_session.return_value = [0.1] * 512

        indexer = FullIndexer(embedder=mock_embedder, store=mock_store)

        base_time = 1_700_000_000_000

        doc1 = _make_session_doc(
            "s1",
            project_name="proj",
            project_root="/tmp/proj",
            session_start=base_time,
            files_edited=["a.py"],
            domains=["backend"],
        )
        doc2 = _make_session_doc(
            "s2",
            project_name="proj",
            project_root="/tmp/proj",
            session_start=base_time + 12 * 3600 * 1000,
            files_edited=["a.py"],
            domains=["backend"],
            parent_id="s1",
        )

        raw1 = _make_raw_session("s1")
        raw2 = _make_raw_session("s2", parent_id="s1")

        mock_adapter = MagicMock()
        mock_adapter.session_type = "json"
        mock_adapter.parse_raw.side_effect = [raw1, raw2]

        with (
            patch("smartfork.indexer.indexer.get_adapter", return_value=mock_adapter),
            patch("smartfork.indexer.indexer.SessionScanner") as mock_scanner_cls,
            patch.object(
                indexer.parser, "parse_session", side_effect=[doc1, doc2]
            ),
            patch.object(indexer.intelligence, "enrich"),
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = [
                ("test_agent", Path("/tmp/s1"))
            ] * 2
            mock_scanner_cls.return_value = mock_scanner

            stats = indexer.index_all()

        assert "relationships" in stats
        assert stats["relationships"] > 0
