"""SearchOrchestrator that wires all search stages into a pipeline."""

from typing import Any

from loguru import logger

from smartfork.models.search import JudgeOutput, QueryDecomposition, ResultCard
from smartfork.search.decomposer import QueryDecomposer
from smartfork.search.judge import BatchJudgeAgent
from smartfork.search.parallel_retriever import ParallelRetriever
from smartfork.search.reranker import RerankerAgent
from smartfork.search.synthesis import SynthesisAgent


class SearchOrchestrator:
    """Wires decomposer → retriever → reranker → judge → synthesis into a pipeline."""

    def __init__(
        self,
        decomposer: QueryDecomposer,
        retriever: ParallelRetriever,
        reranker: RerankerAgent,
        judge: BatchJudgeAgent,
        synthesis: SynthesisAgent,
    ) -> None:
        """Initialize with all pipeline stage dependencies.

        Args:
            decomposer: LLM-based query decomposer.
            retriever: Parallel deterministic search retriever.
            reranker: LLM-based candidate reranker.
            judge: LLM-based relevance judge.
            synthesis: Deterministic ResultCard formatter.
        """
        self.decomposer = decomposer
        self.retriever = retriever
        self.reranker = reranker
        self.judge = judge
        self.synthesis = synthesis
        self.last_empty_reasoning: str = ""

    def _build_empty_reasoning(self) -> str:
        """Build a human-readable explanation for why no results were returned."""
        rejected = getattr(self.judge, "rejected_judgments", [])
        if not rejected:
            return ""
        reasons: list[str] = []
        for j in rejected[:3]:
            if j.reason:
                reasons.append(f"{j.session_id}: {j.reason}")
        if reasons:
            return f"Reviewed {len(rejected)} candidates but none matched. " + "; ".join(reasons)
        return f"Reviewed {len(rejected)} candidates but none matched your query."

    def search(
        self,
        query: str,
        top_k: int = 5,
        project_filter: str | None = None,
        quality_filter: str | None = None,
    ) -> list[ResultCard]:
        """Execute the 5-stage search pipeline.

        Args:
            query: Raw user search query.
            top_k: Number of top results to return.
            project_filter: Optional project name filter.
            quality_filter: Optional quality tag filter.

        Returns:
            List of ResultCard objects, sliced to at most top_k.
        """
        self.last_empty_reasoning = ""

        # Stage 1: Decompose
        print("Decomposing query...")
        try:
            qd = self.decomposer.decompose(query)
        except Exception as e:
            logger.warning(f"Decomposer failed: {e}")
            qd = QueryDecomposition(core_goal=query, search_variants=[query])

        # Stage 2: Retrieve
        variant_count = len(qd.search_variants) if qd.search_variants else 0
        print(f"Searching {variant_count} variants...")
        try:
            candidates = self.retriever.retrieve(
                qd,
                top_k=top_k,
                project_filter=project_filter,
                quality_filter=quality_filter,
            )
        except Exception as e:
            logger.warning(f"Retriever failed: {e}")
            candidates = []

        if not candidates:
            return []

        # Stage 3: Rerank
        print(f"Reranking {len(candidates)} candidates...")
        try:
            reranked = self.reranker.rerank(
                candidates,
                query,
                top_n=max(top_k * 3, 15),
            )
        except Exception as e:
            logger.warning(f"Reranker failed: {e}")
            reranked = sorted(
                candidates,
                key=lambda c: c.get("match_score", 0.0),
                reverse=True,
            )[: max(top_k * 3, 15)]

        if not reranked:
            return []

        # Stage 4: Judge
        print("Judging relevance...")
        try:
            judgments = self.judge.judge(reranked, query, qd, top_n=top_k)
        except Exception as e:
            logger.warning(f"Judge failed: {e}")
            return self._build_warning_cards(reranked, top_k)

        if not judgments:
            self.last_empty_reasoning = self._build_empty_reasoning()
            return []

        # Stage 5: Synthesize
        print("Synthesizing results...")
        try:
            cards = self.synthesis.synthesize(judgments, reranked, qd)
        except Exception as e:
            logger.warning(f"Synthesis failed: {e}")
            cards = self._build_raw_cards(judgments, reranked, top_k)

        return cards[:top_k]

    def _build_warning_cards(
        self,
        candidates: list[dict[str, Any]],
        top_k: int,
    ) -> list[ResultCard]:
        """Build ResultCards with warning badges when the judge fails."""
        cards: list[ResultCard] = []
        for rank, candidate in enumerate(candidates[:top_k], start=1):
            cards.append(
                ResultCard(
                    rank=rank,
                    session_id=candidate.get("session_id", ""),
                    title=candidate.get("title", ""),
                    project_name=candidate.get("project_name", ""),
                    match_score=candidate.get(
                        "relevance_score", candidate.get("match_score", 0.0)
                    ),
                    relevance_explanation="",
                    quality_badge="[yellow]Unverified match[/yellow]",
                    time_ago=candidate.get("time_ago", ""),
                    duration=candidate.get("duration", ""),
                    files_summary=candidate.get("files_summary", ""),
                    excerpt=candidate.get("content", ""),
                    tags=candidate.get("tags", []),
                    fork_command=candidate.get("fork_command", ""),
                )
            )
        return cards

    def _build_raw_cards(
        self,
        judgments: list[JudgeOutput],
        candidates: list[dict[str, Any]],
        top_k: int,
    ) -> list[ResultCard]:
        """Build ResultCards deterministically when synthesis fails."""
        candidate_map: dict[str, dict[str, Any]] = {
            c["session_id"]: c for c in candidates if "session_id" in c
        }
        cards: list[ResultCard] = []
        rank = 1
        for judgment in judgments[:top_k]:
            if judgment.relevance_score < 0.5:
                continue
            candidate = candidate_map.get(judgment.session_id, {})
            badge = (
                "[green]Strong match[/green]"
                if judgment.relevance_score >= 0.8
                else "[yellow]Moderate match[/yellow]"
            )
            cards.append(
                ResultCard(
                    rank=rank,
                    session_id=judgment.session_id,
                    title=candidate.get("title", ""),
                    project_name=candidate.get("project_name", ""),
                    match_score=judgment.relevance_score,
                    relevance_explanation=judgment.reason,
                    quality_badge=badge,
                    time_ago=candidate.get("time_ago", ""),
                    duration=candidate.get("duration", ""),
                    files_summary=candidate.get("files_summary", ""),
                    excerpt=judgment.key_snippet,
                    tags=candidate.get("tags", []),
                    fork_command=candidate.get("fork_command", ""),
                )
            )
            rank += 1
        return cards
