"""Tests for the embedding pipeline."""

import pytest

from smartfork.indexer.chunker import Chunk
from smartfork.indexer.embedder import EmbeddingPipeline


class MockEmbedder:
    """Mock embedding provider for testing."""

    def __init__(self) -> None:
        self.embed_calls: list[str] = []
        self.query_calls: list[str] = []

    def embed(self, text: str, doc_type: str = "task_doc") -> list[float]:
        self.embed_calls.append(text)
        return [0.1, 0.2, 0.3]

    def embed_query(self, query: str) -> list[float]:
        self.query_calls.append(query)
        return [0.4, 0.5, 0.6]

    def embed_batch(self, texts: list[str], doc_type: str = "task_doc") -> list[list[float]]:
        return [[0.1]] * len(texts)

    def get_dimensions(self) -> int:
        return 3


class TestEmbeddingPipeline:
    @pytest.fixture
    def pipeline(self, tmp_path) -> EmbeddingPipeline:
        embedder = MockEmbedder()
        return EmbeddingPipeline(
            embedder=embedder,  # type: ignore[arg-type]
            persist_dir=tmp_path / "chroma_db",
            collection_name="test_collection",
            batch_size=2,
            max_retries=1,
        )

    def test_init_creates_persist_dir(self, tmp_path) -> None:
        embedder = MockEmbedder()
        _pipe = EmbeddingPipeline(
            embedder=embedder,  # type: ignore[arg-type]
            persist_dir=tmp_path / "test_chroma",
        )
        assert (tmp_path / "test_chroma").exists()

    def test_embed_query(self, pipeline) -> None:
        result = pipeline.embed_query("test query")
        assert len(result) == 3
        assert pipeline.embedder.query_calls == ["test query"]  # type: ignore[union-attr]

    def test_embed_and_store_basic(self, pipeline) -> None:
        chunks = [
            Chunk(
                chunk_id="sess1_task",
                session_id="sess1",
                content="Task: Fix the auth bug",
                doc_type="task_doc",
                chunk_index=0,
            ),
            Chunk(
                chunk_id="sess1_reason_1",
                session_id="sess1",
                content="The JWT token was expired.",
                doc_type="reasoning_doc",
                chunk_index=1,
            ),
        ]

        stored = pipeline.embed_and_store(chunks)
        assert stored == 2

    def test_embed_and_store_with_progress_callback(self, pipeline) -> None:
        chunks = [
            Chunk(
                chunk_id=f"chunk_{i}",
                session_id="sess1",
                content=f"Content {i}",
                doc_type="task_doc",
                chunk_index=i,
            )
            for i in range(5)
        ]

        progress_values: list[tuple[int, int]] = []
        def track(current: int, total: int) -> None:
            progress_values.append((current, total))

        stored = pipeline.embed_and_store(chunks, progress_callback=track)
        assert stored == 5
        assert len(progress_values) > 0

    def test_retry_on_failure(self, tmp_path) -> None:
        embedder = MockEmbedder()
        call_count = [0]

        def flaky_embed(text: str, doc_type: str = "task_doc") -> list[float]:
            call_count[0] += 1
            if call_count[0] < 3:
                raise RuntimeError("Temporary failure")
            return [0.1, 0.2, 0.3]

        embedder.embed = flaky_embed  # type: ignore[method-assign]

        pipeline = EmbeddingPipeline(
            embedder=embedder,  # type: ignore[arg-type]
            persist_dir=tmp_path / "chroma_retry",
            max_retries=3,
            batch_size=1,
        )

        chunk = Chunk(
            chunk_id="test_chunk",
            session_id="sess1",
            content="test",
            doc_type="task_doc",
            chunk_index=0,
        )

        stored = pipeline.embed_and_store([chunk])
        assert stored == 1
        assert call_count[0] == 3  # 2 failures + 1 success

    def test_get_collection_stats(self, pipeline) -> None:
        # Add some data first
        chunk = Chunk(
            chunk_id="stat_test",
            session_id="sess1",
            content="Test content",
            doc_type="task_doc",
            chunk_index=0,
        )
        pipeline.embed_and_store([chunk])

        stats = pipeline.get_collection_stats()
        assert stats["document_count"] >= 1
        assert stats["collection_name"] == "test_collection"
