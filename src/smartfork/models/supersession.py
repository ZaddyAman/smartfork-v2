"""Supersession-related data models for SmartFork v2."""

from dataclasses import dataclass, field


@dataclass
class SupersessionLink:
    """A link between two sessions where one supersedes the other."""

    superseded_id: str  # Older session
    superseding_id: str  # Newer session that replaces it
    confidence: float  # 0.0 to 1.0
    detected_at: int  # ms timestamp of detection
    reason: str = ""  # Why this was detected


@dataclass
class ResolutionStatus:
    """Resolution status of a session (regex-based)."""

    status: str = "unknown"  # "solved" | "partial" | "ongoing" | "unknown"
    signals: list[str] = field(default_factory=list)
    had_errors: bool = False


SIMILARITY_THRESHOLDS = {
    "error_recall": 0.82,
    "decision_hunting": 0.80,
    "default": 0.85,
}
