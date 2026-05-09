"""Supersession detection for SmartFork v2."""

import re
from typing import Any

from smartfork.models.session import SessionDocument
from smartfork.models.supersession import SIMILARITY_THRESHOLDS

# Regex patterns for resolution status
RESOLVED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(fixed|solved|resolved|completed|done|finished|working)\b", re.IGNORECASE),
    re.compile(r"\b(fix\s*(is|was)\s*(applied|deployed|merged|committed))\b", re.IGNORECASE),
]
ONGOING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(in\s*progress|wip|working\s*on|not\s*yet|still\s*need)\b", re.IGNORECASE),
    re.compile(r"\b(todo|to-do|remaining|left\s*to\s*do)\b", re.IGNORECASE),
]
# Negation prefixes to avoid false positives
NEGATION_PREFIXES = [
    "not ", "n't ", "never ", "no ", "cannot ", "unable to ",
]


def _has_negation(text: str, match_start: int) -> bool:
    """Check if a match is preceded by a negation word."""
    prefix = text[max(0, match_start - 30) : match_start].lower()
    return any(prefix.rstrip().endswith(neg.rstrip()) for neg in NEGATION_PREFIXES)


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot: float = sum(a * b for a, b in zip(vec1, vec2, strict=True))
    mag1: float = sum(a * a for a in vec1) ** 0.5
    mag2: float = sum(b * b for b in vec2) ** 0.5
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


class SupersessionDetector:
    """Detects when newer sessions supersede older ones.

    Uses content similarity, project/domain overlap, and resolution
    status to determine if one session obsoletes another.
    """

    def __init__(self) -> None:
        self.thresholds = SIMILARITY_THRESHOLDS

    def detect_supersession(
        self,
        older: SessionDocument,
        newer: SessionDocument,
        older_vector: list[float] | None = None,
        newer_vector: list[float] | None = None,
    ) -> float:
        """Calculate supersession confidence between two sessions.

        Args:
            older: The potentially superseded (older) session.
            newer: The potentially superseding (newer) session.
            older_vector: Pre-computed vector for older session.
            newer_vector: Pre-computed vector for newer session.

        Returns:
            Confidence score 0.0 to 1.0. Values above threshold indicate
            a supersession relationship.
        """
        # Guard: self-supersession
        if older.session_id == newer.session_id:
            return 0.0

        # Guard: unknown project
        if older.project_name == "unknown_project" or newer.project_name == "unknown_project":
            return 0.0

        # Guard: must be same project
        if older.project_name != newer.project_name:
            return 0.0

        # Guard: newer must actually be newer
        if newer.session_start <= older.session_start:
            return 0.0

        # Guard: short tasks (<1 turn) are likely config/setup, not candidates
        if older.task_raw and len(older.task_raw) < 20:
            return 0.0

        # Check domain overlap
        older_domains = set(older.domains)
        newer_domains = set(newer.domains)
        if not older_domains & newer_domains:
            return 0.0  # No domain overlap

        # Calculate similarity score
        similarity = 0.5  # base score from domain/project match

        # Boost from content similarity if vectors available
        if older_vector and newer_vector:
            vec_sim = _cosine_similarity(older_vector, newer_vector)
            similarity = 0.3 + (0.7 * vec_sim)  # Blend domain (0.3) + vector (0.7)

        # Boost if older has low resolution status
        older_resolved = self._check_resolution(older)
        if not older_resolved:
            similarity += 0.1

        # Boost if newer has high resolution status
        newer_resolved = self._check_resolution(newer)
        if newer_resolved:
            similarity += 0.05

        return min(similarity, 1.0)

    def _check_resolution(self, session: SessionDocument) -> bool:
        """Check if a session appears to be resolved using regex."""
        text = session.task_raw + " " + session.summary_doc
        for pattern in RESOLVED_PATTERNS:
            for match in pattern.finditer(text):
                if not _has_negation(text, match.start()):
                    return True
        return False

    def find_supersessions(
        self,
        sessions: list[SessionDocument],
        vectors: dict[str, list[float]] | None = None,
        intent: str = "default",
    ) -> list[tuple[str, str, float]]:
        """Find all supersession relationships in a list of sessions.

        Args:
            sessions: List of sessions to analyze.
            vectors: Optional dict of session_id → embedding vector.
            intent: Search intent for threshold selection.

        Returns:
            List of (superseded_id, superseding_id, confidence) tuples.
        """
        threshold = self.thresholds.get(intent, self.thresholds["default"])
        results: list[tuple[str, str, float]] = []

        for i, older in enumerate(sessions):
            for j, newer in enumerate(sessions):
                if i == j:
                    continue
                older_vec = vectors.get(older.session_id) if vectors else None
                newer_vec = vectors.get(newer.session_id) if vectors else None
                score = self.detect_supersession(older, newer, older_vec, newer_vec)
                if score >= threshold:
                    results.append((older.session_id, newer.session_id, score))

        return results


class SupersessionAnnotator:
    """Annotates search results with supersession indicators.

    Adds visual indicators and follows supersession chains.
    """

    @staticmethod
    def annotate(
        session_id: str,
        supersession_map: dict[str, tuple[str, float]],
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """Annotate a session with its supersession status.

        Args:
            session_id: The session to annotate.
            supersession_map: Map of superseded_id → (superseding_id, confidence).
            max_depth: Maximum chain depth to follow.

        Returns:
            Dict with status, indicator, and superseded_by chain info.
        """
        # Check if this session is superseded
        if session_id in supersession_map:
            superseding_id, confidence = supersession_map[session_id]
            chain: list[str] = [session_id, superseding_id]
            current = superseding_id
            depth = 0
            while current in supersession_map and depth < max_depth:
                current, _ = supersession_map[current]
                chain.append(current)
                depth += 1
            return {
                "status": "superseded",
                "indicator": "⬆",
                "superseded_by": superseding_id,
                "confidence": confidence,
                "chain": chain,
            }

        # Check if this session supersedes another
        for superseded_id, (superseding_id, confidence) in supersession_map.items():
            if superseding_id == session_id:
                return {
                    "status": "superseding",
                    "indicator": "✅",
                    "supersedes": superseded_id,
                    "confidence": confidence,
                    "boost": 0.15,
                }

        return {
            "status": "none",
            "indicator": "",
        }
