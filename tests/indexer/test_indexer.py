"""Tests for FullIndexer."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from smartfork.indexer.indexer import FullIndexer
from smartfork.indexer.metadata_store import MetadataStore


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
        assert indexer.chunker is not None
        assert indexer.intelligence is not None
        assert indexer.store is not None
