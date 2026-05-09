"""Search cache with TTL and session invalidation."""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict

from smartfork.models.search import ResultCard


class SearchCache:
    """LRU cache for search results with TTL and session invalidation."""

    def __init__(self, max_size: int = 128, ttl: int = 300) -> None:
        self.max_size = max_size
        self.ttl = ttl
        self._cache: OrderedDict[str, tuple[list[ResultCard], float]] = OrderedDict()
        self._session_index: dict[str, set[str]] = {}

    def _make_key(
        self,
        query: str,
        project_filter: str | None = None,
        quality_filter: str | None = None,
        top_k: int = 10,
    ) -> str:
        key_str = f"{query}|{project_filter}|{quality_filter}|{top_k}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(
        self,
        query: str,
        project_filter: str | None = None,
        quality_filter: str | None = None,
        top_k: int = 10,
    ) -> list[ResultCard] | None:
        """Retrieve cached results if present and not expired.

        Args:
            query: The search query string.
            project_filter: Optional project filter used in the search.
            quality_filter: Optional quality filter used in the search.
            top_k: Number of results requested.

        Returns:
            Cached list of ResultCard objects, or None if missing/expired.
        """
        key = self._make_key(query, project_filter, quality_filter, top_k)
        if key not in self._cache:
            return None
        results, expiry = self._cache[key]
        if time.time() > expiry:
            self._remove(key)
            return None
        self._cache.move_to_end(key)
        return results

    def put(
        self,
        query: str,
        results: list[ResultCard],
        project_filter: str | None = None,
        quality_filter: str | None = None,
        top_k: int = 10,
    ) -> None:
        """Store results in cache with TTL.

        Args:
            query: The search query string.
            results: List of ResultCard objects to cache.
            project_filter: Optional project filter used in the search.
            quality_filter: Optional quality filter used in the search.
            top_k: Number of results requested.
        """
        key = self._make_key(query, project_filter, quality_filter, top_k)
        expiry = time.time() + self.ttl
        self._cache[key] = (results, expiry)
        self._cache.move_to_end(key)

        # Index by session_id for invalidation
        for card in results:
            self._session_index.setdefault(card.session_id, set()).add(key)

        # Evict oldest if over size
        while len(self._cache) > self.max_size:
            oldest_key, _ = self._cache.popitem(last=False)
            self._remove_from_index(oldest_key)

    def invalidate_session(self, session_id: str) -> None:
        """Invalidate all cached entries that contain a given session.

        Args:
            session_id: The session ID to invalidate across the cache.
        """
        keys = self._session_index.pop(session_id, set())
        for key in list(keys):
            self._remove(key)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self._session_index.clear()

    def _remove(self, key: str) -> None:
        if key not in self._cache:
            return
        self._cache.pop(key)
        self._remove_from_index(key)

    def _remove_from_index(self, key: str) -> None:
        for sid, keys in list(self._session_index.items()):
            keys.discard(key)
            if not keys:
                del self._session_index[sid]
