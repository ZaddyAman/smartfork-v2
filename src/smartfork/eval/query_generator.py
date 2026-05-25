"""Generate synthetic search queries from session content."""

from __future__ import annotations

import json
from typing import Any, cast

from loguru import logger

from smartfork.models.evaluation import EvalQueryBatch, GeneratedQuery

__all__ = ["GeneratedQuery", "QueryGenerator", "_build_heuristic_query"]

PROMPT_TEMPLATE = """You are a developer using a session search tool.
Generate 3 natural search queries from this session that the developer might type:

Session task: {task_raw}
Summary: {summary_doc}
Tech tags: {tech_tags}
Domains: {domains}
Files edited: {files_edited}

Generate exactly 3 queries:
1. specific: rich with keywords, 8-15 words, specific technical terms
2. short: 1-3 words, terse, what someone types quickly
3. vague: natural language, indirect, no obvious tech keywords,
   developer remembers the feeling not the tech

Return JSON object: {"queries": [{"query": str, "query_type": str, "source_session_id": str}]}.
"""


def _coerce_str_list(value: Any) -> list[str]:
    """Return a clean string list from JSON text or loose store values."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = [value] if value else []
        return [str(item) for item in decoded if item] if isinstance(decoded, list) else []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def _build_heuristic_query(session: dict[str, Any], query_type: str) -> str:
    """Build a fallback query when LLM is unavailable."""
    domains = _coerce_str_list(session.get("domains", []))
    tech_tags = _coerce_str_list(session.get("tech_tags", []))
    task = str(session.get("task_raw", ""))

    if query_type == "short":
        keywords = [t for t in tech_tags[:2] if t]
        if not keywords and domains:
            keywords = [domains[0]]
        return " ".join(keywords) or "session"

    if query_type == "vague":
        if "error" in task.lower() or "bug" in task.lower() or "fix" in task.lower():
            return "that error I was dealing with"
        if "implement" in task.lower() or "build" in task.lower():
            return "that thing I was building"
        if "config" in task.lower() or "setup" in task.lower():
            return "that configuration issue"
        return "that thing I was working on"

    # specific — default
    parts = [task[:100]] if task else []
    if tech_tags:
        parts.append(", ".join(tech_tags[:3]))
    query = " ".join(parts)
    return query[:200]


class QueryGenerator:
    """Generates synthetic queries from session content using an LLM."""

    def __init__(self, llm: Any | None = None) -> None:
        """Initialize with optional LLM.

        Args:
            llm: LLM provider with ``complete_structured`` method.
                  Falls back to heuristic if None.
        """
        self.llm = llm

    def generate(self, session: dict[str, Any]) -> list[GeneratedQuery]:
        """Generate 3 synthetic queries for a session.

        Args:
            session: Session dict from MetadataStore.get_session().

        Returns:
            List of 3 GeneratedQuery objects.
        """
        session_id = str(session.get("session_id", ""))

        if self.llm is None:
            logger.debug("No LLM available, using heuristic query generation.")
            return [
                GeneratedQuery(
                    query=_build_heuristic_query(session, "specific"),
                    query_type="specific",
                    source_session_id=session_id,
                ),
                GeneratedQuery(
                    query=_build_heuristic_query(session, "short"),
                    query_type="short",
                    source_session_id=session_id,
                ),
                GeneratedQuery(
                    query=_build_heuristic_query(session, "vague"),
                    query_type="vague",
                    source_session_id=session_id,
                ),
            ]

        prompt = PROMPT_TEMPLATE.format(
            task_raw=str(session.get("task_raw", ""))[:500],
            summary_doc=str(session.get("summary_doc", ""))[:500],
            tech_tags=", ".join(_coerce_str_list(session.get("tech_tags", []))),
            domains=", ".join(_coerce_str_list(session.get("domains", []))),
            files_edited=", ".join(_coerce_str_list(session.get("files_edited", []))[:5]),
        )

        try:
            batch = cast(
                EvalQueryBatch,
                self.llm.complete_structured(
                    prompt=prompt,
                    output_schema=EvalQueryBatch,
                    max_tokens=800,
                    temperature=0.5,
                ),
            )
            for q in batch.queries:
                q.source_session_id = session_id
            by_type = {q.query_type: q for q in batch.queries}
            if {"specific", "short", "vague"}.issubset(by_type):
                return [by_type["specific"], by_type["short"], by_type["vague"]]
            raise ValueError("LLM did not return all required query types")
        except Exception as exc:
            logger.warning(f"LLM query generation failed ({exc}), using heuristic.")
            return [
                GeneratedQuery(
                    query=_build_heuristic_query(session, "specific"),
                    query_type="specific",
                    source_session_id=session_id,
                ),
                GeneratedQuery(
                    query=_build_heuristic_query(session, "short"),
                    query_type="short",
                    source_session_id=session_id,
                ),
                GeneratedQuery(
                    query=_build_heuristic_query(session, "vague"),
                    query_type="vague",
                    source_session_id=session_id,
                ),
            ]
