"""Relationship, chain, and timeline models for SmartFork v2."""

from dataclasses import dataclass, field

from smartfork.models.session import QualityTag, SessionDocument


@dataclass
class SessionRelationship:
    """A directed relationship between two sessions."""

    from_session: str
    to_session: str
    relationship_type: str  # 'continuation' | 'supersession' | 'branch' | 'related'
    confidence: float
    detected_by: str  # 'explicit' | 'heuristic' | 'llm_verified'
    reasons: list[str] = field(default_factory=list)
    created_at: int = 0  # ms

    _VALID_TYPES: set[str] = field(
        default_factory=lambda: {"continuation", "supersession", "branch", "related"},
        repr=False,
    )
    _VALID_DETECTED_BY: set[str] = field(
        default_factory=lambda: {"explicit", "heuristic", "llm_verified"},
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.from_session == self.to_session:
            raise ValueError("from_session must not equal to_session")
        if self.relationship_type not in self._VALID_TYPES:
            raise ValueError(
                f"relationship_type must be one of {sorted(self._VALID_TYPES)}, "
                f"got '{self.relationship_type}'"
            )
        if self.detected_by not in self._VALID_DETECTED_BY:
            raise ValueError(
                f"detected_by must be one of {sorted(self._VALID_DETECTED_BY)}, "
                f"got '{self.detected_by}'"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}"
            )


@dataclass
class Chain:
    """A chain of related sessions."""

    sessions: list[SessionDocument] = field(default_factory=list)
    chain_type: str = "linear"
    head_session_id: str = ""
    tail_session_id: str = ""

    _VALID_CHAIN_TYPES: set[str] = field(
        default_factory=lambda: {"linear", "branched", "merged"},
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.chain_type not in self._VALID_CHAIN_TYPES:
            raise ValueError(
                f"chain_type must be one of {sorted(self._VALID_CHAIN_TYPES)}, "
                f"got '{self.chain_type}'"
            )
        if len(self.sessions) < 1:
            raise ValueError("sessions must have at least 1 element")
        expected_head = self.sessions[0].session_id
        expected_tail = self.sessions[-1].session_id
        if not self.head_session_id:
            self.head_session_id = expected_head
        elif self.head_session_id != expected_head:
            raise ValueError(
                f"head_session_id must match first session ({expected_head}), "
                f"got '{self.head_session_id}'"
            )
        if not self.tail_session_id:
            self.tail_session_id = expected_tail
        elif self.tail_session_id != expected_tail:
            raise ValueError(
                f"tail_session_id must match last session ({expected_tail}), "
                f"got '{self.tail_session_id}'"
            )


@dataclass
class TimelineEntry:
    """A single entry in a session timeline."""

    session_id: str
    timestamp: int  # ms
    task: str = ""
    quality_tag: QualityTag = QualityTag.UNKNOWN
    summary: str = ""
    relationship_to_next: str | None = None


@dataclass
class TimelineSummary:
    """Summary of a complete session timeline."""

    narrative: str = ""
    timeline: list[TimelineEntry] = field(default_factory=list)
    suggested_fork_session_id: str = ""
    resolution_status: str = "unknown"

    _VALID_RESOLUTION_STATUSES: set[str] = field(
        default_factory=lambda: {"solved", "ongoing", "dead_end", "mixed", "unknown"},
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.resolution_status not in self._VALID_RESOLUTION_STATUSES:
            raise ValueError(
                f"resolution_status must be one of {sorted(self._VALID_RESOLUTION_STATUSES)}, "
                f"got '{self.resolution_status}'"
            )
