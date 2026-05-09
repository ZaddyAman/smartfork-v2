"""Search-related data models for SmartFork v2."""

from dataclasses import dataclass, field
from enum import StrEnum


class SearchIntent(StrEnum):
    """What kind of session the user is looking for."""

    IMPLEMENTATION_LOOKUP = "implementation_lookup"
    ERROR_RECALL = "error_recall"
    DECISION_HUNTING = "decision_hunting"
    PATTERN_HUNTING = "pattern_hunting"
    VAGUE_MEMORY = "vague_memory"
    TEMPORAL_LOOKUP = "temporal_lookup"
    CONTINUATION = "continuation"


@dataclass
class QueryDecomposition:
    """Output of query understanding (deterministic or LLM-based)."""

    intent: SearchIntent
    core_goal: str
    entities: list[str] = field(default_factory=list)
    search_variants: list[str] = field(default_factory=list)
    what_should_match: str = ""
    what_should_not_match: str = ""
    prefer_code: bool = False
    prefer_recent: bool = False
    time_range_days: int = 90


@dataclass
class SearchResult:
    """A single search result from any search path."""

    session_id: str
    title: str
    project_name: str
    match_score: float
    relevance_explanation: str = ""
    quality_tag: str = ""
    supersession_status: str = "none"
    duration_minutes: float = 0.0
    session_start: int = 0
    files_edited: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    summary_preview: str = ""
    task_preview: str = ""


@dataclass
class ResultCard:
    """A formatted result card for display in TUI/CLI."""

    rank: int
    session_id: str
    title: str
    project_name: str
    match_score: float
    relevance_explanation: str = ""
    quality_badge: str = ""
    supersession_note: str = ""
    time_ago: str = ""
    duration: str = ""
    files_summary: str = ""
    excerpt: str = ""
    fork_command: str = ""
