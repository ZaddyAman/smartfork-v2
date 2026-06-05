"""Search-related data models for SmartFork v2."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from smartfork.models.relationship import TimelineSummary


class SearchIntent(StrEnum):
    """What kind of session the user is looking for."""

    IMPLEMENTATION_LOOKUP = "implementation_lookup"
    ERROR_RECALL = "error_recall"
    DECISION_HUNTING = "decision_hunting"
    PATTERN_HUNTING = "pattern_hunting"
    VAGUE_MEMORY = "vague_memory"
    TEMPORAL_LOOKUP = "temporal_lookup"
    CONTINUATION = "continuation"


class QueryDecomposition(BaseModel):
    """Output of query understanding (deterministic or LLM-based)."""

    core_goal: str
    search_variants: list[str] = Field(default_factory=list)
    entities: dict[str, Any] = Field(default_factory=dict)
    intent: str = "vague_memory"
    metadata_filters: dict[str, Any] = Field(default_factory=dict)
    prefer_recent: bool = False
    prefer_code: bool = False


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


class RerankResult(BaseModel):
    """Single candidate relevance scoring from LLM reranker."""

    session_id: str
    relevance_score: float
    reason: str = ""


class BatchRerankResult(BaseModel):
    """Batch output from LLM reranker."""

    rankings: list[RerankResult] = Field(default_factory=list)


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
    tags: list[str] = field(default_factory=list)
    fork_command: str = ""
    synthesis: TimelineSummary | None = None


class JudgeOutput(BaseModel):
    """Single judgment from the batch judge agent."""

    session_id: str
    relevance_score: float
    matches_query: bool
    reason: str
    key_snippet: str


class BatchJudgeResult(BaseModel):
    """Batch output from the judge agent."""

    judgments: list[JudgeOutput] = Field(default_factory=list)
