"""Multi-session synthesizer for SmartFork v2.

Uses 1 structured LLM call to generate a human-readable narrative,
timeline, and fork suggestion from grouped session chains.
"""

from datetime import datetime
from typing import Any

from loguru import logger

from smartfork.models.relationship import Chain, TimelineEntry, TimelineSummary
from smartfork.models.session import QualityTag


class MultiSessionSynthesizer:
    """Synthesizes multi-session narratives and timelines."""

    def __init__(self, llm: object | None = None) -> None:
        self.llm = llm

    def synthesize_timeline(
        self,
        query: str,
        chains: list[Chain],
    ) -> TimelineSummary:
        """Generate a timeline summary from session chains.

        If an LLM is available, makes a single structured call to generate a
        human-readable narrative.  Structural fields (timeline,
        suggested_fork_session_id, resolution_status) are always derived
        deterministically so the output is robust to LLM failures.

        Args:
            query: The user's original query.
            chains: List of related session chains.

        Returns:
            TimelineSummary with narrative, timeline, and suggestions.
        """
        if not chains:
            return TimelineSummary(
                narrative="No related sessions found.",
                timeline=[],
                suggested_fork_session_id="",
                resolution_status="unknown",
            )

        primary_chain = chains[0]
        timeline = self._build_timeline(primary_chain)
        suggested_fork = self._get_latest_session_id(primary_chain)
        deterministic_status = self._determine_resolution_status(primary_chain)

        if self.llm:
            try:
                llm_summary = self._call_llm(query, chains)
                llm_summary.timeline = timeline
                llm_summary.suggested_fork_session_id = suggested_fork
                if llm_summary.resolution_status not in {
                    "solved",
                    "ongoing",
                    "dead_end",
                    "mixed",
                }:
                    llm_summary.resolution_status = deterministic_status
                return llm_summary
            except Exception as e:
                logger.error(f"Multi-session synthesis LLM call failed: {e}")

        fallback_narrative = self._build_fallback_narrative(query, chains)
        return TimelineSummary(
            narrative=fallback_narrative,
            timeline=timeline,
            suggested_fork_session_id=suggested_fork,
            resolution_status=deterministic_status,
        )

    def _call_llm(self, query: str, chains: list[Chain]) -> TimelineSummary:
        """Make the structured LLM call and normalise the response."""
        assert self.llm is not None
        chain_text = self._format_chains_for_prompt(chains)
        prompt = (
            "Summarize this developer's work journey based on their coding sessions.\n\n"
            f'User query: "{query}"\n\n'
            f"Session chains:\n{chain_text}\n\n"
            "Return structured data with these fields:\n"
            '  narrative: 2-3 paragraph human-readable summary of the journey\n'
            '  resolution_status: one of "solved", "ongoing", "dead_end", "mixed"\n'
            '  suggested_fork_session_id: session_id of the latest relevant session\n\n'
            "Rules:\n"
            "- narrative: Tell the story chronologically. What was attempted, "
            "what succeeded, what's the current status.\n"
            '- resolution_status: "solved" if latest session has solution_found, '
            '"ongoing" if partial, "dead_end" if all dead_end, "mixed" otherwise.\n'
            "- suggested_fork_session_id: Recommend the most recent session in the "
            "most relevant chain.\n"
        )

        if hasattr(self.llm, "complete_structured"):
            result: Any = self.llm.complete_structured(
                prompt=prompt,
                output_schema=TimelineSummary,
                max_tokens=800,
                temperature=0.3,
            )
            if isinstance(result, TimelineSummary):
                return result
            if isinstance(result, dict):
                return self._dict_to_timeline_summary(result)
            # Unexpected type — try to parse as text
            return self._parse_text_timeline_summary(str(result))

        # Fallback to plain text completion if structured is unavailable
        text_result = self.llm.complete(  # type: ignore[attr-defined]
            prompt, max_tokens=800, temperature=0.3
        )
        return self._parse_text_timeline_summary(str(text_result))

    @staticmethod
    def _dict_to_timeline_summary(data: dict[str, Any]) -> TimelineSummary:
        status = data.get("resolution_status", "unknown")
        if status not in {"solved", "ongoing", "dead_end", "mixed", "unknown"}:
            status = "unknown"
        return TimelineSummary(
            narrative=data.get("narrative", ""),
            timeline=[],  # populated later by the caller
            suggested_fork_session_id=data.get("suggested_fork_session_id", ""),
            resolution_status=status,
        )

    @staticmethod
    def _parse_text_timeline_summary(text: str) -> TimelineSummary:
        import json

        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                return MultiSessionSynthesizer._dict_to_timeline_summary(data)
        except (json.JSONDecodeError, ValueError):
            pass
        return TimelineSummary(
            narrative="",
            timeline=[],
            suggested_fork_session_id="",
            resolution_status="unknown",
        )

    @staticmethod
    def _build_timeline(chain: Chain) -> list[TimelineEntry]:
        """Build structured timeline entries from a chain."""
        timeline: list[TimelineEntry] = []
        sessions = chain.sessions
        for i, session in enumerate(sessions):
            relationship_to_next = None
            if i < len(sessions) - 1:
                relationship_to_next = "continued_in"

            task = session.task_raw
            if len(task) > 80:
                task = task[:77] + "..."

            summary = session.summary_doc
            if len(summary) > 200:
                summary = summary[:197] + "..."

            entry = TimelineEntry(
                session_id=session.session_id,
                timestamp=session.session_start,
                task=task,
                quality_tag=session.quality_tag,
                summary=summary,
                relationship_to_next=relationship_to_next,
            )
            timeline.append(entry)
        return timeline

    @staticmethod
    def _get_latest_session_id(chain: Chain) -> str:
        """Return the session_id of the most recent session in a chain."""
        if not chain.sessions:
            return ""
        latest = max(chain.sessions, key=lambda s: s.session_start)
        return latest.session_id

    @staticmethod
    def _determine_resolution_status(chain: Chain) -> str:
        """Derive resolution status from the quality tags in a chain."""
        if not chain.sessions:
            return "unknown"
        tags = [s.quality_tag for s in chain.sessions]
        latest_tag = tags[-1]
        if latest_tag == QualityTag.SOLUTION_FOUND:
            return "solved"
        if latest_tag == QualityTag.PARTIAL:
            return "ongoing"
        if all(t == QualityTag.DEAD_END for t in tags):
            return "dead_end"
        return "mixed"

    def _format_chains_for_prompt(self, chains: list[Chain]) -> str:
        """Format chains into a human-readable block for the LLM prompt."""
        lines: list[str] = []
        for i, chain in enumerate(chains, 1):
            lines.append(f"\nChain {i}:")
            for j, session in enumerate(chain.sessions, 1):
                date = self._format_date(session.session_start)
                quality = (
                    session.quality_tag.value
                    if hasattr(session.quality_tag, "value")
                    else str(session.quality_tag)
                )
                task_display = session.task_raw[:80]
                lines.append(f"  {j}. [{date}] {task_display} (quality: {quality})")
                if session.summary_doc:
                    lines.append(f"     Summary: {session.summary_doc[:150]}")
        return "\n".join(lines)

    @staticmethod
    def _format_date(timestamp: int) -> str:
        """Format a millisecond timestamp as YYYY-MM-DD."""
        if timestamp <= 0:
            return "unknown"
        return datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")

    def _build_fallback_narrative(self, query: str, chains: list[Chain]) -> str:
        """Build a plain listing of chain entries when the LLM is unavailable."""
        lines: list[str] = [f'Query: "{query}"', "Related session chains:"]
        for i, chain in enumerate(chains, 1):
            lines.append(f"\nChain {i}:")
            for session in chain.sessions:
                date = self._format_date(session.session_start)
                quality = (
                    session.quality_tag.value
                    if hasattr(session.quality_tag, "value")
                    else str(session.quality_tag)
                )
                task_display = session.task_raw[:80]
                lines.append(
                    f"  - [{date}] {session.session_id}: {task_display} "
                    f"(quality: {quality})"
                )
        return "\n".join(lines)
