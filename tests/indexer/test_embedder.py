"""Tests for the session-level embedding pipeline."""

from unittest.mock import MagicMock, patch

import pytest

from smartfork.indexer.embedder import EmbeddingPipeline
from smartfork.indexer.metadata_store import MetadataStore
from smartfork.indexer.session_essence_builder import SessionEssenceBuilder
from smartfork.models.session import SessionDocument


class MockEmbedder:
    """Mock embedding provider for testing."""

    def __init__(self) -> None:
        self.embed_calls: list[str] = []
        self.query_calls: list[str] = []
        self.batch_calls: list[list[str]] = []

    def embed(self, text: str, doc_type: str = "task_doc") -> list[float]:
        self.embed_calls.append(text)
        return [0.1, 0.2, 0.3]

    def embed_query(self, query: str) -> list[float]:
        self.query_calls.append(query)
        return [0.4, 0.5, 0.6]

    def embed_batch(self, texts: list[str], doc_type: str = "task_doc") -> list[list[float]]:
        self.batch_calls.append(texts)
        return [[0.1, 0.2, 0.3] for _ in texts]

    def get_dimensions(self) -> int:
        return 3


class MockOllamaEmbedder(MockEmbedder):
    """Mock Ollama embedder with instruction support."""

    def _build_prompt(self, text: str, doc_type: str) -> str:  # noqa: ARG002
        return f"prompt: {text}"


@pytest.fixture
def session() -> SessionDocument:
    return SessionDocument(
        session_id="sess1",
        agent="test",
        project_name="proj",
        project_root="/proj",
        task_raw="Fix the auth bug",
        summary_doc="Resolved JWT expiration issue",
        reasoning_docs=["The token was expired", "Refreshed with new secret"],
        tech_tags=["python", "jwt"],
    )


@pytest.fixture
def pipeline(tmp_path) -> EmbeddingPipeline:
    embedder = MockEmbedder()
    store = MetadataStore(db_path=tmp_path / "metadata.db")
    return EmbeddingPipeline(
        embedder=embedder,  # type: ignore[arg-type]
        store=store,
    )


class TestEmbedSession:
    def test_embed_session_stores_vector(self, pipeline: EmbeddingPipeline, session: SessionDocument) -> None:
        pipeline.store.store_vector = MagicMock()  # type: ignore[method-assign]

        vector = pipeline.embed_session(session)

        assert vector is not None
        assert len(vector) == 3
        pipeline.store.store_vector.assert_called_once_with(session.session_id, vector)  # type: ignore[union-attr]

    def test_embed_session_uses_instruction_prefix_for_ollama(self, tmp_path, session: SessionDocument) -> None:
        embedder = MockOllamaEmbedder()
        store = MetadataStore(db_path=tmp_path / "metadata.db")
        pipeline = EmbeddingPipeline(
            embedder=embedder,  # type: ignore[arg-type]
            store=store,
        )

        pipeline.embed_session(session)

        # Should have used build_essence_with_instruction (instruction prefix present)
        assert len(embedder.embed_calls) == 1
        assert embedder.embed_calls[0].startswith("Represent this coding session for semantic retrieval:")

    def test_embed_session_fallback_to_st(self, pipeline: EmbeddingPipeline, session: SessionDocument) -> None:
        # Force primary embedder to fail
        pipeline.embedder.embed = MagicMock(side_effect=RuntimeError("primary failed"))  # type: ignore[method-assign]
        pipeline.store.store_vector = MagicMock()  # type: ignore[method-assign]

        with patch(
            "smartfork.providers.embedding.SentenceTransformerEmbedder",
        ) as mock_st_class:
            mock_fallback = MagicMock()
            mock_fallback.embed.return_value = [0.9, 0.8, 0.7]
            mock_st_class.return_value = mock_fallback

            vector = pipeline.embed_session(session)

        assert vector == [0.9, 0.8, 0.7]
        mock_st_class.assert_called_once_with(
            model="mixedbread-ai/mxbai-embed-large-v1",
            dimensions=1024,
        )
        pipeline.store.store_vector.assert_called_once_with(session.session_id, [0.9, 0.8, 0.7])  # type: ignore[union-attr]

    def test_embed_session_double_failure_returns_none(self, pipeline: EmbeddingPipeline, session: SessionDocument) -> None:
        pipeline.embedder.embed = MagicMock(side_effect=RuntimeError("primary failed"))  # type: ignore[method-assign]

        with patch(
            "smartfork.providers.embedding.SentenceTransformerEmbedder",
        ) as mock_st_class:
            mock_fallback = MagicMock()
            mock_fallback.embed.side_effect = RuntimeError("fallback failed")
            mock_st_class.return_value = mock_fallback

            vector = pipeline.embed_session(session)

        assert vector is None


class TestEmbedSessionsBatch:
    def test_embed_sessions_batch_with_embed_batch(self, pipeline: EmbeddingPipeline) -> None:
        sessions = [
            SessionDocument(
                session_id=f"sess{i}",
                agent="test",
                project_name="proj",
                project_root="/proj",
                task_raw=f"Task {i}",
            )
            for i in range(3)
        ]
        pipeline.store.store_vector = MagicMock()  # type: ignore[method-assign]

        result = pipeline.embed_sessions_batch(sessions)

        assert len(result) == 3
        for sess in sessions:
            assert sess.session_id in result
            pipeline.store.store_vector.assert_any_call(sess.session_id, result[sess.session_id])  # type: ignore[union-attr]

    def test_embed_sessions_batch_sequential_fallback(self, pipeline: EmbeddingPipeline) -> None:
        sessions = [
            SessionDocument(
                session_id=f"sess{i}",
                agent="test",
                project_name="proj",
                project_root="/proj",
                task_raw=f"Task {i}",
            )
            for i in range(2)
        ]

        # Force batch embed to fail
        pipeline.embedder.embed_batch = MagicMock(side_effect=RuntimeError("batch failed"))  # type: ignore[method-assign]
        pipeline.store.store_vector = MagicMock()  # type: ignore[method-assign]

        result = pipeline.embed_sessions_batch(sessions)

        assert len(result) == 2
        for sess in sessions:
            assert sess.session_id in result

    def test_embed_sessions_batch_progress_callback(self, pipeline: EmbeddingPipeline) -> None:
        sessions = [
            SessionDocument(
                session_id=f"sess{i}",
                agent="test",
                project_name="proj",
                project_root="/proj",
                task_raw=f"Task {i}",
            )
            for i in range(3)
        ]

        progress_values: list[tuple[int, int]] = []

        def track(current: int, total: int) -> None:
            progress_values.append((current, total))

        result = pipeline.embed_sessions_batch(sessions, progress_callback=track)

        assert len(result) == 3
        assert len(progress_values) == 1
        assert progress_values[0] == (3, 3)

    def test_embed_sessions_batch_progress_callback_sequential_fallback(self, pipeline: EmbeddingPipeline) -> None:
        sessions = [
            SessionDocument(
                session_id=f"sess{i}",
                agent="test",
                project_name="proj",
                project_root="/proj",
                task_raw=f"Task {i}",
            )
            for i in range(3)
        ]

        pipeline.embedder.embed_batch = MagicMock(side_effect=RuntimeError("batch failed"))  # type: ignore[method-assign]

        progress_values: list[tuple[int, int]] = []

        def track(current: int, total: int) -> None:
            progress_values.append((current, total))

        result = pipeline.embed_sessions_batch(sessions, progress_callback=track)

        assert len(result) == 3
        assert len(progress_values) == 3
        assert progress_values == [(1, 3), (2, 3), (3, 3)]


class TestEmbedQuery:
    def test_embed_query(self, pipeline: EmbeddingPipeline) -> None:
        result = pipeline.embed_query("test query")
        assert result == [0.4, 0.5, 0.6]
        assert pipeline.embedder.query_calls == ["test query"]  # type: ignore[union-attr]


class TestKeyboardInterrupt:
    def test_keyboard_interrupt_propagates(self, tmp_path, session: SessionDocument) -> None:
        embedder = MockEmbedder()

        def raise_keyboard_interrupt(text: str, doc_type: str = "task_doc") -> list[float]:
            raise KeyboardInterrupt("user cancelled")

        embedder.embed = raise_keyboard_interrupt  # type: ignore[method-assign]

        store = MetadataStore(db_path=tmp_path / "metadata.db")
        pipeline = EmbeddingPipeline(
            embedder=embedder,  # type: ignore[arg-type]
            store=store,
        )

        with pytest.raises(KeyboardInterrupt):
            pipeline.embed_session(session)
