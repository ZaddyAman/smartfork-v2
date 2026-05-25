"""JSON cache for evaluation results."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from loguru import logger


class EvalCache:
    """Disk-based cache for evaluation queries and judgments.

    Saves generated queries and LLM judge scores so re-runs are fast
    and results are reproducible. Cache invalidation is keyed on
    session ``indexed_at`` timestamps.
    """

    def __init__(self, cache_path: Path | str | None = None) -> None:
        """Initialize cache.

        Args:
            cache_path: Path to cache JSON file. Defaults to
                ``~/.smartfork/eval_cache.json``.
        """
        if cache_path is None:
            cache_path = Path.home() / ".smartfork" / "eval_cache.json"
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = self._load()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, encoding="utf-8") as fh:
                    data: dict[str, Any] = json.load(fh)
                    return data
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(f"Cache load failed ({exc}), starting fresh.")
        return {
            "version": 1,
            "session_sample": [],
            "generated_queries": {},
            "judgments": {},
        }

    def _save(self) -> None:
        try:
            with open(self.cache_path, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            logger.warning(f"Cache save failed: {exc}")

    # ------------------------------------------------------------------
    # Session sampling
    # ------------------------------------------------------------------

    def get_sampled_sessions(self) -> list[str] | None:
        """Return cached session IDs, or None if not yet sampled."""
        sample = self._data.get("session_sample")
        return sample if sample else None

    def set_sampled_sessions(self, session_ids: list[str]) -> None:
        self._data["session_sample"] = session_ids
        self._save()

    # ------------------------------------------------------------------
    # Generated queries
    # ------------------------------------------------------------------

    def get_generated_queries(self, session_id: str) -> list[dict[str, Any]] | None:
        """Return cached queries for a session, or None if not cached."""
        gq = self._data.get("generated_queries", {})
        entry = gq.get(session_id)
        if isinstance(entry, dict):
            queries = entry.get("queries")
            if isinstance(queries, list):
                return [q for q in queries if isinstance(q, dict)]
        return None

    def set_generated_queries(
        self,
        session_id: str,
        queries: list[dict[str, Any]],
        indexed_at: int,
    ) -> None:
        if "generated_queries" not in self._data:
            self._data["generated_queries"] = {}
        self._data["generated_queries"][session_id] = {
            "indexed_at": indexed_at,
            "queries": queries,
        }
        self._save()

    def is_query_cache_valid(self, session_id: str, current_indexed_at: int) -> bool:
        """Check if cached queries are still valid (session unchanged)."""
        gq = self._data.get("generated_queries", {})
        entry = gq.get(session_id)
        if not entry:
            return False
        return bool(entry.get("indexed_at") == current_indexed_at)

    # ------------------------------------------------------------------
    # Judgments
    # ------------------------------------------------------------------

    @staticmethod
    def _judge_key(query: str, result_session_id: str, mode: str) -> str:
        """Build a deterministic cache key for a judgment."""
        payload = f"{query}::{result_session_id}::{mode}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def get_judgment(self, query: str, result_session_id: str, mode: str) -> dict[str, Any] | None:
        """Return cached judgment, or None if not cached."""
        key = self._judge_key(query, result_session_id, mode)
        judgments = self._data.get("judgments", {})
        entry = judgments.get(key)
        return entry if isinstance(entry, dict) else None

    def set_judgment(
        self,
        query: str,
        result_session_id: str,
        mode: str,
        score: int,
        reason: str,
    ) -> None:
        key = self._judge_key(query, result_session_id, mode)
        if "judgments" not in self._data:
            self._data["judgments"] = {}
        self._data["judgments"][key] = {
            "query": query,
            "result_session_id": result_session_id,
            "mode": mode,
            "score": score,
            "reason": reason,
        }
        self._save()

    def clear(self) -> None:
        """Wipe the cache."""
        self._data = {
            "version": 1,
            "session_sample": [],
            "generated_queries": {},
            "judgments": {},
        }
        self._save()
        logger.info("Eval cache cleared.")
