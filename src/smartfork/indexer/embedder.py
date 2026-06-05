"""Embedding pipeline for SmartFork v2 — session-level embedding with sqlite-vec."""

from collections.abc import Callable

from loguru import logger

from smartfork.indexer.metadata_store import MetadataStore
from smartfork.indexer.session_essence_builder import SessionEssenceBuilder
from smartfork.models.session import SessionDocument
from smartfork.providers.protocols import EmbeddingProvider


class EmbeddingPipeline:
    """Orchestrates session embedding and sqlite-vec storage.

    Takes SessionDocument objects, builds an essence text, embeds it, and
    stores the vector in the SQLite-backed metadata store via sqlite-vec.
    """

    def __init__(
        self,
        embedder: EmbeddingProvider,
        store: MetadataStore | None = None,
        essence_builder: SessionEssenceBuilder | None = None,
    ) -> None:
        self.embedder = embedder
        self.store = store or MetadataStore()
        self.essence_builder = essence_builder or SessionEssenceBuilder()

    def embed_session(self, session: SessionDocument) -> list[float] | None:
        """Embed a single session and store in sqlite-vec.

        1. Build essence via ``SessionEssenceBuilder``.
        2. If the embedder supports instruction-aware embedding (Ollama),
           use ``build_essence_with_instruction``; otherwise use ``build_essence``.
        3. Embed text via the primary embedder.
        4. On failure, fall back to sentence-transformers ``mxbai-embed-large`` (1024d).
        5. On second failure, log an error and return ``None``.

        Args:
            session: The session to embed.

        Returns:
            The embedding vector, or ``None`` if embedding failed.
        """
        essence = self.essence_builder.build_essence(session)

        if hasattr(self.embedder, "_build_prompt"):
            text = self.essence_builder.build_essence_with_instruction(session)
        else:
            text = essence

        vector: list[float] | None = None
        try:
            vector = self.embedder.embed(text)
        except Exception:
            logger.warning(
                f"Primary embedder failed for session {session.session_id}, "
                "falling back to sentence-transformers"
            )
            try:
                from smartfork.providers.embedding import SentenceTransformerEmbedder

                fallback = SentenceTransformerEmbedder(
                    model="mixedbread-ai/mxbai-embed-large-v1",
                    dimensions=1024,
                )
                vector = fallback.embed(text)
            except Exception:
                logger.error(
                    f"Fallback embedder also failed for session {session.session_id}"
                )
                return None

        if vector is not None:
            self.store.store_vector(session.session_id, vector)

        return vector

    def embed_sessions_batch(
        self,
        sessions: list[SessionDocument],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, list[float]]:
        """Embed multiple sessions in batch.

        Builds essences for all sessions, attempts a batch embed via the primary
        embedder, and falls back to sequential :meth:`embed_session` calls if
        the batch operation fails.  Calls ``progress_callback(current, total)``
        after each successfully stored session when running sequentially, or once
        at the end when the batch succeeds.

        Args:
            sessions: List of sessions to embed.
            progress_callback: Optional callback(current, total) for progress.

        Returns:
            Dict mapping ``session_id`` → vector for successful embeddings.
        """
        vectors: dict[str, list[float]] = {}
        total = len(sessions)

        essences: list[str] = []
        for session in sessions:
            if hasattr(self.embedder, "_build_prompt"):
                essence = self.essence_builder.build_essence_with_instruction(session)
            else:
                essence = self.essence_builder.build_essence(session)
            essences.append(essence)

        if hasattr(self.embedder, "embed_batch"):
            try:
                batch_vectors = self.embedder.embed_batch(essences)
                for session, vec in zip(sessions, batch_vectors, strict=True):
                    self.store.store_vector(session.session_id, vec)
                    vectors[session.session_id] = vec
                if progress_callback:
                    progress_callback(total, total)
                return vectors
            except Exception as exc:
                logger.warning(
                    f"Batch embed failed, falling back to sequential: {exc}"
                )

        # Sequential fallback
        for i, session in enumerate(sessions):
            vector = self.embed_session(session)
            if vector is not None:
                vectors[session.session_id] = vector
            if progress_callback:
                progress_callback(i + 1, total)

        return vectors

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query.

        Args:
            query: The search query text.

        Returns:
            Query embedding vector.
        """
        return self.embedder.embed_query(query)
