"""Tests for config models."""

from pathlib import Path

from smartfork.models.config import AgentConfig, IndexingConfig, ProviderConfig, SearchConfig, UIConfig


class TestAgentConfig:
    def test_defaults(self) -> None:
        cfg = AgentConfig()
        assert cfg.enabled is False
        assert cfg.sessions_path == ""
        assert cfg.ide is None

    def test_get_paths_single_string(self) -> None:
        cfg = AgentConfig(sessions_path="/tmp/sessions")
        assert cfg.get_paths() == [Path("/tmp/sessions")]

    def test_get_paths_list(self) -> None:
        cfg = AgentConfig(sessions_path=["/a", "/b"])
        assert cfg.get_paths() == [Path("/a"), Path("/b")]

    def test_get_paths_empty_string(self) -> None:
        cfg = AgentConfig(sessions_path="")
        assert cfg.get_paths() == []

    def test_get_paths_empty_list(self) -> None:
        cfg = AgentConfig(sessions_path=[])
        assert cfg.get_paths() == []

    def test_get_paths_mixed_list_empty_strings(self) -> None:
        cfg = AgentConfig(sessions_path=["/a", "", "/b"])
        assert cfg.get_paths() == [Path("/a"), Path("/b")]


class TestProviderConfig:
    def test_defaults(self) -> None:
        cfg = ProviderConfig()
        assert cfg.provider == "ollama"
        assert cfg.model == ""
        assert cfg.base_url is None

    def test_custom(self) -> None:
        cfg = ProviderConfig(provider="openai", model="gpt-4o", base_url="https://api.openai.com")
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o"


class TestIndexingConfig:
    def test_defaults(self) -> None:
        cfg = IndexingConfig()
        assert cfg.chunk_size == 512
        assert cfg.chunk_overlap == 128
        assert cfg.batch_size == 100
        assert cfg.auto_tag is True

    def test_custom(self) -> None:
        cfg = IndexingConfig(chunk_size=256, auto_summarize=False)
        assert cfg.chunk_size == 256
        assert cfg.auto_summarize is False


class TestSearchConfig:
    def test_defaults(self) -> None:
        cfg = SearchConfig()
        assert cfg.deterministic_enabled is True
        assert cfg.agentic_enabled is False
        assert cfg.cache_ttl == 300

    def test_custom(self) -> None:
        cfg = SearchConfig(agentic_enabled=True, max_agent_refinement_rounds=5)
        assert cfg.agentic_enabled is True
        assert cfg.max_agent_refinement_rounds == 5


class TestUIConfig:
    def test_defaults(self) -> None:
        cfg = UIConfig()
        assert cfg.theme == "obsidian"
        assert cfg.use_textual is True
        assert cfg.lite_mode is False

    def test_custom(self) -> None:
        cfg = UIConfig(theme="phosphor", disable_animations=True)
        assert cfg.theme == "phosphor"
        assert cfg.disable_animations is True
