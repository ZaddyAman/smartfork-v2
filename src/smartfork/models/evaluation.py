"""Evaluation data models for SmartFork v2."""

import time
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from smartfork.models.search import ResultCard


class GeneratedQuery(BaseModel):
    """A synthetic query with its type and expected source session."""

    query: str = Field(description="The generated search query")
    query_type: str = Field(description="specific, short, or vague")
    source_session_id: str = Field(description="Session this query was generated from")


class EvalQueryBatch(BaseModel):
    """Structured output schema for LLM query generation."""

    queries: list[GeneratedQuery] = Field(description="3 generated queries")


class EvalJudgeOutput(BaseModel):
    """A single 0-3 relevance judgment."""

    score: int = Field(
        ge=0,
        le=3,
        description="0=irrelevant, 1=tangential, 2=partial, 3=direct",
    )
    reason: str = Field(description="Brief justification for the score")


class EvalBatchJudgeOutput(BaseModel):
    """Structured output schema for batched relevance judging."""

    judgments: list[EvalJudgeOutput] = Field(description="Judgments in result order")


@dataclass
class ModeResult:
    """Search results and judgments for a single query in one mode."""

    mode: str
    query: str
    query_type: str
    source_session_id: str
    result_session_ids: list[str] = field(default_factory=list)
    judgments: list[EvalJudgeOutput] = field(default_factory=list)
    latency_ms: float = 0.0
    llm_calls: int = 0
    search_results: list[ResultCard] = field(default_factory=list)


@dataclass
class EvalRun:
    """Complete evaluation run data."""

    sampled_session_ids: list[str]
    queries: list[GeneratedQuery]
    mode_results: list[ModeResult]
    overall_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    per_query_type_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    end_time: float = field(default_factory=time.time)
