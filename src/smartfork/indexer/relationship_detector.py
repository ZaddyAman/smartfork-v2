"""Relationship detector — explicit, heuristic, and optional LLM-verified tiers."""

import math
import time
from collections import defaultdict

from loguru import logger

from smartfork.models.relationship import SessionRelationship
from smartfork.models.session import QualityTag, SessionDocument


class RelationshipDetector:
    """Detects session relationships at index time.

    Three tiers:
    1. Explicit: uses parent_id from adapters (OpenCode)
    2. Heuristic: temporal proximity, file overlap, embedding similarity
    3. LLM-verified: optional, disabled by default
    """

    HEURISTIC_THRESHOLD = 0.40

    # Scoring weights
    TEMPORAL_WEIGHT = 0.30
    FILE_OVERLAP_WEIGHT = 0.25
    EMBEDDING_WEIGHT = 0.20
    WORKSPACE_WEIGHT = 0.15
    RESOLUTION_WEIGHT = 0.10

    # Time constants (milliseconds)
    _MS_PER_HOUR = 3600 * 1000
    _MS_PER_DAY = 24 * _MS_PER_HOUR
    _MS_PER_30_DAYS = 30 * _MS_PER_DAY

    def __init__(self) -> None:
        pass

    def detect_all(
        self,
        sessions: list[SessionDocument],
        vectors: dict[str, list[float]] | None = None,
    ) -> list[SessionRelationship]:
        """Run all detection tiers and return discovered relationships."""
        relationships: list[SessionRelationship] = []

        explicit = self._detect_explicit(sessions)
        relationships.extend(explicit)

        heuristic = self._detect_heuristic(sessions, vectors)
        relationships.extend(heuristic)

        logger.info(
            f"Relationship detection complete: {len(explicit)} explicit, "
            f"{len(heuristic)} heuristic"
        )
        return relationships

    def _detect_explicit(self, sessions: list[SessionDocument]) -> list[SessionRelationship]:
        """Tier 1: Use parent_id for explicit continuation relationships."""
        relationships: list[SessionRelationship] = []
        now = int(time.time() * 1000)
        for session in sessions:
            if session.parent_id:
                relationships.append(
                    SessionRelationship(
                        from_session=session.parent_id,
                        to_session=session.session_id,
                        relationship_type="continuation",
                        confidence=1.0,
                        detected_by="explicit",
                        reasons=["explicit_parent_link"],
                        created_at=now,
                    )
                )
        return relationships

    def _detect_heuristic(
        self,
        sessions: list[SessionDocument],
        vectors: dict[str, list[float]] | None = None,
    ) -> list[SessionRelationship]:
        """Tier 2: Group by project, sort by time, compare forward-only."""
        relationships: list[SessionRelationship] = []

        by_project: dict[str, list[SessionDocument]] = defaultdict(list)
        for session in sessions:
            by_project[session.project_name].append(session)

        for project_sessions in by_project.values():
            sorted_sessions = sorted(project_sessions, key=lambda s: s.session_start)
            n = len(sorted_sessions)
            for i in range(n):
                older = sorted_sessions[i]
                for j in range(i + 1, n):
                    newer = sorted_sessions[j]

                    if not self._passes_hard_filters(older, newer):
                        continue

                    score, reasons = self._score_pair(older, newer, vectors)

                    if score >= self.HEURISTIC_THRESHOLD:
                        rel_type = self._classify_relationship(older, newer, score)
                        relationships.append(
                            SessionRelationship(
                                from_session=older.session_id,
                                to_session=newer.session_id,
                                relationship_type=rel_type,
                                confidence=round(score, 4),
                                detected_by="heuristic",
                                reasons=reasons,
                                created_at=newer.session_start,
                            )
                        )

        return relationships

    def _passes_hard_filters(
        self,
        older: SessionDocument,
        newer: SessionDocument,
    ) -> bool:
        """Apply hard exclusion filters."""
        if older.session_id == newer.session_id:
            return False

        time_diff = newer.session_start - older.session_start
        if time_diff > self._MS_PER_30_DAYS:
            return False

        return bool(set(older.domains) & set(newer.domains))

    def _score_pair(
        self,
        older: SessionDocument,
        newer: SessionDocument,
        vectors: dict[str, list[float]] | None,
    ) -> tuple[float, list[str]]:
        """Score a pair of sessions with weighted signals."""
        score = 0.0
        reasons: list[str] = []

        # Temporal proximity (< 24 hours)
        time_diff = newer.session_start - older.session_start
        if time_diff < self._MS_PER_DAY:
            score += self.TEMPORAL_WEIGHT
            reasons.append("temporal_proximity")

        # File overlap (> 30% of max length)
        older_files = set(older.files_edited)
        newer_files = set(newer.files_edited)
        max_len = max(1, max(len(older_files), len(newer_files)))
        if older_files and newer_files:
            overlap_count = len(older_files & newer_files)
            overlap_ratio = overlap_count / max_len
            if overlap_ratio > 0.30:
                score += self.FILE_OVERLAP_WEIGHT
                reasons.append("file_overlap")

        # Embedding similarity (> 0.8)
        if vectors and older.session_id in vectors and newer.session_id in vectors:
            sim = self._cosine_similarity(
                vectors[older.session_id],
                vectors[newer.session_id],
            )
            if sim > 0.8:
                score += self.EMBEDDING_WEIGHT
                reasons.append("embedding_similarity")

        # Same workspace
        if older.project_root and older.project_root == newer.project_root:
            score += self.WORKSPACE_WEIGHT
            reasons.append("same_workspace")

        # Resolution boost (older is resolved)
        if self._is_resolved(older):
            score += self.RESOLUTION_WEIGHT
            reasons.append("resolution_boost")

        return min(score, 1.0), reasons

    def _classify_relationship(
        self,
        older: SessionDocument,
        newer: SessionDocument,
        score: float,
    ) -> str:
        """Classify relationship type based on metadata."""
        if self._is_resolved(older) and self._significant_task_overlap(
            older.task_raw, newer.task_raw
        ):
            return "supersession"

        if self._significant_task_overlap(
            older.task_raw, newer.task_raw
        ) and (set(older.files_edited) & set(newer.files_edited)):
            return "continuation"

        if (
            older.project_name == newer.project_name
            and not self._significant_task_overlap(older.task_raw, newer.task_raw)
        ):
            return "branch"

        return "related"

    def _is_resolved(self, session: SessionDocument) -> bool:
        """Check if session quality_tag == 'solution_found'."""
        return session.quality_tag == QualityTag.SOLUTION_FOUND

    def _significant_task_overlap(self, task_a: str, task_b: str) -> bool:
        """Compare task vocabulary overlap > 50%."""
        words_a = self._tokenize_task(task_a)
        words_b = self._tokenize_task(task_b)

        if not words_a or not words_b:
            return False

        intersection = words_a & words_b
        union = words_a | words_b
        if not union:
            return False

        return len(intersection) / len(union) > 0.5

    @staticmethod
    def _tokenize_task(task: str) -> set[str]:
        """Tokenize a task string into lowercase words without stop words or punctuation."""
        import string

        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "was",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "and",
            "or",
            "but",
            "with",
            "from",
            "by",
            "as",
        }

        translator = str.maketrans(string.punctuation, " " * len(string.punctuation))
        cleaned = task.lower().translate(translator)
        words = {w for w in cleaned.split() if w and w not in stop_words}
        return words

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
        mag_a = math.sqrt(sum(a * a for a in vec_a))
        mag_b = math.sqrt(sum(b * b for b in vec_b))

        if mag_a == 0.0 or mag_b == 0.0:
            return 0.0

        return dot_product / (mag_a * mag_b)
