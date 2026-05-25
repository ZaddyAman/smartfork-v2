"""LLM-as-Judge relevance scoring for eval runs."""

from __future__ import annotations

import json
from typing import Any, cast

from loguru import logger

from smartfork.models.evaluation import EvalBatchJudgeOutput, EvalJudgeOutput

JudgeOutput = EvalJudgeOutput


PROMPT_TEMPLATE = """You are evaluating search result relevance.

QUERY: {query}

SESSION CONTENT:
Task: {task_raw}
Summary: {summary_doc}
Files edited: {files_edited}
Domains: {domains}
Tech tags: {tech_tags}
Quality: {quality_tag}
Duration: {duration} minutes

Score how relevant this session is to the query:
- 3: Directly relevant - the session is about exactly what the query asks
- 2: Partially relevant - addresses part of the query or closely related topic
- 1: Tangentially related - same project/tech area but not what the query asks
- 0: Irrelevant - no meaningful connection to the query

Respond with JSON: {{"score": int, "reason": str}}
"""

BATCH_PROMPT_TEMPLATE = """You are evaluating search result relevance.

QUERY: {query}

SESSION RESULTS:
{session_blocks}

Score each session result in order:
- 3: Directly relevant - the session is about exactly what the query asks
- 2: Partially relevant - addresses part of the query or closely related topic
- 1: Tangentially related - same project/tech area but not what the query asks
- 0: Irrelevant - no meaningful connection to the query

Respond with JSON: {{"judgments": [{{"score": int, "reason": str}}]}}
Return exactly {count} judgments in the same order.
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


def _session_prompt_fields(session: dict[str, Any]) -> dict[str, str]:
    """Build bounded, string-only prompt fields from a session dictionary."""
    return {
        "task_raw": str(session.get("task_raw", ""))[:600],
        "summary_doc": str(session.get("summary_doc", ""))[:600],
        "files_edited": ", ".join(_coerce_str_list(session.get("files_edited", []))[:10]),
        "domains": ", ".join(_coerce_str_list(session.get("domains", []))),
        "tech_tags": ", ".join(_coerce_str_list(session.get("tech_tags", []))),
        "quality_tag": str(session.get("quality_tag", "unknown")),
        "duration": str(session.get("duration_minutes", 0.0)),
    }


class RelevanceJudge:
    """Judge relevance of search results using an LLM."""

    def __init__(self, llm: Any | None = None) -> None:
        """Initialize with an optional LLM provider."""
        self.llm = llm

    def judge(self, query: str, session: dict[str, Any]) -> JudgeOutput:
        """Score a single query/session pair."""
        if self.llm is None:
            logger.warning("No LLM available for judging; returning neutral score.")
            return JudgeOutput(score=1, reason="No LLM available for judging")

        prompt = PROMPT_TEMPLATE.format(query=query, **_session_prompt_fields(session))

        try:
            return cast(
                JudgeOutput,
                self.llm.complete_structured(
                    prompt=prompt,
                    output_schema=JudgeOutput,
                    max_tokens=200,
                    temperature=0.1,
                ),
            )
        except Exception as exc:
            logger.warning(f"LLM judge failed ({exc}); returning neutral score.")
            return JudgeOutput(score=1, reason=f"Judge error: {exc}")

    def judge_batch(
        self,
        query: str,
        sessions: list[dict[str, Any]],
    ) -> list[JudgeOutput]:
        """Judge multiple sessions for the same query."""
        if self.llm is None:
            return [self.judge(query, sess) for sess in sessions]

        session_blocks = "\n\n".join(
            self._format_session_block(index, session)
            for index, session in enumerate(sessions, start=1)
        )
        prompt = BATCH_PROMPT_TEMPLATE.format(
            query=query,
            session_blocks=session_blocks,
            count=len(sessions),
        )

        try:
            batch = cast(
                EvalBatchJudgeOutput,
                self.llm.complete_structured(
                    prompt=prompt,
                    output_schema=EvalBatchJudgeOutput,
                    max_tokens=500,
                    temperature=0.1,
                ),
            )
            if len(batch.judgments) == len(sessions):
                return batch.judgments
            raise ValueError("LLM returned the wrong number of judgments")
        except Exception as exc:
            logger.warning(f"Batch judge failed ({exc}); falling back to per-result judging.")
            return [self.judge(query, sess) for sess in sessions]

    @staticmethod
    def _format_session_block(index: int, session: dict[str, Any]) -> str:
        fields = _session_prompt_fields(session)
        return (
            f"Result {index}\n"
            f"Task: {fields['task_raw']}\n"
            f"Summary: {fields['summary_doc']}\n"
            f"Files edited: {fields['files_edited']}\n"
            f"Domains: {fields['domains']}\n"
            f"Tech tags: {fields['tech_tags']}\n"
            f"Quality: {fields['quality_tag']}\n"
            f"Duration: {fields['duration']} minutes"
        )
