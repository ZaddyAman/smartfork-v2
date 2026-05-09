# SmartFork v2 — Configuration System (Layer 0)

> **Build target:** TOML-based config with Pydantic validation, secrets management, multi-agent support.
> **Design:** TOML-based config with Pydantic validation, secrets management, multi-agent support.

---

## Design

SmartFork v2 uses **TOML** for configuration (not JSON). Two files:

1. `~/.smartfork/config.toml` — All user-facing config (human-readable)
2. `~/.smartfork/secrets.env` — API keys (never committed, file permissions 0o600 on Unix)

Config is loaded via Pydantic `BaseSettings` for env var override support (`SMARTFORK_` prefix).

---

## Config Model

### File: `src/smartfork/config.py`

```toml
# ~/.smartfork/config.toml — Example

[core]
theme = "obsidian"
log_level = "INFO"
schema_version = 2

[agents]
default = "kilocode"

[agents.kilocode]
enabled = true
sessions_path = "C:\\Users\\...\\Cursor\\User\\globalStorage\\kilocode.kilo-code\\tasks"
ide = "Cursor"

[agents.claudecode]
enabled = false
sessions_path = "~/.claude/projects"

[agents.opencode]
enabled = false
sessions_path = "~/.local/share/opencode/opencode.db"

[paths]
sqlite_db = "~/.smartfork/metadata.db"
qdrant_db = "~/.smartfork/qdrant_db"
cache_dir = "~/.smartfork/cache"

[models]
embedding_provider = "ollama"
embedding_model = "qwen3-embedding:0.6b"
embedding_dimensions = 512
llm_provider = "ollama"
llm_model = "qwen2.5-coder:7b"

[indexing]
chunk_size = 512
chunk_overlap = 128
default_search_results = 10

[performance]
lite_mode = false
animation_fps = 10
disable_animations = false
batch_size = 100
enable_search_cache = true
search_cache_size = 128
search_cache_ttl = 300
adaptive_fps = true
```

### Pydantic Model

```python
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Optional, Dict, Union, List

class AgentConfig(BaseModel):
    enabled: bool = False
    sessions_path: Union[str, List[str]] = ""
    ide: Optional[str] = None
    
    def get_paths(self) -> List[Path]:
        """Return paths as list, handling both string and list formats."""

class SmartForkConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SMARTFORK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # Agents
    agents: Dict[str, AgentConfig] = Field(default_factory=dict)
    default_agent: Optional[str] = None
    
    # Storage
    sqlite_db_path: Path = Field(default=CONFIG_DIR / "metadata.db")
    qdrant_db_path: Path = Field(default=CONFIG_DIR / "qdrant_db")
    cache_dir: Path = Field(default=CONFIG_DIR / "cache")
    
    # Logging
    log_level: str = "INFO"
    log_file: Optional[Path] = None
    
    # Theme
    theme: str = "obsidian"
    
    # Models
    embedding_provider: str = "ollama"
    embedding_model: str = "qwen3-embedding:0.6b"
    embedding_dimensions: int = 512
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5-coder:7b"
    llm_base_url: Optional[str] = None
    
    # Indexing
    chunk_size: int = 512
    chunk_overlap: int = 128
    default_search_results: int = 10
    
    # Performance
    lite_mode: bool = False
    animation_fps: int = 10
    disable_animations: bool = False
    batch_size: int = 100
    enable_search_cache: bool = True
    search_cache_size: int = 128
    search_cache_ttl: int = 300
    adaptive_fps: bool = True
    
    # Validators
    @validator("theme")
    def validate_theme(cls, v):
        valid = {"phosphor", "obsidian", "ember", "arctic", "iron", "tungsten"}
        if v.lower() not in valid:
            raise ValueError(f"Unknown theme '{v}'. Valid: {', '.join(sorted(valid))}")
        return v.lower()
    
    # Methods
    def save(self) -> None: ...
    
    @classmethod
    def load(cls) -> "SmartForkConfig": ...
    
    def get_secret(self, key: str) -> Optional[str]: ...
    def set_secret(self, key: str, value: str) -> None: ...
    
    # Legacy compat
    @property
    def kilo_code_tasks_path(self) -> Path:
        """Legacy: returns first enabled Kilo Code path."""
```

---

## Secrets Management

### File: `~/.smartfork/secrets.env`

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

- Never committed to git. Always in `.gitignore`.
- On Unix: file permissions set to `0o600` (owner read/write only)
- On Windows: no permission change (handled by user directory ACLs)
- `get_secret()` checks: environment variable → secrets.env file → None
- `set_secret()` writes to secrets.env, preserves other entries

---

## Legacy Migration

When SmartFork v2 first runs:

1. Check for `~/.smartfork/config.json` (v1 format)
2. If found and `config.toml` doesn't exist: auto-migrate
3. Migration converts JSON → TOML, adds new fields with defaults
4. Old Kilo Code path → `agents.kilocode.enabled = true`
5. Save as `config.toml`, keep `config.json` as backup
6. Log migration event

---

## Singleton Pattern

```python
_config: Optional[SmartForkConfig] = None

def get_config() -> SmartForkConfig:
    """Lazy-load and cache config."""
    global _config
    if _config is None:
        _config = SmartForkConfig.load()
    return _config

def reload_config() -> SmartForkConfig:
    """Force reload (after user changes)."""
    global _config
    _config = SmartForkConfig.load()
    return _config
```

---

## Path Constants

```python
CONFIG_DIR = Path.home() / ".smartfork"
CONFIG_FILE = CONFIG_DIR / "config.toml"
SECRETS_FILE = CONFIG_DIR / "secrets.env"
```

Create `CONFIG_DIR` on first access if it doesn't exist.

---

## Setup Wizard Integration

The setup wizard (`smartfork setup`) uses this config system:
1. Detects installed coding agents → enables their config
2. Asks for API keys → stores in secrets.env
3. Checks Ollama models → recommends which to pull
4. Saves config.toml
5. Confirms "SmartFork is ready. Run smartfork index to begin."

---

## Implementation Order for Ralph

1. `config.py` — SmartForkConfig, AgentConfig, get_config(), reload_config()
2. `config.py` — save(), load(), get_secret(), set_secret()
3. Legacy migration logic (config.json → config.toml)
4. Setup wizard integration points
