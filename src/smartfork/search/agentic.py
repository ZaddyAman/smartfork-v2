"""Agentic search engine (Path B) for SmartFork v2.

PydanticAI orchestrated multi-step search with Smolagents workers.
Fallback to deterministic search when LLM is unavailable.
"""

from typing import Any

from loguru import logger

from smartfork.models.search import (
    QueryDecomposition,
    ResultCard,
)
from smartfork.search.deterministic import DeterministicSearchEngine


class AgenticSearchEngine:
    """LLM-orchestrated multi-step search engine.

    Pipeline: understand → search → evaluate → refine → synthesize
    """

    def __init__(
        self,
        llm: Any | None = None,
        deterministic: DeterministicSearchEngine | None = None,
    ) -> None:
        """Initialize agentic search engine.

        Args:
            llm: Optional LLM provider for agentic path.
            deterministic: Deterministic engine for fallback and workers.
        """
        self.llm = llm
        self.deterministic = deterministic or DeterministicSearchEngine()
        self.max_rounds = 3
        self.relevance_threshold = 6.0

    def search(
        self,
        query: str,
        top_k: int = 10,
        project_filter: str | None = None,
        quality_filter: str | None = None,
    ) -> list[ResultCard]:
        """Execute the full agentic search pipeline.

        Falls back to deterministic search if LLM is unavailable.

        Args:
            query: User search query.
            top_k: Number of results to return.
            project_filter: Optional project name filter.
            quality_filter: Optional quality tag filter.

        Returns:
            List of ResultCard objects with relevance explanations.
        """
        if self.llm is None:
            logger.info("LLM not available, falling back to deterministic search")
            return self.deterministic.search(query, top_k, project_filter, quality_filter)

        # Step 1: Query Understanding
        qd = self._understand_query(query)

        # Step 2: Multi-Variant Parallel Search
        all_results = self._parallel_search(qd, top_k * 2)

        # Step 3: Evaluate
        evaluated = self._evaluate_results(all_results, qd)

        # Step 4: Refine (if needed, max 3 rounds)
        for round_num in range(self.max_rounds):
            if self._any_above_threshold(evaluated):
                break
            if round_num < self.max_rounds - 1:
                new_variants = self._refine_query(query, qd, evaluated, round_num)
                qd.search_variants = new_variants
                more_results = self._parallel_search(qd, top_k)
                all_results = self._deduplicate(all_results + more_results)
                evaluated = self._evaluate_results(all_results, qd)

        # Step 5: Synthesize explanations
        cards = self._synthesize_cards(evaluated[:top_k], qd)

        return cards

    def _understand_query(self, query: str) -> QueryDecomposition:
        """Step 1: Use LLM to understand and decompose the query.

        Args:
            query: User search query.

        Returns:
            Structured QueryDecomposition.
        """
        # Try LLM-based decomposition
        try:
            result = self.llm.complete_structured(  # type: ignore[union-attr]
                f"Analyze this developer search query and provide intent, "
                f"entities, and 3-5 search variants: {query}",
                output_schema=QueryDecomposition,
                max_tokens=200,
                temperature=0.1,
            )
            if isinstance(result, QueryDecomposition):
                return result
        except Exception as e:
            logger.warning(f"LLM query understanding failed: {e}")

        # Fall back to deterministic parser
        from smartfork.search.deterministic import QueryParser

        parser = QueryParser()
        return parser.parse(query)

    def _parallel_search(
        self, qd: QueryDecomposition, top_k: int
    ) -> list[dict[str, Any]]:
        """Step 2: Execute multiple search strategies in parallel.

        Uses ThreadPoolExecutor for concurrent search across variants.

        Args:
            qd: Query decomposition with search variants.
            top_k: Results per variant.

        Returns:
            Combined and deduplicated results.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        all_results: list[dict[str, Any]] = []

        def _search_variant(variant: str) -> list[dict[str, Any]]:
            results: list[dict[str, Any]] = []
            cards = self.deterministic.search(variant, top_k)
            for card in cards:
                results.append({
                    "session_id": card.session_id,
                    "title": card.title,
                    "match_score": card.match_score,
                    "variant": variant,
                })
            return results

        with ThreadPoolExecutor(max_workers=min(5, len(qd.search_variants))) as executor:
            futures = {
                executor.submit(_search_variant, v): v
                for v in qd.search_variants[:5]
            }
            for future in as_completed(futures):
                try:
                    all_results.extend(future.result())
                except Exception as e:
                    logger.warning(f"Search variant failed: {e}")

        return self._deduplicate(all_results)

    def _deduplicate(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deduplicate results by session_id, keeping highest score."""
        seen: dict[str, dict[str, Any]] = {}
        for r in results:
            sid = r["session_id"]
            if sid not in seen or r.get("match_score", 0) > seen[sid].get("match_score", 0):
                seen[sid] = r
        return list(seen.values())

    def _evaluate_results(
        self, results: list[dict[str, Any]], qd: QueryDecomposition
    ) -> list[dict[str, Any]]:
        """Step 3: Evaluate each result's relevance.

        With LLM: reads top candidates, rates relevance 0-10.
        Without LLM: uses match_score as-is.

        Args:
            results: Search results to evaluate.
            qd: Original query decomposition.

        Returns:
            Results with relevance scores added.
        """
        if self.llm:
            try:
                for r in results:
                    prompt = (
                        f"Rate how relevant this session is to the query "
                        f"'{qd.core_goal}' on a scale of 0-10. "
                        f"Session: {r.get('title', 'Unknown')}. "
                        f"Respond with just the number."
                    )
                    response = self.llm.complete(prompt, max_tokens=5)
                    try:
                        r["relevance"] = float(str(response).strip()) / 10.0
                        r["relevance_explanation"] = str(response).strip()
                    except (ValueError, TypeError):
                        r["relevance"] = r.get("match_score", 0.5)
                        r["relevance_explanation"] = ""
            except Exception as e:
                logger.warning(f"LLM evaluation failed: {e}")

        # Fallback: use match_score
        for r in results:
            if "relevance" not in r:
                r["relevance"] = r.get("match_score", 0.5)
                r["relevance_explanation"] = ""

        return sorted(results, key=lambda x: x.get("relevance", 0), reverse=True)

    def _any_above_threshold(self, results: list[dict[str, Any]]) -> bool:
        """Check if any result exceeds the relevance threshold."""
        return any(r.get("relevance", 0) >= (self.relevance_threshold / 10.0) for r in results)

    def _refine_query(
        self,
        query: str,
        qd: QueryDecomposition,
        results: list[dict[str, Any]],
        round_num: int,
    ) -> list[str]:
        """Step 4: Generate new search variants when nothing above threshold.

        Args:
            query: Original query.
            qd: Current decomposition.
            results: Current (low-quality) results.
            round_num: Current refinement round number.

        Returns:
            List of new search variants.
        """
        if self.llm:
            try:
                prompt = (
                    f"The search for '{query}' returned no highly relevant results. "
                    f"Generate 3 alternative search queries that might find better matches. "
                    f"Current results: {[r.get('title') for r in results[:3]]}"
                )
                response = self.llm.complete(prompt, max_tokens=100)
                lines = [
                    line.lstrip("-").lstrip("0123456789. ").strip()
                    for line in str(response).split("\n")
                    if line.strip()
                ]
                variants = lines[:3] if lines else []
                if variants:
                    return variants
            except Exception as e:
                logger.warning(f"LLM refinement failed: {e}")

        # Fallback: broaden the query
        words = query.split()
        return [query, " ".join(words[: len(words) // 2])]

    def _synthesize_cards(
        self, results: list[dict[str, Any]], qd: QueryDecomposition
    ) -> list[ResultCard]:
        """Step 5: Format results with natural language explanations.

        Args:
            results: Evaluated and ranked results.
            qd: Original query decomposition.

        Returns:
            List of ResultCard objects.
        """
        cards: list[ResultCard] = []
        for rank, r in enumerate(results, start=1):
            card = ResultCard(
                rank=rank,
                session_id=r.get("session_id", ""),
                title=r.get("title", "Unknown"),
                project_name=r.get("project_name", ""),
                match_score=r.get("relevance", r.get("match_score", 0)),
                relevance_explanation=r.get("relevance_explanation", ""),
                quality_badge=r.get("quality_badge", ""),
                supersession_note=r.get("supersession_note", ""),
                time_ago=r.get("time_ago", ""),
                duration=r.get("duration", ""),
                files_summary=r.get("files_summary", ""),
                excerpt=r.get("excerpt", ""),
                fork_command=f"smartfork fork {r.get('session_id', '')}",
            )
            cards.append(card)
        return cards
