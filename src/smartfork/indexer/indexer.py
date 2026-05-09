"""FullIndexer — orchestrates the complete indexing pipeline."""

import contextlib
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger

from smartfork.adapters.registry import get_adapter
from smartfork.indexer.chunker import MessageBoundaryChunker
from smartfork.indexer.embedder import EmbeddingPipeline
from smartfork.indexer.intelligence import IndexIntelligence
from smartfork.indexer.metadata_store import MetadataStore
from smartfork.indexer.parser import SessionParser
from smartfork.indexer.scanner import SessionScanner
from smartfork.models.session import SessionDocument


class FullIndexer:
    """Orchestrates the complete indexing pipeline.

    Flow: scan → parse → chunk → embed → store → enrich
    """

    def __init__(
        self,
        embedder: EmbeddingPipeline | None = None,
        store: MetadataStore | None = None,
        intelligence: IndexIntelligence | None = None,
        parser: SessionParser | None = None,
        chunker: MessageBoundaryChunker | None = None,
    ) -> None:
        self.embedder = embedder
        self.store = store or MetadataStore()
        self.intelligence = intelligence or IndexIntelligence()
        self.parser = parser or SessionParser()
        self.chunker = chunker or MessageBoundaryChunker()

    def index_all(
        self,
        agent_ids: list[str] | None = None,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> dict[str, Any]:
        """Run the full indexing pipeline.

        Args:
            agent_ids: Optional list of agent IDs to index. None = all.
            progress_callback: Optional callback(stage, current, total) for progress.

        Returns:
            Dict with indexing statistics.
        """
        start_time = time.time()
        stats: dict[str, Any] = {
            "scanned": 0,
            "parsed": 0,
            "chunked": 0,
            "stored": 0,
            "enriched": 0,
            "errors": 0,
        }

        # 1. Scan for sessions
        scanner = SessionScanner()
        sessions = scanner.scan(agent_ids)
        stats["scanned"] = len(sessions)

        if progress_callback:
            progress_callback("scan", len(sessions), len(sessions))

        # 2. Parse each session
        parsed_sessions: list[tuple[str, SessionDocument]] = []
        for i, (agent_id, session_path) in enumerate(sessions):
            try:
                adapter = get_adapter(agent_id)
                if adapter is None:
                    logger.warning(f"No adapter for {agent_id}, skipping {session_path}")
                    stats["errors"] += 1
                    continue

                raw = adapter.parse_raw(session_path)
                if raw is None:
                    logger.warning(f"Failed to parse {session_path}")
                    stats["errors"] += 1
                    continue

                doc = self.parser.parse_session(raw)
                if doc is None:
                    logger.warning(f"Failed to normalize {session_path}")
                    stats["errors"] += 1
                    continue

                parsed_sessions.append((agent_id, doc))
                stats["parsed"] += 1

                if progress_callback:
                    progress_callback("parse", i + 1, len(sessions))

            except Exception as e:
                logger.error(f"Error parsing {session_path}: {e}")
                stats["errors"] += 1

        # 3. Chunk, embed, store, and enrich each parsed session
        total = len(parsed_sessions)
        for i, (_agent_id, doc) in enumerate(parsed_sessions):
            try:
                # Chunk
                chunks = self.chunker.chunk(doc)
                stats["chunked"] += len(chunks)

                # Embed and store
                if self.embedder:
                    stored = self.embedder.embed_and_store(chunks)
                    stats["stored"] += stored

                # Enrich
                self.intelligence.enrich(doc)
                stats["enriched"] += 1

                # Store metadata
                self.store.upsert_session(doc)

                if progress_callback:
                    progress_callback("index", i + 1, total)

            except Exception as e:
                logger.error(f"Error indexing session {doc.session_id}: {e}")
                stats["errors"] += 1

        elapsed = time.time() - start_time
        stats["elapsed_seconds"] = round(elapsed, 1)
        logger.info(
            f"Indexing complete: {stats['parsed']} parsed, "
            f"{stats['stored']} chunks stored, "
            f"{stats['errors']} errors in {elapsed:.1f}s"
        )
        return stats

    def index_incremental(self) -> dict[str, Any]:
        """Run incremental indexing — only index new/changed sessions.

        Returns:
            Dict with indexing statistics.
        """
        # Get already-indexed session IDs
        indexed_ids: set[str] = set()
        with contextlib.suppress(Exception):
            indexed_ids = set(self.store.get_filtered_ids(limit=999_999_999))

        # Scan and filter
        scanner = SessionScanner()
        all_sessions = scanner.scan()

        new_sessions: list[tuple[str, Path]] = []
        for agent_id, session_path in all_sessions:
            session_id = session_path.stem
            if session_id not in indexed_ids:
                new_sessions.append((agent_id, session_path))

        logger.info(
            f"Incremental: {len(new_sessions)} new of {len(all_sessions)} total sessions"
        )

        stats: dict[str, Any] = {
            "scanned": len(all_sessions),
            "new": len(new_sessions),
            "parsed": 0,
            "stored": 0,
            "errors": 0,
        }

        if not new_sessions:
            return stats

        for agent_id, session_path in new_sessions:
            try:
                adapter = get_adapter(agent_id)
                if adapter is None:
                    stats["errors"] += 1
                    continue
                raw = adapter.parse_raw(session_path)
                if raw is None:
                    stats["errors"] += 1
                    continue
                doc = self.parser.parse_session(raw)
                if doc is None:
                    stats["errors"] += 1
                    continue
                chunks = self.chunker.chunk(doc)
                if self.embedder:
                    stats["stored"] += self.embedder.embed_and_store(chunks)
                self.intelligence.enrich(doc)
                self.store.upsert_session(doc)
                stats["parsed"] += 1
            except Exception as e:
                logger.error(f"Error in incremental indexing {session_path}: {e}")
                stats["errors"] += 1

        return stats
