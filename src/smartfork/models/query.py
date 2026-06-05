"""Query interpretation models for SmartFork v2."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryInterpretation:
    """Structured output from query understanding / expansion."""

    original_query: str
    keywords: list[str] = field(default_factory=list)
    synonyms: list[str] = field(default_factory=list)
    expanded_query: str = ""
    temporal_filter: dict[str, Any] | None = None
    intent: str = "unknown"
    project_hint: str | None = None
    multi_session_confidence: float = 0.0
    needs_deep_mode: bool = False
    quality_boost: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not (0.0 <= self.multi_session_confidence <= 1.0):
            raise ValueError(
                f"multi_session_confidence must be between 0.0 and 1.0, "
                f"got {self.multi_session_confidence}"
            )
