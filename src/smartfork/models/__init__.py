"""SmartFork v2 — Data models, enums, dataclasses, and config."""

from smartfork.models.config import (
    AgentConfig,
    IndexingConfig,
    ProviderConfig,
    SearchConfig,
    UIConfig,
)
from smartfork.models.enrichment import SessionEnrichment
from smartfork.models.fork import ContextReport, ForkIntent
from smartfork.models.progress import ProgressEvent
from smartfork.models.query import QueryInterpretation
from smartfork.models.relationship import (
    Chain,
    SessionRelationship,
    TimelineEntry,
    TimelineSummary,
)
from smartfork.models.search import (
    BatchJudgeResult,
    BatchRerankResult,
    JudgeOutput,
    QueryDecomposition,
    RerankResult,
    ResultCard,
    SearchIntent,
    SearchResult,
)
from smartfork.models.session import (
    QualityTag,
    RawSessionData,
    RawTurn,
    SessionDocument,
)
from smartfork.models.supersession import (
    SIMILARITY_THRESHOLDS,
    ResolutionStatus,
    SupersessionLink,
)

__all__ = [
    # Session
    "RawTurn",
    "RawSessionData",
    "QualityTag",
    "SessionDocument",
    # Search
    "SearchIntent",
    "QueryDecomposition",
    "SearchResult",
    "ResultCard",
    "RerankResult",
    "BatchRerankResult",
    "JudgeOutput",
    "BatchJudgeResult",
    # Fork
    "ForkIntent",
    "ContextReport",
    # Progress
    "ProgressEvent",
    # Config
    "AgentConfig",
    "ProviderConfig",
    "IndexingConfig",
    "SearchConfig",
    "UIConfig",
    # Supersession
    "SupersessionLink",
    "ResolutionStatus",
    "SIMILARITY_THRESHOLDS",
    # Relationship / Chain / Timeline
    "SessionRelationship",
    "Chain",
    "TimelineEntry",
    "TimelineSummary",
    # Query
    "QueryInterpretation",
    # Enrichment
    "SessionEnrichment",
]
