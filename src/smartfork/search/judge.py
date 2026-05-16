"""Batch judge agent for SmartFork v2.

Reads selected content of candidates and drops false positives using structured
LLM judgment.
"""

from typing import Any

from loguru import logger

from smartfork.models.search import BatchJudgeResult, JudgeOutput, QueryDecomposition
from smartfork.providers.protocols import LLMProvider
from smartfork.search.reranker import _extract_keywords

_MAX_CONTENT_LENGTH = 1000
_BATCH_SIZE = 5
_TOP_N = 5

_JUDGE_PROMPT_TEMPLATE = (
    "You are a relevance judge for a developer session search system.\n\n"
    "ORIGINAL QUERY: {query}\n"
    "CORE GOAL: {core_goal}\n"
    "INTENT CLASSIFICATION: {intent}\n\n"
    "Below are candidate coding sessions. For each candidate, read the provided "
    "content carefully and determine:\n"
    "- relevance_score: float from 0.0 to 1.0\n"
    "- matches_query: bool (True only if the session is genuinely relevant)\n"
    "- reason: brief explanation\n"
    "- key_snippet: most relevant excerpt from the content\n\n"
    "CANDIDATES:\n{candidates}\n\n"
    "Return your judgments in the requested structured format."
)


def _flatten_entities(val: Any) -> list[str]:
    """Extract lowercase strings from an entity value (str or list)."""
    if isinstance(val, str):
        return [val.lower()]
    if isinstance(val, list):
        result: list[str] = []
        for item in val:
            result.extend(_flatten_entities(item))
        return result
    return []


def _build_keywords(query: str, qd: QueryDecomposition) -> list[str]:
    """Build a deduplicated keyword list from the query and decomposition entities."""
    keywords = _extract_keywords(query)
    for val in qd.entities.values():
        keywords.extend(_flatten_entities(val))

    seen: set[str] = set()
    unique: list[str] = []
    for kw in keywords:
        lower = kw.lower()
        if lower not in seen:
            seen.add(lower)
            unique.append(lower)
    return unique


def _select_content(candidate: dict[str, Any], keywords: list[str]) -> list[str]:
    """Select matching reasoning docs and files, or fall back to first 3 truncated docs."""
    reasoning_docs = candidate.get("reasoning_docs", []) or []
    files_edited = candidate.get("files_edited", []) or []

    matched: list[str] = []

    for doc in reasoning_docs:
        if any(kw in doc.lower() for kw in keywords):
            matched.append(doc)
        if len(matched) >= 3:
            return matched

    for f in files_edited:
        if any(kw in f.lower() for kw in keywords):
            matched.append(f)
        if len(matched) >= 3:
            return matched

    # Supplement with first reasoning_docs up to 3 total, truncated
    for doc in reasoning_docs:
        if doc not in matched:
            matched.append(doc[:_MAX_CONTENT_LENGTH])
        if len(matched) >= 3:
            break

    return matched


def _build_candidate_text(candidate: dict[str, Any], keywords: list[str]) -> str:
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

    content_items = _select_content(candidate, keywords)
    for i, item in enumerate(content_items, 1):
        lines.append(f"Content {i}: {item}")

    lines.append("")
    return "\n".join(lines)


def _build_batch_prompt(
    candidates: list[dict[str, Any]], query: str, qd: QueryDecomposition
) -> str:
    """Build the full prompt for a batch of candidates."""
    keywords = _build_keywords(query, qd)
    candidate_texts = [_build_candidate_text(c, keywords) for c in candidates]
    return _JUDGE_PROMPT_TEMPLATE.format(
        query=query,
        core_goal=qd.core_goal,
        intent=qd.intent,
        candidates="\n".join(candidate_texts),
    )


class BatchJudgeAgent:
    """LLM-based batch judge that reads candidate content and drops false positives."""

    def __init__(self, llm: LLMProvider) -> None:
        """Initialize with an LLM provider.

        Args:
            llm: An LLMProvider that supports complete_structured().
        """
        self.llm = llm

    def judge(
        self,
        candidates: list[dict[str, Any]],
        query: str,
        qd: QueryDecomposition,
        top_n: int = 5,
    ) -> list[JudgeOutput]:
        """Judge candidates and drop false positives.

        Processes candidates in batches of 5. Falls back to deterministic
        match_score sorting if the LLM fails.

        Args:
            candidates: List of candidate dicts from the retriever.
            query: The original user search query.
            qd: Structured query decomposition.
            top_n: Number of top results to return after judging.

        Returns:
            List of JudgeOutput for candidates that match_query=True,
            sorted by relevance_score descending, top top_n.
        """
        if not candidates:
            return []

        candidate_map: dict[str, dict[str, Any]] = {
            c["session_id"]: c for c in candidates if "session_id" in c
        }

        if not candidate_map:
            logger.warning("No valid candidates with session_id found for judging")
            return []

        all_judgments: list[JudgeOutput] = []
        candidate_list = list(candidate_map.values())

        for i in range(0, len(candidate_list), _BATCH_SIZE):
            batch = candidate_list[i : i + _BATCH_SIZE]
            prompt = _build_batch_prompt(batch, query, qd)
            try:
                result = self.llm.complete_structured(
                    prompt=prompt,
                    output_schema=BatchJudgeResult,
                    max_tokens=1200,
                    temperature=0.1,
                )
                if isinstance(result, BatchJudgeResult) and result.judgments:
                    all_judgments.extend(result.judgments)
                else:
                    logger.warning(
                        f"Batch {i // _BATCH_SIZE + 1}: invalid or empty "
                        "structured response from LLM"
                    )
            except Exception as e:
                logger.warning(f"Batch {i // _BATCH_SIZE + 1}: LLM judging failed: {e}")

        if not all_judgments:
            logger.warning(
                "LLM judging produced no valid results; "
                "falling back to deterministic scores"
            )
            fallback = [
                JudgeOutput(
                    session_id=sid,
                    relevance_score=c.get("match_score", 0.0),
                    matches_query=True,
                    reason="",
                    key_snippet="",
                )
                for sid, c in candidate_map.items()
            ]
            fallback.sort(key=lambda j: j.relevance_score, reverse=True)
            return fallback

        valid: list[JudgeOutput] = []
        seen: set[str] = set()
        for judgment in all_judgments:
            sid = judgment.session_id
            if sid in seen:
                continue
            seen.add(sid)
            if not judgment.matches_query:
                continue
            if sid not in candidate_map:
                logger.warning(
                    f"LLM returned unknown session_id in judge response: {sid}"
                )
                continue
            valid.append(judgment)

        valid.sort(key=lambda j: j.relevance_score, reverse=True)
        return valid[:top_n]
