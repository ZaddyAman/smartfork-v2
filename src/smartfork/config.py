"""Configuration system for SmartFork v2."""

import json
import os
import tomllib
from pathlib import Path
from typing import Any

import tomli_w
from loguru import logger
from pydantic import Field, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import PydanticBaseSettingsSource

from smartfork.models.config import AgentConfig

CONFIG_DIR = Path.home() / ".smartfork"
CONFIG_FILE = CONFIG_DIR / "config.toml"
SECRETS_FILE = CONFIG_DIR / "secrets.env"

VALID_LLM_PROVIDERS: set[str] = {
    "ollama",
    "anthropic",
    "openai",
    "opencode",
    "go",
    "zen",
    "openrouter",
    "groq",
    "gemini",
    "together",
    "mistral",
    "deepseek",
    "fireworks",
    "cohere",
    "xai",
    "perplexity",
}


class _TomlConfigSettingsSource(PydanticBaseSettingsSource):
    """Custom settings source that loads values from config.toml."""

    def __init__(
        self, settings_cls: type[BaseSettings], toml_data: dict[str, Any]
    ) -> None:
        super().__init__(settings_cls)
        self.toml_data = toml_data

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        field_value = self.toml_data.get(field_name)
        return field_value, field_name, False

    def __call__(self) -> dict[str, Any]:
        return self.toml_data


class SmartForkConfig(BaseSettings):
    """SmartFork v2 configuration backed by TOML with env-var override."""

    model_config = SettingsConfigDict(
        env_prefix="SMARTFORK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Custom source order: init kwargs > env vars > .env > TOML > defaults."""
        toml_data: dict[str, Any] = {}
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "rb") as f:
                    data = tomllib.load(f)
                toml_data = cls._flatten_toml(data)
            except Exception as exc:
                logger.warning(
                    f"Failed to parse config file {CONFIG_FILE}: {exc}. Using defaults."
                )

        return (
            init_settings,
            env_settings,
            dotenv_settings,
            _TomlConfigSettingsSource(settings_cls, toml_data),
            file_secret_settings,
        )

    # Agents
    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    default_agent: str | None = None

    # Storage
    sqlite_db_path: Path = CONFIG_DIR / "metadata.db"
    qdrant_db_path: Path = CONFIG_DIR / "qdrant_db"
    cache_dir: Path = CONFIG_DIR / "cache"

    # Logging
    log_level: str = "INFO"
    log_file: Path | None = None

    # Theme
    theme: str = "obsidian"

    # Models
    embedding_provider: str = "ollama"
    embedding_model: str = "qwen3-embedding:0.6b"
    embedding_dimensions: int = 1024
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5-coder:7b"
    llm_base_url: str | None = None

    strategic_llm_provider: str | None = None
    strategic_llm_model: str | None = None
    strategic_llm_base_url: str | None = None
    smart_llm_provider: str | None = None
    smart_llm_model: str | None = None
    smart_llm_base_url: str | None = None

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

    # Schema
    schema_version: int = 3

    # ------------------------------------------------------------------ #
    # Validators
    # ------------------------------------------------------------------ #

    @field_validator("theme")
    @classmethod
    def _validate_theme(cls, v: str) -> str:
        valid = {"phosphor", "obsidian", "ember", "arctic", "iron", "tungsten"}
        lowered = v.lower()
        if lowered not in valid:
            raise ValueError(
                f"Unknown theme '{v}'. Valid: {', '.join(sorted(valid))}"
            )
        return lowered

    @field_validator(
        "sqlite_db_path", "qdrant_db_path", "cache_dir", "log_file"
    )
    @classmethod
    def _expand_paths(cls, v: Any) -> Any:
        if v is None:
            return None
        p = Path(v)
        if str(v).startswith("~"):
            p = p.expanduser()
        return p

    @model_validator(mode="after")
    def _backfill_tiered_llms(self) -> "SmartForkConfig":
        provider_fields = (
            "llm_provider",
            "strategic_llm_provider",
            "smart_llm_provider",
        )
        for field_name in provider_fields:
            value = getattr(self, field_name)
            if value is not None:
                lowered = value.lower()
                if lowered not in VALID_LLM_PROVIDERS:
                    raise ValueError(
                        f"Unknown LLM provider '{value}' in {field_name}. "
                        f"Valid: {', '.join(sorted(VALID_LLM_PROVIDERS))}"
                    )
                setattr(self, field_name, lowered)

        if self.strategic_llm_provider is None:
            self.strategic_llm_provider = self.llm_provider
        if self.strategic_llm_model is None:
            self.strategic_llm_model = self.llm_model
        if self.strategic_llm_base_url is None:
            self.strategic_llm_base_url = self.llm_base_url
        if self.smart_llm_provider is None:
            self.smart_llm_provider = self.llm_provider
        if self.smart_llm_model is None:
            self.smart_llm_model = self.llm_model
        if self.smart_llm_base_url is None:
            self.smart_llm_base_url = self.llm_base_url
        return self

    # ------------------------------------------------------------------ #
    # Load / Save
    # ------------------------------------------------------------------ #

    @classmethod
    def load(cls) -> "SmartForkConfig":
        """Load from TOML, migrating legacy JSON if needed."""
        cls._migrate_legacy()

        if not CONFIG_FILE.exists():
            logger.info(f"Config file not found at {CONFIG_FILE}, using defaults")
            instance = cls()
            instance.save()
            return instance

        try:
            return cls()
        except Exception as exc:
            logger.warning(
                f"Failed to load config from {CONFIG_FILE}: {exc}. Using defaults."
            )
            return cls()

    @classmethod
    def _flatten_toml(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Flatten nested TOML sections into flat kwargs."""
        flat: dict[str, Any] = {}

        # Core
        if "core" in data:
            for key in ("theme", "log_level", "log_file", "schema_version"):
                if key in data["core"]:
                    flat[key] = data["core"][key]

        # Agents: "default" key maps to default_agent; the rest are configs.
        if "agents" in data:
            agents_data = dict(data["agents"])
            if "default" in agents_data:
                flat["default_agent"] = agents_data.pop("default")
            flat["agents"] = {
                k: v for k, v in agents_data.items() if isinstance(v, dict)
            }

        # Paths
        if "paths" in data:
            path_map = {
                "sqlite_db": "sqlite_db_path",
                "qdrant_db": "qdrant_db_path",
                "cache_dir": "cache_dir",
            }
            for toml_key, field_name in path_map.items():
                if toml_key in data["paths"]:
                    flat[field_name] = data["paths"][toml_key]

        # Models
        if "models" in data:
            for key in (
                "embedding_provider",
                "embedding_model",
                "embedding_dimensions",
                "llm_provider",
                "llm_model",
                "llm_base_url",
                "strategic_llm_provider",
                "strategic_llm_model",
                "strategic_llm_base_url",
                "smart_llm_provider",
                "smart_llm_model",
                "smart_llm_base_url",
            ):
                if key in data["models"]:
                    flat[key] = data["models"][key]

        # Indexing
        if "indexing" in data:
            for key in ("chunk_size", "chunk_overlap", "default_search_results"):
                if key in data["indexing"]:
                    flat[key] = data["indexing"][key]

        # Performance
        if "performance" in data:
            for key in (
                "lite_mode",
                "animation_fps",
                "disable_animations",
                "batch_size",
                "enable_search_cache",
                "search_cache_size",
                "search_cache_ttl",
                "adaptive_fps",
            ):
                if key in data["performance"]:
                    flat[key] = data["performance"][key]

        return flat

    def save(self) -> None:
        """Persist configuration as nested TOML."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = self._to_nested_dict()
        with open(CONFIG_FILE, "wb") as f:
            tomli_w.dump(data, f)
        logger.debug(f"Config saved to {CONFIG_FILE}")

    def _to_nested_dict(self) -> dict[str, Any]:
        """Convert instance to nested TOML-compatible dict."""
        core: dict[str, Any] = {
            "schema_version": self.schema_version,
            "theme": self.theme,
            "log_level": self.log_level,
        }
        if self.log_file is not None:
            core["log_file"] = str(self.log_file)

        agents: dict[str, Any] = {}
        if self.default_agent is not None:
            agents["default"] = self.default_agent
        for name, cfg in self.agents.items():
            agents[name] = cfg.model_dump()

        paths = {
            "sqlite_db": str(self.sqlite_db_path),
            "qdrant_db": str(self.qdrant_db_path),
            "cache_dir": str(self.cache_dir),
        }

        models: dict[str, Any] = {
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "embedding_dimensions": self.embedding_dimensions,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "strategic_llm_provider": self.strategic_llm_provider,
            "strategic_llm_model": self.strategic_llm_model,
            "smart_llm_provider": self.smart_llm_provider,
            "smart_llm_model": self.smart_llm_model,
        }
        if self.llm_base_url is not None:
            models["llm_base_url"] = self.llm_base_url
        if self.strategic_llm_base_url is not None:
            models["strategic_llm_base_url"] = self.strategic_llm_base_url
        if self.smart_llm_base_url is not None:
            models["smart_llm_base_url"] = self.smart_llm_base_url

        indexing = {
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "default_search_results": self.default_search_results,
        }

        performance = {
            "lite_mode": self.lite_mode,
            "animation_fps": self.animation_fps,
            "disable_animations": self.disable_animations,
            "batch_size": self.batch_size,
            "enable_search_cache": self.enable_search_cache,
            "search_cache_size": self.search_cache_size,
            "search_cache_ttl": self.search_cache_ttl,
            "adaptive_fps": self.adaptive_fps,
        }

        return {
            "core": core,
            "agents": agents,
            "paths": paths,
            "models": models,
            "indexing": indexing,
            "performance": performance,
        }

    # ------------------------------------------------------------------ #
    # Secrets
    # ------------------------------------------------------------------ #

    def get_secret(self, key: str) -> str | None:
        """Check environment, then secrets file, returning None if missing."""
        if key in os.environ:
            return os.environ[key]

        if not SECRETS_FILE.exists():
            return None

        try:
            with open(SECRETS_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == key:
                            return v.strip()
        except OSError:
            logger.warning(f"Could not read secrets file {SECRETS_FILE}")

        return None

    def set_secret(self, key: str, value: str) -> None:
        """Write a secret, preserving existing entries."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        secrets: dict[str, str] = {}
        if SECRETS_FILE.exists():
            try:
                with open(SECRETS_FILE, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            secrets[k.strip()] = v.strip()
            except OSError:
                logger.warning(f"Could not read secrets file {SECRETS_FILE}")

        secrets[key] = value

        with open(SECRETS_FILE, "w", encoding="utf-8") as f:
            for k, v in secrets.items():
                f.write(f"{k}={v}\n")

        if os.name != "nt":
            try:
                os.chmod(SECRETS_FILE, 0o600)
            except OSError:
                logger.warning(f"Could not set permissions on {SECRETS_FILE}")

    # ------------------------------------------------------------------ #
    # Legacy migration
    # ------------------------------------------------------------------ #

    @classmethod
    def _migrate_legacy(cls) -> None:
        """Migrate ~/.smartfork/config.json to config.toml if present."""
        legacy_file = CONFIG_DIR / "config.json"
        if not legacy_file.exists() or CONFIG_FILE.exists():
            return

        logger.info(f"Migrating legacy config from {legacy_file}")

        try:
            with open(legacy_file, encoding="utf-8") as f:
                old = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"Failed to read legacy config: {exc}")
            return

        agents: dict[str, Any] = {}
        default_agent = old.get("default_agent")

        # Map legacy kilo_code path
        kilo_path = (
            old.get("kilo_code_tasks_path")
            or old.get("tasks_path")
            or old.get("kilocode_path")
        )
        if kilo_path:
            agents["kilocode"] = {
                "enabled": True,
                "sessions_path": kilo_path,
                "ide": old.get("ide", "Cursor"),
            }

        # Preserve any pre-existing nested agents block
        if "agents" in old and isinstance(old["agents"], dict):
            for name, cfg in old["agents"].items():
                if isinstance(cfg, dict):
                    agents[name] = cfg

        flat: dict[str, Any] = {"agents": agents}
        if default_agent is not None:
            flat["default_agent"] = default_agent

        simple_fields = {
            "sqlite_db_path",
            "qdrant_db_path",
            "cache_dir",
            "log_level",
            "log_file",
            "theme",
            "embedding_provider",
            "embedding_model",
            "embedding_dimensions",
            "llm_provider",
            "llm_model",
            "llm_base_url",
            "strategic_llm_provider",
            "strategic_llm_model",
            "strategic_llm_base_url",
            "smart_llm_provider",
            "smart_llm_model",
            "smart_llm_base_url",
            "chunk_size",
            "chunk_overlap",
            "default_search_results",
            "lite_mode",
            "animation_fps",
            "disable_animations",
            "batch_size",
            "enable_search_cache",
            "search_cache_size",
            "search_cache_ttl",
            "adaptive_fps",
            "schema_version",
        }
        for key in simple_fields:
            if key in old:
                flat[key] = old[key]

        try:
            instance = cls(**flat)
            instance.save()
        except Exception as exc:
            logger.warning(f"Failed to migrate legacy config: {exc}")
            return

        backup = legacy_file.with_suffix(".json.bak")
        try:
            legacy_file.rename(backup)
            logger.info(f"Legacy config backed up to {backup}")
        except OSError as exc:
            logger.warning(f"Could not backup legacy config: {exc}")

    # ------------------------------------------------------------------ #
    # Legacy compat
    # ------------------------------------------------------------------ #

    @property
    def kilo_code_tasks_path(self) -> Path:
        """Return first enabled Kilo Code path, or Path('.')."""
        for name, cfg in self.agents.items():
            if name.lower() in {"kilocode", "kilo_code"} and cfg.enabled:
                paths = cfg.get_paths()
                if paths:
                    return paths[0]
        return Path(".")


# ---------------------------------------------------------------------- #
# Singleton
# ---------------------------------------------------------------------- #

_config: SmartForkConfig | None = None


def get_config() -> SmartForkConfig:
    """Lazy-load and cache config."""
    global _config
    if _config is None:
        _config = SmartForkConfig.load()
    return _config


def reload_config() -> SmartForkConfig:
    """Force reload config from disk."""
    global _config
    _config = SmartForkConfig.load()
    return _config
