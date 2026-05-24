"""Deterministic search engine (Path A) for SmartFork v2."""

import string
import time
from typing import Any

from loguru import logger

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
    """Deterministic search: embed -> vector + FTS5 -> RRF fusion -> rerank -> cards.

    This is the always-available, zero-cost search path. It uses:
    - sqlite-vec for vector search
    - FTS5 BM25 for keyword search
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
        """Perform vector similarity search via sqlite-vec."""
        if not self.embedder or not self.metadata_store:
            return {}

        try:
            query_vec = self.embedder.embed_query(query)
            results = self.metadata_store.vector_search(query_vec, limit=top_k * 3)
            return dict(results)
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
            return {}

    def _bm25_search(self, query: str, top_k: int) -> dict[str, float]:
        """Perform keyword search using persistent FTS5 index via MetadataStore."""
        if not self.metadata_store:
            return {}

        expanded_query = self._build_fts5_query(query)

        try:
            results = self.metadata_store.fts5_search(expanded_query, limit=top_k * 3)
            if not results:
                return {}

            # Normalize BM25 scores (lower is better) to 0-1 (higher is better)
            scores = [score for _, score in results]
            min_score = min(scores)
            max_score = max(scores)
            score_range = max_score - min_score

            normalized: dict[str, float] = {}
            for sid, score in results:
                if score_range > 0:
                    normalized[sid] = (max_score - score) / score_range
                else:
                    normalized[sid] = 1.0

            # Return top-k
            sorted_results = sorted(normalized.items(), key=lambda x: -x[1])
            return dict(sorted_results[:top_k])

        except Exception as e:
            logger.debug(f"FTS5 search failed: {e}")
            return {}

    def _build_fts5_query(self, query: str) -> str:
        """Build an FTS5 MATCH query from keywords using OR groups joined with AND.

        If *query* already contains `` OR `` (e.g. from QueryInterpreter) it is
        treated as a disjunction — top-level groups are joined with OR so that
        any matching term scores.
        """
        stop_words = {
            "the", "a", "an", "is", "was", "in", "on", "at", "to", "for",
            "and", "or", "of", "with", "by", "from", "as", "it", "this",
            "that", "these", "those", "i", "you", "he", "she", "we", "they",
            "me", "my", "our", "us", "them", "their", "his", "her", "its",
            "be", "been", "being", "have", "has", "had", "do", "does", "did",
            "will", "would", "could", "should", "may", "might", "can",
            "what", "which", "who", "when", "where", "why", "how",
            "all", "any", "both", "each", "few", "more", "most", "other",
            "some", "such", "no", "nor", "not", "only", "own", "same", "so",
            "than", "too", "very", "just", "now", "then", "here", "there",
            "up", "down", "out", "off", "over", "under", "again", "further",
            "once", "also", "if", "because", "until", "while", "about",
            "against", "between", "into", "through", "during", "before",
            "after", "above", "below", "am", "are",
        }

        try:
            from smartfork.search.query_interpreter import SYNONYM_MAP
            has_synonyms = True
        except ImportError:
            has_synonyms = False

        # Pre-expanded queries from QueryInterpreter use OR semantics at the top level.
        if " OR " in query:
            raw_terms = [t.strip() for t in query.split(" OR ")]
            groups: list[str] = []
            seen: set[str] = set()
            for term in raw_terms:
                words = [
                    w.strip('"\'').lower()
                    for w in term.split()
                    if w.lower() not in stop_words and len(w.strip('"\'')) > 1
                ]
                for word in words:
                    if word in seen:
                        continue
                    seen.add(word)
                    if has_synonyms and word in SYNONYM_MAP:
                        synonyms = [word] + [s for s in SYNONYM_MAP[word] if s not in seen]
                        seen.update(synonyms)
                        quoted = [f'"{s}"' for s in synonyms]
                        groups.append(f"({' OR '.join(quoted)})")
                    else:
                        groups.append(f'"{word}"')
            return " OR ".join(groups) if groups else query

        # Original short-query path: AND together keyword groups.
        words = [
            w.strip('"\'').lower()
            for w in query.split()
            if w.lower() not in stop_words and len(w.strip('"\'')) > 1
        ]

        if not words:
            return query

        groups = []
        seen = set()

        for word in words:
            if word in seen:
                continue
            seen.add(word)

            if has_synonyms and word in SYNONYM_MAP:
                synonyms = [word] + [s for s in SYNONYM_MAP[word] if s not in seen]
                seen.update(synonyms)
                quoted = [f'"{s}"' for s in synonyms]
                groups.append(f"({' OR '.join(quoted)})")
            else:
                groups.append(f'"{word}"')

        return " AND ".join(groups)

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

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract lowercase keywords from query text."""
        translator = str.maketrans("", "", string.punctuation)
        cleaned = text.lower().translate(translator)
        stop_words = {
            "the", "a", "an", "is", "was", "in", "on", "at", "to", "for",
            "and", "or", "of", "with", "by", "from", "as", "it", "this",
            "that", "these", "those", "i", "you", "he", "she", "we", "they",
            "me", "my", "our", "us", "them", "their", "his", "her", "its",
            "be", "been", "being", "have", "has", "had", "do", "does", "did",
            "will", "would", "could", "should", "may", "might", "can",
            "what", "which", "who", "when", "where", "why", "how",
            "all", "any", "both", "each", "few", "more", "most", "other",
            "some", "such", "no", "nor", "not", "only", "own", "same", "so",
            "than", "too", "very", "just", "now", "then", "here", "there",
            "up", "down", "out", "off", "over", "under", "again", "further",
            "once", "also", "if", "because", "until", "while", "about",
            "against", "between", "into", "through", "during", "before",
            "after", "above", "below", "am", "are",
        }
        return [w for w in cleaned.split() if w not in stop_words and len(w) > 2]

    def _rerank(
        self, results: dict[str, float], decomposition: QueryDecomposition
    ) -> list[tuple[str, float]]:
        """Multi-signal reranker.

        Weights: semantic 45%, file_overlap 20%, keyword_density 15%,
        quality 10%, recency 5%, code_preference 5% = 100%.
        Relationship boost: +0.15 if latest_in_chain, ×0.70 if superseded.
        """
        query_keywords = self._extract_keywords(decomposition.core_goal)
        reranked: list[tuple[str, float]] = []

        for session_id, base_score in results.items():
            final_score = base_score * 0.45

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

                    # File overlap (20%)
                    if query_keywords:
                        files_edited = self.metadata_store._deserialize_list(
                            session.get("files_edited", "[]")
                        )
                        overlap = sum(
                            1
                            for kw in query_keywords
                            if any(kw in f.lower() for f in files_edited)
                        )
                        final_score += 0.20 * (overlap / len(query_keywords))

                    # Keyword density (15%)
                    if query_keywords:
                        text = " ".join([
                            session.get("task_raw", ""),
                            session.get("summary_doc", ""),
                        ]).lower()
                        matches = sum(1 for kw in query_keywords if kw in text)
                        final_score += 0.15 * (matches / len(query_keywords))

                    # Relationship boost
                    superseding = self.metadata_store.get_superseding_sessions(
                        session_id
                    )
                    if superseding:
                        final_score *= 0.70
                    else:
                        superseded = self.metadata_store.get_superseded_sessions(
                            session_id
                        )
                        if superseded:
                            final_score += 0.15

            # Code preference bonus (5%)
            if decomposition.prefer_code:
                final_score += 0.05

            reranked.append((session_id, min(final_score, 1.0)))

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
