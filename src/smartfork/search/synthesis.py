"""Synthesis agent for SmartFork v2.

Maps judge outputs and candidate metadata into formatted ResultCards.
No LLM is required — purely deterministic formatting and badge assignment.
"""

from typing import Any

from smartfork.models.search import JudgeOutput, QueryDecomposition, ResultCard


class SynthesisAgent:
    """Format judge outputs into display-ready ResultCards."""

    def synthesize(
        self,
        judgments: list[JudgeOutput],
        candidates: list[dict[str, Any]],
        qd: QueryDecomposition,
    ) -> list[ResultCard]:
        """Build ResultCards from judgments and candidate metadata.

        Args:
            judgments: Ranked judgments from the judge agent.
            candidates: Candidate dicts from the retriever.
            qd: Structured query decomposition (unused, kept for API symmetry).

        Returns:
            List of ResultCard objects for display. Empty if no candidates
            survive the relevance threshold.
        """
        candidate_map: dict[str, dict[str, Any]] = {
            c["session_id"]: c for c in candidates if "session_id" in c
        }

        cards: list[ResultCard] = []
        rank = 1

        for judgment in judgments:
            if judgment.relevance_score < 0.5:
                continue

            candidate = candidate_map.get(judgment.session_id, {})

            badge = self._map_badge(judgment.relevance_score)

            card = ResultCard(
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
            cards.append(card)
            rank += 1

        return cards

    @staticmethod
    def _map_badge(score: float) -> str:
        """Map a relevance score to a colored badge string.

        Args:
            score: Relevance score between 0.0 and 1.0.

        Returns:
            Rich-formatted badge string.
        """
        if score >= 0.8:
            return "[green]Strong match[/green]"
        return "[yellow]Moderate match[/yellow]"
