"""Deterministic search engine (Path A) for SmartFork v2."""

import time
from typing import Any

from loguru import logger

from smartfork.indexer.metadata_store import MetadataStore
from smartfork.models.search import QueryDecomposition, ResultCard, SearchIntent

# Intent detection patterns
INTENT_PATTERNS: dict[SearchIntent, list[str]] = {
    SearchIntent.ERROR_RECALL: [
        "error", "bug", "fix", "crash", "broken", "fail", "exception",
        "traceback", "stack trace", "not working", "issue",
    ],
    SearchIntent.IMPLEMENTATION_LOOKUP: [
        "how did i", "how to", "implement", "build", "create", "setup",
        "configure", "add", "write", "code for",
    ],
    SearchIntent.DECISION_HUNTING: [
        "why did", "why choose", "why use", "decision", "approach",
        "alternative", "tradeoff", "instead of", "versus", "vs",
    ],
    SearchIntent.PATTERN_HUNTING: [
        "pattern", "architecture", "design pattern", "best practice",
        "convention", "style", "idiom",
    ],
    SearchIntent.TEMPORAL_LOOKUP: [
        "last week", "yesterday", "recently", "today", "earlier",
        "this week", "this month", "last session",
    ],
    SearchIntent.CONTINUATION: [
        "continue", "resume", "pick up", "where i left", "go back to",
        "finish", "complete the",
    ],
}


def _humanize_timestamp(ts_ms: int) -> str:
    """Convert millisecond timestamp to human-readable relative time."""
    now = int(time.time() * 1000)
    diff_ms = now - ts_ms
    if diff_ms < 0:
        return "just now"

    seconds = diff_ms // 1000
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24

    if days > 30:
        months = days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    if days > 0:
        return f"{days} day{'s' if days > 1 else ''} ago"
    if hours > 0:
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    if minutes > 0:
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    return "just now"


def _humanize_duration(minutes: float) -> str:
    """Convert duration in minutes to human-readable string."""
    if minutes < 1:
        return "<1 min"
    if minutes < 60:
        return f"{int(minutes)} min"
    hours = minutes / 60
    return f"{hours:.1f}h"


class QueryParser:
    """Regex-based query parser for intent detection and entity extraction."""

    # Common technology keywords (90+)
    TECH_KEYWORDS: set[str] = {
        "python", "javascript", "typescript", "rust", "go", "java", "kotlin",
        "react", "vue", "angular", "svelte", "next.js", "nuxt",
        "fastapi", "flask", "django", "express", "spring", "rails",
        "postgresql", "mysql", "mongodb", "redis", "sqlite", "prisma",
        "docker", "kubernetes", "terraform", "aws", "gcp", "azure",
        "graphql", "rest", "grpc", "websocket", "soap",
        "jwt", "oauth", "auth0", "keycloak",
        "pytest", "jest", "cypress", "selenium",
        "pandas", "numpy", "tensorflow", "pytorch",
        "git", "github", "gitlab", "bitbucket",
        "ci/cd", "jenkins", "actions", "pipeline",
        "css", "scss", "tailwind", "bootstrap", "html",
        "linux", "bash", "powershell", "shell",
        "vscode", "cursor", "neovim", "intellij",
        "api", "cli", "sdk", "library", "framework", "package",
        "database", "cache", "queue", "proxy", "load balancer",
        "auth", "authn", "authz", "encryption", "ssl", "tls",
        "sql", "nosql", "orm", "migration", "seed",
        "react native", "flutter", "electron", "tauri",
    }

    def parse(self, query: str) -> QueryDecomposition:
        """Parse a user query into structured decomposition.

        Args:
            query: Raw user search query.

        Returns:
            QueryDecomposition with intent, entities, and search variants.
        """
        query_lower = query.lower()

        # Detect intent
        intent = self._detect_intent(query_lower)

        # Extract entities (tech keywords, file names, concepts)
        entities = self._extract_entities(query_lower)

        # Generate search variants
        variants = self._generate_variants(query, intent)

        # Temporal preference
        prefer_recent = intent == SearchIntent.TEMPORAL_LOOKUP
        prefer_code = intent in (SearchIntent.IMPLEMENTATION_LOOKUP, SearchIntent.ERROR_RECALL)

        return QueryDecomposition(
            core_goal=query,
            search_variants=variants,
            entities={"technologies": entities},
            intent=intent.value,
            prefer_code=prefer_code,
            prefer_recent=prefer_recent,
        )

    def _detect_intent(self, query_lower: str) -> SearchIntent:
        """Detect search intent from query keywords."""
        scores: dict[SearchIntent, int] = {}
        for intent, keywords in INTENT_PATTERNS.items():
            score = sum(1 for kw in keywords if kw in query_lower)
            if score > 0:
                scores[intent] = score

        if scores:
            return max(scores, key=lambda k: scores[k])
        return SearchIntent.VAGUE_MEMORY

    def _extract_entities(self, query_lower: str) -> list[str]:
        """Extract technology keywords and entities from query."""
        entities: set[str] = set()
        for keyword in self.TECH_KEYWORDS:
            if keyword in query_lower:
                entities.add(keyword)
        return sorted(entities)

    def _generate_variants(self, query: str, intent: SearchIntent) -> list[str]:
        """Generate search variants from the original query."""
        variants = [query]
        words = query.split()

        # Drop stop words variant
        stop_words = {"the", "a", "an", "is", "was", "in", "on", "at", "to", "for"}
        cleaned = " ".join(w for w in words if w.lower() not in stop_words)
        if cleaned != query:
            variants.append(cleaned)

        # Intent-specific variants
        if intent == SearchIntent.ERROR_RECALL:
            variants.append(f"fix error {query}")
        elif intent == SearchIntent.IMPLEMENTATION_LOOKUP:
            variants.append(f"how to implement {query}")

        return variants


class DeterministicSearchEngine:
    """Deterministic search: embed -> vector + BM25 -> RRF fusion -> rerank -> cards.

    This is the always-available, zero-cost search path. It uses:
    - ChromaDB for vector search
    - rank-bm25 for keyword search
    - Reciprocal Rank Fusion (RRF) to combine results
    - Multi-signal reranker for final ordering
    """

    def __init__(self, embedder: Any | None = None, metadata_store: Any | None = None) -> None:
        self.embedder = embedder
        self.metadata_store = metadata_store
        self.query_parser = QueryParser()

    def search(
        self,
        query: str,
        top_k: int = 10,
        project_filter: str | None = None,
        quality_filter: str | None = None,
    ) -> list[ResultCard]:
        """Execute a deterministic search.

        Args:
            query: User search query.
            top_k: Number of results to return.
            project_filter: Optional project name filter.
            quality_filter: Optional quality tag filter.

        Returns:
            List of ResultCard objects.
        """
        decomposition = self.query_parser.parse(query)

        # If embedder is available, do vector search
        vector_results: dict[str, float] = {}
        if self.embedder:
            try:
                vector_results = self._vector_search(query, top_k * 2)
            except Exception as e:
                logger.warning(f"Vector search failed: {e}")

        # BM25 search
        bm25_results: dict[str, float] = self._bm25_search(query, top_k * 2)

        # RRF fusion
        fused = self._rrf_fuse(vector_results, bm25_results, k=60)

        # Metadata filter
        if project_filter or quality_filter:
            fused = self._apply_filters(fused, project_filter, quality_filter)

        # Rerank
        reranked = self._rerank(fused, decomposition)

        # Format as result cards
        cards = self._format_cards(reranked[:top_k], decomposition)

        return cards

    def _vector_search(self, query: str, top_k: int) -> dict[str, float]:
        """Perform vector similarity search via ChromaDB.

        Embeds the query, queries the ChromaDB collection, and maps
        chunk results back to session IDs (taking max score per session).
        """
        if not self.embedder:
            return {}

        try:
            query_vec = self.embedder.embed_query(query)
            collection = self.embedder.collection
            results = collection.query(
                query_embeddings=[query_vec],
                n_results=min(top_k * 3, 100),  # fetch extra since we aggregate
                include=["metadatas", "distances"],
            )
        except Exception as e:
            logger.debug(f"ChromaDB query failed: {e}")
            return {}

        session_scores: dict[str, float] = {}
        if results and results.get("metadatas") and results.get("distances"):
            metadatas_list = results["metadatas"][0]
            distances_list = results["distances"][0]
            for meta, distance in zip(metadatas_list, distances_list, strict=False):
                session_id = meta.get("session_id", "")
                if not session_id:
                    continue
                # ChromaDB cosine distance: 0 = identical, 2 = opposite
                # Convert to similarity: 1 - (distance / 2)
                similarity = max(0.0, 1.0 - (distance / 2.0))
                if session_id not in session_scores or similarity > session_scores[session_id]:
                    session_scores[session_id] = similarity

        return session_scores

    def _bm25_search(self, query: str, top_k: int) -> dict[str, float]:
        """Perform BM25 keyword search over session metadata.

        Builds a corpus from task_raw + summary_doc of all sessions in the
        metadata store and ranks using BM25Okapi.
        """
        if not self.metadata_store:
            return {}

        # Fetch all sessions from metadata store
        try:
            store: MetadataStore = self.metadata_store
            all_ids = store.get_filtered_ids(limit=10_000)
        except Exception as e:
            logger.debug(f"Failed to fetch session IDs for BM25: {e}")
            return {}

        if not all_ids:
            return {}

        # Build corpus
        corpus_docs: list[list[str]] = []
        session_ids: list[str] = []
        for sid in all_ids:
            try:
                session_data = store.get_session(sid)
                if session_data is None:
                    continue
                # Combine searchable fields
                text = " ".join([
                    session_data.get("task_raw", ""),
                    session_data.get("summary_doc", ""),
                    session_data.get("project_name", ""),
                    " ".join(store._deserialize_list(session_data.get("domains", "[]"))),
                    " ".join(store._deserialize_list(session_data.get("languages", "[]"))),
                    " ".join(store._deserialize_list(session_data.get("tech_tags", "[]"))),
                ]).lower().split()
                if text:
                    corpus_docs.append(text)
                    session_ids.append(sid)
            except Exception:
                continue

        if not corpus_docs:
            return {}

        # Run BM25
        try:
            from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]
            bm25 = BM25Okapi(corpus_docs)
            tokenized_query = query.lower().split()
            scores = bm25.get_scores(tokenized_query)

            session_scores: dict[str, float] = {}
            for sid, score in zip(session_ids, scores, strict=False):
                if score > 0:
                    session_scores[sid] = float(score)

            # Normalize to 0-1 range
            if session_scores:
                max_score = max(session_scores.values())
                if max_score > 0:
                    session_scores = {
                        sid: s / max_score for sid, s in session_scores.items()
                    }

            # Return top-k
            sorted_results = sorted(session_scores.items(), key=lambda x: -x[1])
            return dict(sorted_results[:top_k])

        except ImportError:
            logger.debug("rank-bm25 not installed, skipping BM25 search")
            return {}
        except Exception as e:
            logger.debug(f"BM25 search failed: {e}")
            return {}

    def _rrf_fuse(
        self,
        vector_results: dict[str, float],
        bm25_results: dict[str, float],
        k: int = 60,
    ) -> dict[str, float]:
        """Reciprocal Rank Fusion — combine vector and BM25 results.

        Args:
            vector_results: {session_id: similarity_score}
            bm25_results: {session_id: bm25_score}
            k: RRF constant (default 60).

        Returns:
            Fused {session_id: rrf_score} dict, sorted descending.
        """
        if not vector_results and not bm25_results:
            return {}

        # Build rank maps
        vec_ranked = sorted(vector_results.items(), key=lambda x: -x[1])
        bm25_ranked = sorted(bm25_results.items(), key=lambda x: -x[1])

        rrf_scores: dict[str, float] = {}

        for rank, (session_id, _) in enumerate(vec_ranked, start=1):
            rrf_scores[session_id] = rrf_scores.get(session_id, 0) + 1.0 / (k + rank)

        for rank, (session_id, _) in enumerate(bm25_ranked, start=1):
            rrf_scores[session_id] = rrf_scores.get(session_id, 0) + 1.0 / (k + rank)

        return dict(sorted(rrf_scores.items(), key=lambda x: -x[1]))

    def _apply_filters(
        self,
        results: dict[str, float],
        project_filter: str | None,
        quality_filter: str | None,
    ) -> dict[str, float]:
        """Filter results by metadata criteria."""
        if not self.metadata_store:
            return results

        filtered: dict[str, float] = {}
        for session_id, score in results.items():
            session = self.metadata_store.get_session(session_id)
            if session is None:
                continue
            if project_filter and session.get("project_name") != project_filter:
                continue
            if quality_filter and session.get("quality_tag") != quality_filter:
                continue
            filtered[session_id] = score
        return filtered

    def _rerank(
        self, results: dict[str, float], decomposition: QueryDecomposition
    ) -> list[tuple[str, float]]:
        """Multi-signal reranker: semantic 50%, file 20%, keyword 15%, recency 5%, quality 10%."""
        reranked: list[tuple[str, float]] = []
        for session_id, base_score in results.items():
            # Base score carries 50% weight
            final_score = base_score * 0.5

            if self.metadata_store:
                session = self.metadata_store.get_session(session_id)
                if session:
                    # Quality bonus (10%)
                    quality = session.get("quality_tag", "unknown")
                    if quality == "solution_found":
                        final_score += 0.10
                    elif quality == "partial":
                        final_score += 0.05

                    # Recency bonus (5%)
                    if decomposition.prefer_recent:
                        ts = session.get("session_start", 0)
                        if ts > 0:
                            age_days = (time.time() * 1000 - ts) / (86400 * 1000)
                            if age_days < 7:
                                final_score += 0.05
                            elif age_days < 30:
                                final_score += 0.03
            else:
                # Bonus for recency (if temporal intent)
                if decomposition.prefer_recent:
                    final_score += 0.05

            # Bonus for code preference
            if decomposition.prefer_code:
                final_score += 0.05

            reranked.append((session_id, final_score))

        return sorted(reranked, key=lambda x: -x[1])

    def _format_cards(
        self, ranked: list[tuple[str, float]], decomposition: QueryDecomposition
    ) -> list[ResultCard]:
        """Format ranked results into display-ready ResultCards."""
        cards: list[ResultCard] = []
        for rank, (session_id, score) in enumerate(ranked, start=1):
            # Pull metadata if available
            title = session_id
            project_name = ""
            quality_badge = ""
            time_ago = ""
            duration = ""
            files_summary = ""
            excerpt = ""

            if self.metadata_store:
                session = self.metadata_store.get_session(session_id)
                if session:
                    title = session.get("task_raw", session_id) or session_id
                    title = title.strip("'\"`")
                    if len(title) > 50:
                        title = title[:47] + "..."
                    project_name = session.get("project_name", "")
                    quality = session.get("quality_tag", "unknown")
                    quality_map = {
                        "solution_found": "✓ Solved",
                        "partial": "⚠ Partial",
                        "dead_end": "✗ Dead End",
                        "reference": "📖 Reference",
                        "unknown": "? Unknown",
                    }
                    quality_badge = quality_map.get(quality, quality)

                    ts = session.get("session_start", 0)
                    if ts:
                        time_ago = _humanize_timestamp(ts)
                    dur = session.get("duration_minutes", 0.0)
                    if dur:
                        duration = _humanize_duration(dur)

                    # Files summary
                    files_edited = self.metadata_store._deserialize_list(
                        session.get("files_edited", "[]")
                    )
                    if files_edited:
                        count = len(files_edited)
                        files_summary = f"{count} file{'s' if count != 1 else ''} edited"

                    # Excerpt from summary or task
                    excerpt = session.get("summary_doc", "") or session.get("task_raw", "")
                    if len(excerpt) > 120:
                        excerpt = excerpt[:117] + "..."

                    # Tags: combine tech_tags + domains + languages
                    tech_tags = self.metadata_store._deserialize_list(
                        session.get("tech_tags", "[]")
                    )
                    domains = self.metadata_store._deserialize_list(
                        session.get("domains", "[]")
                    )
                    languages = self.metadata_store._deserialize_list(
                        session.get("languages", "[]")
                    )
                    all_tags = tech_tags + domains + languages

                    # Deduplicate case-insensitively, preserving original case of first occurrence
                    seen: set[str] = set()
                    unique_tags: list[str] = []
                    for tag in all_tags:
                        tag_lower = tag.lower()
                        if tag_lower not in seen:
                            seen.add(tag_lower)
                            unique_tags.append(tag)

                    # Prioritize tags matching query entities, then limit to 5
                    entity_values: list[str] = []
                    for v in decomposition.entities.values():
                        if isinstance(v, list):
                            entity_values.extend(str(item) for item in v)
                        else:
                            entity_values.append(str(v))
                    query_entities = {e.lower() for e in entity_values}

                    def _tag_priority(
                        tag: str, _entities: set[str] = query_entities
                    ) -> tuple[int, str]:
                        return (0 if tag.lower() in _entities else 1, tag.lower())

                    tags = sorted(unique_tags, key=_tag_priority)[:5]
                else:
                    tags = []
            else:
                tags = []

            cards.append(
                ResultCard(
                    rank=rank,
                    session_id=session_id,
                    title=title,
                    project_name=project_name,
                    match_score=score,
                    relevance_explanation="",
                    quality_badge=quality_badge,
                    supersession_note="",
                    time_ago=time_ago,
                    duration=duration,
                    files_summary=files_summary,
                    excerpt=excerpt,
                    tags=tags,
                    fork_command=f"smartfork fork {session_id}",
                )
            )
        return cards
