"""SearchOrchestrator — QueryInterpreter → DeterministicSearchEngine → (deep synthesis)."""

from typing import Any

from loguru import logger

from smartfork.models.query import QueryInterpretation
from smartfork.models.search import ResultCard
from smartfork.search.deterministic import DeterministicSearchEngine
from smartfork.search.query_interpreter import QueryInterpreter


class SearchOrchestrator:
    """Wires QueryInterpreter → DeterministicSearchEngine → optional deep synthesis."""

    def __init__(
        self,
        embedder: Any | None = None,
        metadata_store: Any | None = None,
        llm: Any | None = None,
        use_fast: bool = False,
        use_deep: bool = False,
    ) -> None:
        """Initialize with embedder, metadata store, and optional LLM.

        Args:
            embedder: Embedding model for vector search.
            metadata_store: Metadata store for session data and FTS5.
            llm: Optional LLM provider for query interpretation and synthesis.
            use_fast: Skip all LLM calls and use deterministic search directly.
            use_deep: Force deep mode (multi-session synthesis).
        """
        self.embedder = embedder
        self.store = metadata_store
        self.llm = llm
        self.use_fast = use_fast
        self.use_deep = use_deep
        self.interpreter = QueryInterpreter(llm=llm) if llm else None
        self.engine = DeterministicSearchEngine(
            embedder=embedder, metadata_store=metadata_store
        )
        self.last_empty_reasoning: str = ""

    def search(
        self,
        query: str,
        top_k: int = 5,
        project_filter: str | None = None,
        quality_filter: str | None = None,
    ) -> list[ResultCard]:
        """Execute the search pipeline.

        Flow:
          Fast mode:  DeterministicSearchEngine.search() directly (0 LLM calls).
          Default:    QueryInterpreter.interpret() → DeterministicSearchEngine.search()
                      (1 LLM call + deterministic search).
          Deep mode:  Same as default + SessionGraphEngine + MultiSessionSynthesizer
                      (2 LLM calls total).

        Args:
            query: Raw user search query.
            top_k: Number of top results to return.
            project_filter: Optional project name filter.
            quality_filter: Optional quality tag filter.

        Returns:
            List of ResultCard objects, sliced to at most top_k.
        """
        self.last_empty_reasoning = ""

        # ── Fast mode: 0 LLM calls ──────────────────────────────────────────
        if self.use_fast:
            print("Fast search...")
            try:
                return self.engine.search(query, top_k, project_filter, quality_filter)
            except Exception as e:
                logger.warning(f"Fast search failed: {e}")
                return []

        # ── Interpret query (1 LLM call) ────────────────────────────────────
        print("Interpreting query...")
        qi: QueryInterpretation
        try:
            if self.interpreter is not None:
                qi = self.interpreter.interpret(query, deep_mode=self.use_deep)
            else:
                qi = QueryInterpreter(llm=None).interpret(query, deep_mode=self.use_deep)
        except Exception as e:
            logger.warning(f"QueryInterpreter failed: {e}. Using deterministic fallback.")
            qi = QueryInterpreter(llm=None).interpret(query, deep_mode=self.use_deep)

        # ── Deterministic search (0 LLM calls) ──────────────────────────────
        print("Searching...")
        search_query = qi.expanded_query or qi.original_query or query
        try:
            results = self.engine.search(
                search_query, top_k, project_filter, quality_filter
            )
        except Exception as e:
            logger.warning(f"Deterministic search failed: {e}")
            return []

        if not results:
            self.last_empty_reasoning = f"No results for expanded query: {search_query}"
            return []

        # ── Deep mode: multi-session path (1 more LLM call) ─────────────────
        if qi.needs_deep_mode or self.use_deep:
            print("Deep synthesis...")
            # TODO(SessionGraphEngine + MultiSessionSynthesizer — US-026, US-027)
            # For now: annotate results with deep-mode marker.
            try:
                results = self._deep_synthesis(results, qi, query)
            except Exception as e:
                logger.warning(f"Deep synthesis failed: {e}. Returning results without narrative.")

        return results[:top_k]

    def _deep_synthesis(
        self,
        results: list[ResultCard],
        interpretation: QueryInterpretation,
        original_query: str,
    ) -> list[ResultCard]:
        """Placeholder for deep multi-session synthesis.

        When SessionGraphEngine and MultiSessionSynthesizer land, this method
        will be replaced with real graph traversal + LLM narrative generation.
        """
        for card in results:
            if not card.relevance_explanation:
                card.relevance_explanation = (
                    "Deep mode: multi-session analysis requested."
                )
        return results
