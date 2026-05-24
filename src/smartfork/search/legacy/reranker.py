"""LLM-based reranker agent for SmartFork v2.

Scores retrieved candidates against the original query using structured
LLM output, then re-sorts by relevance_score descending.
"""

from typing import Any

from loguru import logger

from smartfork.models.search import BatchRerankResult, RerankResult
from smartfork.providers.protocols import LLMProvider

# Common English stop words to exclude from keyword extraction
_STOP_WORDS: set[str] = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "is",
    "was",
    "are",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "can",
    "shall",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "i",
    "you",
    "he",
    "she",
    "we",
    "they",
    "me",
    "him",
    "her",
    "us",
    "them",
    "my",
    "your",
    "his",
    "our",
    "their",
    "what",
    "which",
    "who",
    "when",
    "where",
    "why",
    "how",
    "all",
    "any",
    "both",
    "each",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "just",
    "now",
    "then",
    "here",
    "there",
    "up",
    "down",
    "out",
    "off",
    "over",
    "under",
    "again",
    "further",
    "once",
    "about",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "between",
    "among",
    "from",
    "as",
    "if",
    "because",
    "until",
    "while",
    "doing",
    "get",
    "got",
    "getting",
    "make",
    "made",
    "making",
    "take",
    "took",
    "taking",
    "go",
    "went",
    "going",
    "come",
    "came",
    "coming",
    "see",
    "saw",
    "seen",
    "seeing",
    "know",
    "knew",
    "known",
    "knowing",
    "think",
    "thought",
    "thinking",
    "say",
    "said",
    "saying",
    "use",
    "used",
    "using",
    "work",
    "worked",
    "working",
    "try",
    "tried",
    "trying",
    "want",
    "wanted",
    "wanting",
    "need",
    "needed",
    "needing",
    "like",
    "liked",
    "liking",
    "look",
    "looked",
    "looking",
    "find",
    "found",
    "finding",
    "give",
    "gave",
    "given",
    "giving",
    "tell",
    "told",
    "telling",
    "ask",
    "asked",
    "asking",
    "seem",
    "seemed",
    "seeming",
    "feel",
    "felt",
    "feeling",
    "leave",
    "left",
    "leaving",
    "call",
    "called",
    "calling",
    "good",
    "new",
    "first",
    "last",
    "long",
    "great",
    "little",
    "old",
    "right",
    "big",
    "high",
    "different",
    "small",
    "large",
    "next",
    "early",
    "young",
    "important",
    "public",
    "bad",
    "able",
}

_RERANK_PROMPT_TEMPLATE = (
    "You are a relevance scoring assistant for a developer session search system.\n\n"
    "ORIGINAL QUERY: {query}\n\n"
    "Below are candidate coding sessions. For each candidate, evaluate how "
    "relevant it is to the original query. Consider:\n"
    "- Does the session's task or summary directly address the query?\n"
    "- Are the technologies and concepts in the query present?\n"
    "- Is the reasoning content related to the query topic?\n\n"
    "Return a relevance_score between 0.0 (completely irrelevant) and "
    "1.0 (perfectly relevant). Include a brief reason for each score.\n\n"
    "CANDIDATES:\n{candidates}\n\n"
    "Score all candidates and return the results in the requested structured format."
)


def _extract_keywords(query: str) -> list[str]:
    """Extract meaningful keywords from the query for filtering reasoning docs."""
    words: list[str] = []
    for word in query.lower().split():
        cleaned = "".join(ch for ch in word if ch.isalnum())
        if len(cleaned) >= 3 and cleaned not in _STOP_WORDS:
            words.append(cleaned)
    return words


def _filter_reasoning_docs(reasoning_docs: list[str], query: str) -> list[str]:
    """Return reasoning docs that contain query keywords, up to 3."""
    keywords = _extract_keywords(query)
    if not keywords:
        return reasoning_docs[:3]

    filtered: list[str] = []
    for doc in reasoning_docs:
        doc_lower = doc.lower()
        if any(kw in doc_lower for kw in keywords):
            filtered.append(doc)
        if len(filtered) >= 3:
            break
    return filtered


def _build_candidate_text(candidate: dict[str, Any], query: str) -> str:
    """Build a prompt snippet for a single candidate."""
    lines: list[str] = [
        f"--- Candidate {candidate.get('session_id', 'unknown')} ---",
        f"Title: {candidate.get('title', '')}",
    ]

    task_raw = candidate.get("task_raw", "")
    if task_raw:
        lines.append(f"Task: {task_raw}")

    summary_doc = candidate.get("summary_doc", "")
    if summary_doc:
        lines.append(f"Summary: {summary_doc}")

    reasoning_docs = candidate.get("reasoning_docs", [])
    if isinstance(reasoning_docs, list) and reasoning_docs:
        filtered = _filter_reasoning_docs(reasoning_docs, query)
        for i, doc in enumerate(filtered, 1):
            lines.append(f"Reasoning {i}: {doc}")

    lines.append("")
    return "\n".join(lines)


def _build_batch_prompt(candidates: list[dict[str, Any]], query: str) -> str:
    """Build the full prompt for a batch of candidates."""
    candidate_texts = [_build_candidate_text(c, query) for c in candidates]
    return _RERANK_PROMPT_TEMPLATE.format(
        query=query,
        candidates="\n".join(candidate_texts),
    )


class RerankerAgent:
    """LLM-based reranker that scores candidates against the original query."""

    def __init__(self, llm: LLMProvider) -> None:
        """Initialize with an LLM provider.

        Args:
            llm: An LLMProvider that supports complete_structured().
        """
        self.llm = llm

    def rerank(
        self,
        candidates: list[dict[str, Any]],
        query: str,
        top_n: int = 15,
    ) -> list[dict[str, Any]]:
        """Rerank candidates by LLM-evaluated relevance to the query.

        Processes candidates in batches of 5 to stay within token limits.
        Falls back to deterministic match_score sorting if the LLM fails.

        Args:
            candidates: List of candidate dicts from the retriever.
            query: The original user search query.
            top_n: Number of top results to return.

        Returns:
            Re-sorted list of candidate dicts with relevance_score and reason.
        """
        if not candidates:
            return []

        # Map session_id -> original candidate for enrichment
        candidate_map: dict[str, dict[str, Any]] = {
            c["session_id"]: c for c in candidates if "session_id" in c
        }

        if not candidate_map:
            logger.warning("No valid candidates with session_id found for reranking")
            return candidates

        batch_size = 5
        all_rankings: list[RerankResult] = []
        candidate_list = list(candidate_map.values())

        for i in range(0, len(candidate_list), batch_size):
            batch = candidate_list[i : i + batch_size]
            prompt = _build_batch_prompt(batch, query)
            try:
                result = self.llm.complete_structured(
                    prompt=prompt,
                    output_schema=BatchRerankResult,
                    max_tokens=800,
                    temperature=0.1,
                )
                if isinstance(result, BatchRerankResult) and result.rankings:
                    all_rankings.extend(result.rankings)
                else:
                    logger.warning(
                        f"Batch {i // batch_size + 1}: invalid or empty "
                        "structured response from LLM"
                    )
            except Exception as e:
                logger.warning(
                    f"Batch {i // batch_size + 1}: LLM reranking failed: {e}"
                )

        if not all_rankings:
            logger.warning(
                "LLM reranking produced no valid results; "
                "falling back to deterministic match_score sorting"
            )
            return sorted(
                candidates,
                key=lambda c: c.get("match_score", 0.0),
                reverse=True,
            )[:top_n]

        # Attach relevance scores and reasons to candidates
        enriched: list[dict[str, Any]] = []
        seen: set[str] = set()
        for ranking in all_rankings:
            sid = ranking.session_id
            if sid in seen:
                continue
            seen.add(sid)
            if sid not in candidate_map:
                logger.warning(
                    f"LLM returned unknown session_id in rerank response: {sid}"
                )
                continue
            candidate = dict(candidate_map[sid])
            candidate["relevance_score"] = ranking.relevance_score
            candidate["reason"] = ranking.reason
            enriched.append(candidate)

        # Include any candidates that the LLM missed (score 0.0, empty reason)
        for sid, candidate in candidate_map.items():
            if sid not in seen:
                c = dict(candidate)
                c["relevance_score"] = 0.0
                c["reason"] = ""
                enriched.append(c)

        # Sort by relevance_score descending and return top_n
        enriched.sort(key=lambda c: c.get("relevance_score", 0.0), reverse=True)
        return enriched[:top_n]
