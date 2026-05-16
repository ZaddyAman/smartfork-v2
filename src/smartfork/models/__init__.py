"""SmartFork v2 — Data models, enums, dataclasses, and config."""

from smartfork.models.config import (
    AgentConfig,
    IndexingConfig,
    ProviderConfig,
    SearchConfig,
    UIConfig,
)
from smartfork.models.fork import ContextReport, ForkIntent
from smartfork.models.progress import ProgressEvent
from smartfork.models.search import (
    BatchRerankResult,
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
]
