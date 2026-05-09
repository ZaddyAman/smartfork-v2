"""Embedding pipeline for SmartFork v2 — chunk → embed → store in ChromaDB."""

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from loguru import logger

from smartfork.indexer.chunker import Chunk
from smartfork.providers.protocols import EmbeddingProvider


class EmbeddingPipeline:
    """Orchestrates chunk embedding and ChromaDB storage.

    Takes chunks from the chunking system, embeds them with instruction
    prefixes, and upserts vectors + metadata into ChromaDB.
    """

    def __init__(
        self,
        embedder: EmbeddingProvider,
        persist_dir: str | Path = "~/.smartfork/chroma_db",
        collection_name: str = "smartfork_sessions",
        batch_size: int = 32,
        max_retries: int = 3,
    ) -> None:
        self.embedder = embedder
        self.persist_dir = Path(persist_dir).expanduser()
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self.batch_size = batch_size
        self.max_retries = max_retries
        self._collection: Any | None = None

    @property
    def collection(self) -> Any:
        """Lazy-load the ChromaDB collection."""
        if self._collection is None:
            import chromadb
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self.persist_dir))
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def _retry_with_backoff(
        self, fn: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """Execute a function with exponential backoff retry.

        Args:
            fn: The function to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The function's return value.

        Raises:
            RuntimeError: If all retries exhausted.
        """
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(
                        f"Embedding attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {wait}s..."
                    )
                    time.sleep(wait)
        raise RuntimeError(
            f"All {self.max_retries} embedding attempts failed. Last error: {last_error}"
        ) from last_error

    def embed_and_store(
        self,
        chunks: list[Chunk],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> int:
        """Embed chunks and store in ChromaDB.

        Args:
            chunks: List of Chunk objects to embed and store.
            progress_callback: Optional callback(current, total) for progress.

        Returns:
            Number of chunks successfully stored.
        """
        stored = 0
        total = len(chunks)

        # Process in batches
        for i in range(0, total, self.batch_size):
            batch = chunks[i : i + self.batch_size]

            # Separate chunks by doc_type for instruction-aware embedding
            texts: list[str] = []
            ids: list[str] = []
            metadatas: list[dict[str, Any]] = []

            for chunk in batch:
                texts.append(chunk.content)
                ids.append(chunk.chunk_id)
                metadatas.append({
                    "session_id": chunk.session_id,
                    "doc_type": chunk.doc_type,
                    "chunk_index": str(chunk.chunk_index),
                    "is_code_block": str(chunk.is_code_block),
                })

            # Embed with retry — one text at a time (batch embedding not supported by all providers)
            embeddings: list[list[float]] = []
            for text in texts:
                emb = self._retry_with_backoff(self.embedder.embed, text)
                embeddings.append(emb)

            # Upsert to ChromaDB
            try:
                self.collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=texts,
                    metadatas=metadatas,
                )
                stored += len(batch)
            except Exception as e:
                logger.error(f"Failed to upsert batch to ChromaDB: {e}")
                raise

            if progress_callback:
                progress_callback(min(i + self.batch_size, total), total)

        return stored

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query.

        Args:
            query: The search query text.

        Returns:
            Query embedding vector.
        """
        return cast(list[float], self._retry_with_backoff(self.embedder.embed_query, query))

    def get_collection_stats(self) -> dict[str, Any]:
        """Get statistics about the ChromaDB collection.

        Returns:
            Dict with count and other stats.
        """
        try:
            count = self.collection.count()
            return {
                "collection_name": self.collection_name,
                "document_count": count,
                "persist_dir": str(self.persist_dir),
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {"error": str(e)}
