"""Fork-related data models for SmartFork v2."""

from dataclasses import dataclass, field
from enum import StrEnum


class ForkIntent(StrEnum):
    """What the user wants to do with the forked context."""

    CONTINUE = "continue"
    REFERENCE = "reference"
    DEBUG = "debug"
    SYNTHESIZE = "synthesize"


@dataclass
class ContextReport:
    """Output of fork priming. What gets injected into the new session."""

    session_id: str
    fork_intent: ForkIntent
    summary: str = ""
    approach: str = ""
    completed: str = ""
    remaining: str = ""
    key_files: list[str] = field(default_factory=list)
    key_decisions: list[str] = field(default_factory=list)
    code_snippets: list[str] = field(default_factory=list)
    gotchas: list[str] = field(default_factory=list)
    supersession_warning: str = ""
    is_compacted: bool = False
    gap_analysis: str = ""
