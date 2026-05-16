"""Session-related data models for SmartFork v2."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


@dataclass
class RawTurn:
    """A single conversation turn extracted by any adapter."""

    role: str  # "user" | "assistant" | "tool" | "system"
    content: str  # Raw text content
    timestamp: int = 0  # Unix timestamp in milliseconds
    is_tool_call: bool = False
    tool_name: str | None = None


@dataclass
class RawSessionData:
    """Agent-agnostic session data. Output of SessionAdapter.parse_raw()."""

    session_id: str
    agent_id: str  # "kilocode" | "claudecode" | "opencode" | ...
    session_path: Path

    turns: list[RawTurn] = field(default_factory=list)

    # File signals
    files_edited: list[str] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)
    files_mentioned: list[str] = field(default_factory=list)
    files_user_edited: list[str] = field(default_factory=list)
    final_files: list[str] = field(default_factory=list)

    # Session context
    workspace_dir: str = ""
    task_raw: str = ""
    model_used: str | None = None
    session_start: int = 0  # ms
    session_end: int = 0  # ms
    edit_count: int = 0
    user_edit_count: int = 0

    # Adapter extras (not used by core pipeline)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_minutes(self) -> float:
        if self.session_end > self.session_start > 0:
            return round((self.session_end - self.session_start) / 60000.0, 1)
        return 0.0


class QualityTag(StrEnum):
    """Classification of session outcome. Set at index time by LLM."""

    SOLUTION_FOUND = "solution_found"  # Working code + final commit
    DEAD_END = "dead_end"  # Abandoned, contradicted by later session
    PARTIAL = "partial"  # Incomplete but has useful fragments
    REFERENCE = "reference"  # Setup/config, not a specific fix
    UNKNOWN = "unknown"  # Not yet classified


@dataclass
class SessionDocument:
    """Normalized session document flowing through the core pipeline."""

    session_id: str
    agent: str  # Which agent produced this
    project_name: str
    project_root: str

    # Timestamps
    session_start: int = 0  # ms
    session_end: int = 0  # ms
    duration_minutes: float = 0.0

    # Model
    model_used: str | None = None

    # File signals
    files_edited: list[str] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)
    files_mentioned: list[str] = field(default_factory=list)
    edit_count: int = 0
    user_edit_count: int = 0
    final_files: list[str] = field(default_factory=list)

    # Derived properties
    domains: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    layers: list[str] = field(default_factory=list)
    session_pattern: str = "standard_implementation"

    # Content
    task_raw: str = ""
    reasoning_docs: list[str] = field(default_factory=list)
    summary_doc: str = ""
    propositions: list[str] = field(default_factory=list)

    # Quality (set at index time)
    quality_tag: QualityTag = QualityTag.UNKNOWN
    tech_tags: list[str] = field(default_factory=list)

    # Index metadata
    indexed_at: int = 0  # ms
    schema_version: int = 3
