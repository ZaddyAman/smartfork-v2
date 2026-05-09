"""Provider protocols for SmartFork v2."""

from pathlib import Path
from typing import Protocol

from smartfork.models.session import RawSessionData


class LLMProvider(Protocol):
    """Protocol for LLM completion providers."""

    def complete(
        self, prompt: str, max_tokens: int = 500, temperature: float = 0.1
    ) -> str: ...

    def complete_structured(
        self, prompt: str, output_schema: type, max_tokens: int = 500
    ) -> object: ...


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers."""

    def embed(self, text: str, doc_type: str = "task_doc") -> list[float]: ...

    def embed_query(self, query: str) -> list[float]: ...

    def embed_batch(
        self, texts: list[str], doc_type: str = "task_doc"
    ) -> list[list[float]]: ...

    def get_dimensions(self) -> int: ...


class SessionAdapter(Protocol):
    """Protocol for agent-specific session parsers."""

    agent_id: str
    display_name: str
    session_type: str  # "dir" | "file" | "sqlite"

    def is_valid_session(self, session_path: Path) -> bool: ...

    def get_session_files(self, session_path: Path) -> list[str]: ...

    def parse_raw(self, session_path: Path) -> RawSessionData | None: ...

    def get_default_sessions_paths(self) -> list[Path]: ...

    def get_ide_choices(self) -> list[str]: ...
