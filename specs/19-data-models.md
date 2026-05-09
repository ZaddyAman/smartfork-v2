# SmartFork v2 — Data Models

> **Build target:** All Pydantic models, dataclasses, enums, and protocols.
> **Must implement BEFORE any other layer.** Every other spec references these types.
> These models are the foundation. Every other layer imports from here.

---

## 1. Adapter Types (normalized contract)

**File:** `src/smartfork/models/session.py`

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List
from enum import Enum


@dataclass
class RawTurn:
    """A single conversation turn extracted by any adapter."""
    role: str           # "user" | "assistant" | "tool" | "system"
    content: str        # Raw text content
    timestamp: int = 0  # Unix timestamp in milliseconds
    is_tool_call: bool = False
    tool_name: Optional[str] = None


@dataclass
class RawSessionData:
    """Agent-agnostic session data. Output of SessionAdapter.parse_raw()."""
    session_id: str
    agent_id: str           # "kilocode" | "claudecode" | "opencode" | ...
    session_path: Path

    turns: List[RawTurn] = field(default_factory=list)

    # File signals
    files_edited: List[str] = field(default_factory=list)
    files_read: List[str] = field(default_factory=list)
    files_mentioned: List[str] = field(default_factory=list)
    files_user_edited: List[str] = field(default_factory=list)
    final_files: List[str] = field(default_factory=list)

    # Session context
    workspace_dir: str = ""
    task_raw: str = ""
    model_used: Optional[str] = None
    session_start: int = 0  # ms
    session_end: int = 0    # ms
    edit_count: int = 0
    user_edit_count: int = 0

    # Adapter extras (not used by core pipeline)
    extra: dict = field(default_factory=dict)

    @property
    def duration_minutes(self) -> float:
        if self.session_end > self.session_start > 0:
            return round((self.session_end - self.session_start) / 60000.0, 1)
        return 0.0
```

---

## 2. Session Document (core pipeline type)

**File:** `src/smartfork/models/session.py` (continued)

```python
class QualityTag(str, Enum):
    """Classification of session outcome. Set at index time by LLM."""
    SOLUTION_FOUND = "solution_found"   # Working code + final commit
    DEAD_END = "dead_end"               # Abandoned, contradicted by later session
    PARTIAL = "partial"                 # Incomplete but has useful fragments
    REFERENCE = "reference"             # Setup/config, not a specific fix
    UNKNOWN = "unknown"                 # Not yet classified


class SessionDocument:
    """Normalized session document flowing through the core pipeline."""
    session_id: str
    agent: str              # Which agent produced this
    project_name: str
    project_root: str

    # Timestamps
    session_start: int = 0  # ms
    session_end: int = 0    # ms
    duration_minutes: float = 0.0

    # Model
    model_used: Optional[str] = None

    # File signals
    files_edited: List[str] = field(default_factory=list)
    files_read: List[str] = field(default_factory=list)
    files_mentioned: List[str] = field(default_factory=list)
    edit_count: int = 0
    user_edit_count: int = 0
    final_files: List[str] = field(default_factory=list)

    # Derived properties
    domains: List[str] = field(default_factory=list)     # e.g., ["backend", "auth", "database"]
    languages: List[str] = field(default_factory=list)   # e.g., ["python", "typescript"]
    layers: List[str] = field(default_factory=list)      # e.g., ["backend", "frontend"]
    session_pattern: str = "standard_implementation"      # Classified pattern

    # Content
    task_raw: str = ""                  # Primary retrieval key
    reasoning_docs: List[str] = field(default_factory=list)
    summary_doc: str = ""               # LLM-generated 3-sentence summary
    propositions: List[str] = field(default_factory=list)  # Atomic facts

    # Quality (set at index time)
    quality_tag: QualityTag = QualityTag.UNKNOWN
    tech_tags: List[str] = field(default_factory=list)  # e.g., ["FastAPI", "JWT", "PostgreSQL"]

    # Index metadata
    indexed_at: int = 0  # ms
    schema_version: int = 2
```

---

## 3. Search Types

**File:** `src/smartfork/models/search.py`

```python
from dataclasses import dataclass, field
from typing import Optional, List


class SearchIntent(str, Enum):
    """What kind of session the user is looking for."""
    IMPLEMENTATION_LOOKUP = "implementation_lookup"  # "How did I build X?"
    ERROR_RECALL = "error_recall"                   # "How did I fix Y error?"
    DECISION_HUNTING = "decision_hunting"            # "Why did I choose approach A over B?"
    PATTERN_HUNTING = "pattern_hunting"              # "What pattern did I use for Z?"
    VAGUE_MEMORY = "vague_memory"                    # "I remember something about..."
    TEMPORAL_LOOKUP = "temporal_lookup"              # "What was I working on last week?"
    CONTINUATION = "continuation"                    # "Continue where I left off"


@dataclass
class QueryDecomposition:
    """Output of query understanding (deterministic or LLM-based)."""
    intent: SearchIntent
    core_goal: str             # Main thing user wants
    entities: List[str]        # Key entities: file names, tech terms, concepts
    search_variants: List[str] # Reformulated queries for multi-variant search
    what_should_match: str     # Positive signal: what results SHOULD contain
    what_should_not_match: str # Negative signal: what to avoid
    prefer_code: bool = False
    prefer_recent: bool = False
    time_range_days: int = 90


@dataclass
class SearchResult:
    """A single search result from any search path."""
    session_id: str
    title: str                 # LLM-generated session title
    project_name: str
    match_score: float         # 0.0 to 1.0
    relevance_explanation: str # Why this matched (agentic path only)
    quality_tag: str
    supersession_status: str   # "superseding" | "superseded" | "none"
    duration_minutes: float
    session_start: int         # ms
    files_edited: List[str]
    domains: List[str]
    languages: List[str]
    summary_preview: str       # First 150 chars of summary
    task_preview: str          # First 100 chars of task


@dataclass
class ResultCard:
    """A formatted result card for display in TUI/CLI."""
    rank: int
    session_id: str
    title: str
    project_name: str
    match_score: float
    relevance_explanation: str
    quality_badge: str         # "✓ Solved" | "⚠ Partial" | "✗ Dead End" | ""
    supersession_note: str     # "Superseded by abc123" | "Fixes earlier attempt" | ""
    time_ago: str              # "3 days ago" | "2 weeks ago"
    duration: str              # "47 min"
    files_summary: str         # "auth.py, models.py +3"
    excerpt: str               # Most relevant snippet
    fork_command: str          # "smartfork fork abc123def"
```

---

## 4. Fork Types

**File:** `src/smartfork/models/fork.py`

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List


class ForkIntent(str, Enum):
    """What the user wants to do with the forked context."""
    CONTINUE = "continue"       # Continue where the session left off
    REFERENCE = "reference"     # Reference the session's approach/decisions
    DEBUG = "debug"             # Understand a bug fix from this session
    SYNTHESIZE = "synthesize"   # Combine context from multiple sessions


@dataclass
class ContextReport:
    """Output of fork priming. What gets injected into the new session."""
    session_id: str
    fork_intent: ForkIntent
    summary: str                  # What was being done
    approach: str                 # How it was approached
    completed: str                # What was completed
    remaining: str                # What's left (CONTINUE intent only)
    key_files: List[str]          # Most relevant files
    key_decisions: List[str]      # Architecture/approach decisions
    code_snippets: List[str]      # Key code blocks (max 5, 800 chars each)
    gotchas: List[str]            # Warnings: "don't do X because Y"
    supersession_warning: str     # Empty or "This session was superseded by abc123"
    is_compacted: bool            # Was the session compacted?
    gap_analysis: str             # If compacted: what context was lost and recovered
```

---

## 5. Config & Agent Types

**File:** `src/smartfork/models/config.py`

```python
from pydantic import BaseModel, Field
from typing import Optional, Union, List
from pathlib import Path


class AgentConfig(BaseModel):
    """Configuration for a single coding agent."""
    enabled: bool = False
    sessions_path: Union[str, List[str]] = ""
    ide: Optional[str] = None

    def get_paths(self) -> List[Path]:
        if isinstance(self.sessions_path, str):
            return [Path(self.sessions_path)] if self.sessions_path else []
        return [Path(p) for p in self.sessions_path if p]


class ProviderConfig(BaseModel):
    """Configuration for LLM or embedding provider."""
    provider: str = "ollama"    # ollama | anthropic | openai | sentence-transformers
    model: str = ""             # Model name
    base_url: Optional[str] = None


class IndexingConfig(BaseModel):
    """Indexing pipeline configuration."""
    chunk_size: int = 512
    chunk_overlap: int = 128
    batch_size: int = 100
    default_search_results: int = 10
    auto_summarize: bool = True
    auto_tag: bool = True      # Quality + tech tags
    auto_title: bool = True


class SearchConfig(BaseModel):
    """Search pipeline configuration."""
    deterministic_enabled: bool = True     # Path A always on
    agentic_enabled: bool = False          # Path B opt-in
    max_agent_refinement_rounds: int = 3
    cache_enabled: bool = True
    cache_size: int = 128
    cache_ttl: int = 300  # seconds


class UIConfig(BaseModel):
    """UI/TUI configuration."""
    use_textual: bool = True    # Use Textual TUI (False = Rich CLI)
    theme: str = "obsidian"     # phosphor | obsidian | ember | arctic | iron | tungsten
    animation_fps: int = 10
    adaptive_fps: bool = True   # Auto-reduce FPS when idle
    disable_animations: bool = False
    lite_mode: bool = False
```

---

## 6. Provider Protocols

**File:** `src/smartfork/providers/protocols.py`

```python
from typing import Protocol, List, Optional


class LLMProvider(Protocol):
    """Protocol for LLM completion providers."""
    def complete(self, prompt: str, max_tokens: int = 500, temperature: float = 0.1) -> str: ...
    def complete_structured(self, prompt: str, output_schema: type, max_tokens: int = 500) -> object: ...


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers."""
    def embed(self, text: str, doc_type: str = "task_doc") -> List[float]: ...
    def embed_query(self, query: str) -> List[float]: ...
    def embed_batch(self, texts: List[str], doc_type: str = "task_doc") -> List[List[float]]: ...
    def get_dimensions(self) -> int: ...


class SessionAdapter(Protocol):
    """Protocol for agent-specific session parsers."""
    agent_id: str
    display_name: str
    session_type: str  # "dir" | "file" | "sqlite"

    def is_valid_session(self, session_path: Path) -> bool: ...
    def get_session_files(self, session_path: Path) -> List[str]: ...
    def parse_raw(self, session_path: Path) -> Optional[RawSessionData]: ...
    def get_default_sessions_paths(self) -> List[Path]: ...
    def get_ide_choices(self) -> List[str]: ...
```

---

## 7. Supersession Types

**File:** `src/smartfork/models/supersession.py`

```python
@dataclass
class SupersessionLink:
    """A link between two sessions where one supersedes the other."""
    superseded_id: str       # Older session
    superseding_id: str      # Newer session that replaces it  
    confidence: float        # 0.0 to 1.0
    detected_at: int         # ms timestamp of detection
    reason: str              # Why this was detected


@dataclass
class ResolutionStatus:
    """Resolution status of a session (regex-based)."""
    status: str              # "solved" | "partial" | "ongoing" | "unknown"
    signals: List[str]       # Which regex patterns matched
    had_errors: bool


SIMILARITY_THRESHOLDS = {
    "error_recall": 0.82,
    "decision_hunting": 0.80,
    "default": 0.85,
}
```

---

## Implementation Notes for Ralph

1. **All models live in `src/smartfork/models/`** — import from there, never define models in other modules.
2. **Use `@dataclass` for internal types, `BaseModel` for config/boundary types.**
3. **Protocols define interfaces, not implementations.** Put protocols in the package that CONSUMES the interface.
4. **Enums for fixed sets** — QualityTag, SearchIntent, ForkIntent. Never use raw strings.
5. **The `RawTurn.role` field accepts exactly 4 values**: "user", "assistant", "tool", "system".
6. **Timestamps are ALWAYS milliseconds (int).** Never seconds or floats.
7. **Duration is always float minutes.**
8. **All List fields default to empty list, never None.**
