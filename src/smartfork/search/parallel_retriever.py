"""Parallel retriever that runs deterministic search across query variants."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from loguru import logger

from smartfork.models.search import QueryDecomposition, ResultCard
from smartfork.search.deterministic import (
    DeterministicSearchEngine,
    _humanize_duration,
    _humanize_timestamp,
)


class ParallelRetriever:
    """Runs deterministic search across query variants in parallel.

    Accepts a QueryDecomposition, executes each search variant concurrently
    through the deterministic engine, deduplicates by session_id, and returns
    enriched candidate dicts ready for reranking.
    """

    def __init__(self, deterministic_engine: DeterministicSearchEngine) -> None:
        self.deterministic_engine = deterministic_engine

    def retrieve(self, qd: QueryDecomposition, top_k: int) -> list[dict[str, Any]]:
        """Execute deterministic search across all variants in parallel.

        Args:
            qd: Query decomposition with search variants.
            top_k: Final number of top results desired.

        Returns:
            Flat list of candidate dicts with metadata for reranking.
        """
        if not qd.search_variants:
            return []

        all_candidates: list[dict[str, Any]] = []

        def _search_variant(variant: str) -> list[dict[str, Any]]:
            candidates: list[dict[str, Any]] = []
            try:
                cards = self.deterministic_engine.search(variant, top_k=top_k * 2)
            except Exception as e:
                logger.warning(f"Search variant '{variant}' failed: {e}")
                return candidates

            for card in cards:
                candidates.append(self._card_to_candidate(card))
            return candidates

        max_workers = min(5, len(qd.search_variants))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_search_variant, variant): variant
                for variant in qd.search_variants
            }
            for future in as_completed(futures):
                variant = futures[future]
                try:
                    results = future.result()
                    all_candidates.extend(results)
                except Exception as e:
                    logger.warning(f"Search variant '{variant}' raised: {e}")

        return self._deduplicate(all_candidates)

    def _card_to_candidate(self, card: ResultCard) -> dict[str, Any]:
        """Convert a ResultCard into a candidate dict.

        Enriches from metadata_store when available, otherwise falls back
        to ResultCard fields.
        """
        candidate: dict[str, Any] = {
            "session_id": card.session_id,
            "title": card.title,
            "match_score": card.match_score,
            "project_name": card.project_name,
            "fork_command": card.fork_command,
        }

        metadata_store = self.deterministic_engine.metadata_store
        if metadata_store is not None:
            try:
                session = metadata_store.get_session(card.session_id)
                if session is not None:
                    # Full content
                    task_raw = session.get("task_raw", "")
                    summary_doc = session.get("summary_doc", "")
                    content = summary_doc or task_raw
                    candidate["content"] = content
                    candidate["task_raw"] = task_raw
                    candidate["summary_doc"] = summary_doc

                    # Reasoning docs
                    reasoning_raw = session.get("reasoning_docs", "[]")
                    if isinstance(reasoning_raw, list):
                        candidate["reasoning_docs"] = reasoning_raw
                    else:
                        candidate["reasoning_docs"] = metadata_store._deserialize_list(
                            reasoning_raw
                        )

                    # Tags
                    tech_tags = metadata_store._deserialize_list(
                        session.get("tech_tags", "[]")
                    )
                    domains = metadata_store._deserialize_list(
                        session.get("domains", "[]")
                    )
                    languages = metadata_store._deserialize_list(
                        session.get("languages", "[]")
                    )
                    all_tags = tech_tags + domains + languages
                    seen: set[str] = set()
                    unique_tags: list[str] = []
                    for tag in all_tags:
                        tag_lower = tag.lower()
                        if tag_lower not in seen:
                            seen.add(tag_lower)
                            unique_tags.append(tag)
                    candidate["tags"] = unique_tags

                    # Files summary
                    files_edited = metadata_store._deserialize_list(
                        session.get("files_edited", "[]")
                    )
                    if files_edited:
                        count = len(files_edited)
                        candidate["files_summary"] = (
                            f"{count} file{'s' if count != 1 else ''} edited"
                        )
                    else:
                        candidate["files_summary"] = ""

                    # Time ago
                    ts = session.get("session_start", 0)
                    if ts:
                        candidate["time_ago"] = _humanize_timestamp(ts)
                    else:
                        candidate["time_ago"] = ""

                    # Duration
                    dur = session.get("duration_minutes", 0.0)
                    if dur:
                        candidate["duration"] = _humanize_duration(dur)
                    else:
                        candidate["duration"] = ""

                    return candidate
            except Exception as e:
                logger.warning(
                    f"Failed to enrich candidate for {card.session_id}: {e}"
                )

        # Fallback to ResultCard fields
        candidate["content"] = card.excerpt
        candidate["task_raw"] = card.excerpt
        candidate["summary_doc"] = ""
        candidate["reasoning_docs"] = []
        candidate["tags"] = card.tags
        candidate["files_summary"] = card.files_summary
        candidate["time_ago"] = card.time_ago
        candidate["duration"] = card.duration

        return candidate

    def _deduplicate(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deduplicate candidates by session_id, keeping the highest match_score."""
        seen: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            sid = candidate["session_id"]
            if sid not in seen or candidate.get("match_score", 0) > seen[sid].get(
                "match_score", 0
            ):
                seen[sid] = candidate
        return list(seen.values())
