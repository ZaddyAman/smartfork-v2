"""Configuration data models for SmartFork v2."""

from pathlib import Path

from pydantic import BaseModel


class AgentConfig(BaseModel):
    """Configuration for a single coding agent."""

    enabled: bool = False
    sessions_path: str | list[str] = ""
    ide: str | None = None

    def get_paths(self) -> list[Path]:
        if isinstance(self.sessions_path, str):
            return [Path(self.sessions_path)] if self.sessions_path else []
        return [Path(p) for p in self.sessions_path if p]


class ProviderConfig(BaseModel):
    """Configuration for LLM or embedding provider."""

    provider: str = "ollama"
    model: str = ""
    base_url: str | None = None


class IndexingConfig(BaseModel):
    """Indexing pipeline configuration."""

    chunk_size: int = 512
    chunk_overlap: int = 128
    batch_size: int = 100
    default_search_results: int = 10
    auto_summarize: bool = True
    auto_tag: bool = True
    auto_title: bool = True


class SearchConfig(BaseModel):
    """Search pipeline configuration."""

    deterministic_enabled: bool = True
    agentic_enabled: bool = False
    max_agent_refinement_rounds: int = 3
    cache_enabled: bool = True
    cache_size: int = 128
    cache_ttl: int = 300  # seconds


class UIConfig(BaseModel):
    """UI/TUI configuration."""

    use_textual: bool = True
    theme: str = "obsidian"
    animation_fps: int = 10
    adaptive_fps: bool = True
    disable_animations: bool = False
    lite_mode: bool = False
