"""Progress event model for live indexing pipeline display."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProgressEvent:
    """Event emitted during the indexing pipeline for live UI updates.

    All fields are optional — callers populate only the fields relevant
    to the current phase (scanning / parsing / indexing).
    """

    phase: str = "starting"

    # ── Scan phase ──
    agent_id: str | None = None
    scan_status: str = ""     # "running" | "complete" | "pending"
    scan_count: int = 0
    scan_path: str = ""

    # ── Parse phase ──
    current: int = 0          # overall parsed count
    total: int = 0            # overall total to parse
    agent_current: int = 0    # per-agent parsed count
    agent_total: int = 0      # per-agent total

    # ── Index phase ──
    session_current: int = 0
    session_total: int = 0
    chunks: int = 0           # chunks in current session
    embed_current: int = 0    # chunks embedded so far
    embed_total: int = 0      # total chunks for current session
    enrich_step: str = ""     # "structured" | "done"
    enrich_done: int = 0
    enrich_total: int = 1

    # ── Live counters ──
    stats: dict[str, Any] = field(default_factory=dict)
