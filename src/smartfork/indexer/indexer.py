"""FullIndexer — orchestrates the complete indexing pipeline."""

import contextlib
import time
from collections.abc import Callable
from typing import Any

from loguru import logger

from smartfork.adapters.registry import get_adapter
from smartfork.indexer.chunker import MessageBoundaryChunker
from smartfork.indexer.embedder import EmbeddingPipeline
from smartfork.indexer.intelligence import IndexIntelligence
from smartfork.indexer.metadata_store import MetadataStore
from smartfork.indexer.parser import SessionParser
from smartfork.indexer.scanner import SessionScanner
from smartfork.models.progress import ProgressEvent
from smartfork.models.session import RawSessionData, SessionDocument


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
        progress_callback: Callable[[ProgressEvent], None] | None = None,
    ) -> dict[str, Any]:
        """Run the full indexing pipeline.

        Args:
            agent_ids: Optional list of agent IDs to index. None = all.
            progress_callback: Optional callback(ProgressEvent) for progress.

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

        # ── 1. Scan for sessions ──
        scanner = SessionScanner()
        sessions = scanner.scan(agent_ids, progress_callback=progress_callback)
        stats["scanned"] = len(sessions)

        if progress_callback:
            progress_callback(ProgressEvent(
                phase="scanning",
                scan_status="done",
                scan_count=len(sessions),
            ))

        # ── 2. Parse each session ──
        parsed_sessions: list[tuple[str, SessionDocument]] = []

        # Pre-count sessions for accurate progress & cache SQLite results
        # to avoid double-queries.
        cached_sqlite: dict[object, list[Any]] = {}
        total_parse = 0
        for _aid, _sp in sessions:
            adapter = get_adapter(_aid)
            if adapter is None:
                total_parse += 1
                continue
            if (
                adapter.session_type == "sqlite"
                and hasattr(adapter, "get_all_sessions_from_db")
            ):
                all_raw = adapter.get_all_sessions_from_db(_sp)
                cached_sqlite[_sp] = all_raw
                total_parse += len(all_raw)
            else:
                total_parse += 1

        parse_i = 0
        current_agent = ""
        agent_parsed: dict[str, int] = {}
        agent_total: dict[str, int] = {}

        for agent_id, session_path in sessions:
            try:
                adapter = get_adapter(agent_id)
                if adapter is None:
                    logger.warning(f"No adapter for {agent_id}, skipping {session_path}")
                    stats["errors"] += 1
                    parse_i += 1
                    continue

                if agent_id != current_agent:
                    current_agent = agent_id
                    if current_agent not in agent_parsed:
                        agent_parsed[current_agent] = 0
                        agent_total[current_agent] = 0

                if (
                    adapter.session_type == "sqlite"
                    and hasattr(adapter, "get_all_sessions_from_db")
                ):
                    all_raw = cached_sqlite.get(session_path, [])
                    if not all_raw:
                        all_raw = adapter.get_all_sessions_from_db(session_path)
                    agent_total[current_agent] = len(all_raw)

                    for raw in all_raw:
                        if raw is None:
                            continue
                        doc = self.parser.parse_session(raw)
                        if doc is None:
                            stats["errors"] += 1
                            parse_i += 1
                            continue
                        parsed_sessions.append((agent_id, doc))
                        stats["parsed"] += 1
                        agent_parsed[current_agent] += 1
                        parse_i += 1

                        if progress_callback:
                            progress_callback(ProgressEvent(
                                phase="parsing",
                                current=parse_i,
                                total=total_parse,
                                agent_id=current_agent,
                                agent_current=agent_parsed.get(current_agent, 0),
                                agent_total=agent_total.get(current_agent, 0),
                                stats=stats,
                            ))
                else:
                    agent_total[current_agent] += 1
                    raw = adapter.parse_raw(session_path)
                    if raw is None:
                        logger.warning(f"Failed to parse {session_path}")
                        stats["errors"] += 1
                        parse_i += 1
                        continue

                    doc = self.parser.parse_session(raw)
                    if doc is None:
                        logger.warning(f"Failed to normalize {session_path}")
                        stats["errors"] += 1
                        parse_i += 1
                        continue

                    parsed_sessions.append((agent_id, doc))
                    stats["parsed"] += 1
                    agent_parsed[current_agent] += 1
                    parse_i += 1

                    if progress_callback:
                        progress_callback(ProgressEvent(
                            phase="parsing",
                            current=parse_i,
                            total=total_parse,
                            agent_id=current_agent,
                            agent_current=agent_parsed.get(current_agent, 0),
                            agent_total=agent_total.get(current_agent, 0),
                            stats=stats,
                        ))

            except Exception as e:
                logger.error(f"Error parsing {session_path}: {e}")
                stats["errors"] += 1
                parse_i += 1

        # ── 3. Chunk, embed, store, and enrich each parsed session ──
        total = len(parsed_sessions)

        # Fire transition event immediately so display switches from parse to index
        if progress_callback and total > 0:
            first_agent = parsed_sessions[0][0]
            progress_callback(ProgressEvent(
                phase="indexing",
                session_current=0,
                session_total=total,
                agent_id=first_agent,
                chunks=0,
                stats=stats,
            ))

        for i, (agent_id, doc) in enumerate(parsed_sessions):
            try:
                # Embed session
                if self.embedder:
                    vector = self.embedder.embed_session(doc)
                    if vector is not None:
                        stats["stored"] += 1

                # Set indexed_at timestamp
                doc.indexed_at = int(time.time() * 1000)

                # Enrich — pass sub-progress for per-step enrichment
                def enrich_progress(
                    event: ProgressEvent,
                    _i: int = i,
                    _a: str = agent_id,
                ) -> None:
                    event.session_current = _i + 1
                    event.session_total = total
                    event.agent_id = _a
                    event.stats = stats
                    if progress_callback:
                        progress_callback(event)

                self.intelligence.enrich(doc, progress_callback=enrich_progress)
                stats["enriched"] += 1

                # Store metadata
                self.store.upsert_session(doc)

                if progress_callback:
                    progress_callback(ProgressEvent(
                        phase="indexing",
                        session_current=i + 1,
                        session_total=total,
                        agent_id=agent_id,
                        stats=stats,
                    ))

            except Exception as e:
                logger.error(f"Error indexing session {doc.session_id}: {e}")
                stats["errors"] += 1
                if progress_callback:
                    progress_callback(ProgressEvent(
                        phase="indexing",
                        session_current=i + 1,
                        session_total=total,
                        agent_id=agent_id,
                        stats=stats,
                    ))

        elapsed = time.time() - start_time
        stats["elapsed_seconds"] = round(elapsed, 1)
        logger.info(
            f"Indexing complete: {stats['parsed']} parsed, "
            f"{stats['stored']} vectors stored, "
            f"{stats['errors']} errors in {elapsed:.1f}s"
        )
        return stats

    def index_incremental(
        self,
        progress_callback: Callable[[ProgressEvent], None] | None = None,
    ) -> dict[str, Any]:
        """Run incremental indexing — only index new/changed sessions.

        Args:
            progress_callback: Optional callback(ProgressEvent) for progress.

        Returns:
            Dict with indexing statistics.
        """
        start_time = time.time()
        # Get already-indexed session IDs
        indexed_ids: set[str] = set()
        with contextlib.suppress(Exception):
            indexed_ids = set(self.store.get_filtered_ids(limit=999_999_999))

        stats: dict[str, Any] = {
            "scanned": 0,
            "parsed": 0,
            "chunked": 0,
            "stored": 0,
            "enriched": 0,
            "errors": 0,
        }

        # Scan and filter
        scanner = SessionScanner()
        all_sessions = scanner.scan(progress_callback=progress_callback)
        stats["scanned"] = len(all_sessions)

        if progress_callback:
            progress_callback(ProgressEvent(
                phase="scanning",
                scan_status="done",
                scan_count=len(all_sessions),
            ))

        new_session_data: list[tuple[str, RawSessionData]] = []
        for agent_id, session_path in all_sessions:
            adapter = get_adapter(agent_id)
            if adapter is None:
                continue

            # SQLite adapters: get all sessions from the database
            if adapter.session_type == "sqlite" and hasattr(adapter, "get_all_sessions_from_db"):
                for raw in adapter.get_all_sessions_from_db(session_path):
                    if raw and raw.session_id not in indexed_ids:
                        new_session_data.append((agent_id, raw))
            else:
                session_id = session_path.stem
                if session_id not in indexed_ids:
                    raw = adapter.parse_raw(session_path)
                    if raw:
                        new_session_data.append((agent_id, raw))

        stats["new"] = len(new_session_data)

        logger.info(
            f"Incremental: {len(new_session_data)} new of "
            f"{len(all_sessions)} total scan entries"
        )

        total_parse = len(new_session_data)

        if progress_callback and total_parse == 0:
            # Short circuit so UI can close out even with zero items.
            progress_callback(ProgressEvent(phase="parsing", current=0, total=0, stats=stats))
            progress_callback(ProgressEvent(
                phase="indexing", session_current=0, session_total=0, stats=stats,
            ))

        for i, (agent_id, raw) in enumerate(new_session_data):
            try:
                # ── Parse ──
                if progress_callback:
                    progress_callback(ProgressEvent(
                        phase="parsing",
                        current=i + 1,
                        total=total_parse,
                        agent_id=agent_id,
                        stats=stats,
                    ))

                doc = self.parser.parse_session(raw)
                if doc is None:
                    stats["errors"] += 1
                    continue

                stats["parsed"] += 1
                doc.indexed_at = int(time.time() * 1000)

                # ── Embed ──
                if self.embedder:
                    vector = self.embedder.embed_session(doc)
                    if vector is not None:
                        stats["stored"] += 1

                # ── Enrich ──
                def enrich_progress(
                    event: ProgressEvent,
                    _i: int = i,
                    _a: str = agent_id,
                ) -> None:
                    event.session_current = _i + 1
                    event.session_total = total_parse
                    event.agent_id = _a
                    event.stats = stats
                    if progress_callback:
                        progress_callback(event)

                self.intelligence.enrich(doc, progress_callback=enrich_progress)
                stats["enriched"] += 1

                # ── Store ──
                self.store.upsert_session(doc)

                if progress_callback:
                    progress_callback(ProgressEvent(
                        phase="indexing",
                        session_current=i + 1,
                        session_total=total_parse,
                        agent_id=agent_id,
                        stats=stats,
                    ))

            except Exception as e:
                logger.error(f"Error in incremental indexing {raw.session_id}: {e}")
                stats["errors"] += 1

        stats["elapsed_seconds"] = round(time.time() - start_time, 1)
        return stats
