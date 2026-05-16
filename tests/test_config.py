"""Tests for SmartFork v2 configuration system."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import tomli


class TestConfigDefaults:
    """Tests for default config values."""

    @patch("pathlib.Path.home", return_value=Path("/tmp/fake_home"))
    def test_default_theme_is_obsidian(self, mock_home: Path) -> None:
        from smartfork.config import SmartForkConfig
        cfg = SmartForkConfig()
        assert cfg.theme == "obsidian"

    @patch("pathlib.Path.home", return_value=Path("/tmp/fake_home"))
    def test_default_llm_provider_is_ollama(self, mock_home: Path) -> None:
        from smartfork.config import SmartForkConfig
        cfg = SmartForkConfig()
        assert cfg.llm_provider == "ollama"

    @patch("pathlib.Path.home", return_value=Path("/tmp/fake_home"))
    def test_default_embedding_dimensions_is_512(self, mock_home: Path) -> None:
        from smartfork.config import SmartForkConfig
        cfg = SmartForkConfig()
        assert cfg.embedding_dimensions == 512

    @patch("pathlib.Path.home", return_value=Path("/tmp/fake_home"))
    def test_agents_default_to_empty_dict(self, mock_home: Path) -> None:
        from smartfork.config import SmartForkConfig
        cfg = SmartForkConfig()
        assert cfg.agents == {}


class TestThemeValidation:
    """Tests for theme field validation."""

    @patch("pathlib.Path.home", return_value=Path("/tmp/fake_home"))
    def test_all_valid_themes_accepted(self, mock_home: Path) -> None:
        from smartfork.config import SmartForkConfig
        valid_themes = ["phosphor", "obsidian", "ember", "arctic", "iron", "tungsten"]
        for theme in valid_themes:
            cfg = SmartForkConfig(theme=theme)
            assert cfg.theme == theme

    @patch("pathlib.Path.home", return_value=Path("/tmp/fake_home"))
    def test_invalid_theme_raises_value_error(self, mock_home: Path) -> None:
        from smartfork.config import SmartForkConfig
        with pytest.raises(ValueError, match="Unknown theme"):
            SmartForkConfig(theme="blueberry")

    @patch("pathlib.Path.home", return_value=Path("/tmp/fake_home"))
    def test_theme_is_case_insensitive(self, mock_home: Path) -> None:
        from smartfork.config import SmartForkConfig
        cfg = SmartForkConfig(theme="OBSIDIAN")
        assert cfg.theme == "obsidian"


class TestSaveLoadRoundTrip:
    """Tests for save/load round-trip."""

    def test_save_and_load_preserves_values(self, tmp_path: Path) -> None:
        from smartfork.config import SmartForkConfig

        with patch("smartfork.config.CONFIG_DIR", tmp_path), \
             patch("smartfork.config.CONFIG_FILE", tmp_path / "config.toml"), \
             patch("pathlib.Path.home", return_value=tmp_path):
            cfg = SmartForkConfig(
                theme="phosphor",
                llm_provider="anthropic",
                llm_model="claude-3-haiku-20240307",
                chunk_size=256,
                default_agent="kilocode",
            )
            cfg.save()

            loaded = SmartForkConfig.load()
            assert loaded.theme == "phosphor"
            assert loaded.llm_provider == "anthropic"
            assert loaded.llm_model == "claude-3-haiku-20240307"
            assert loaded.chunk_size == 256
            assert loaded.default_agent == "kilocode"

    def test_save_creates_config_dir(self, tmp_path: Path) -> None:
        from smartfork.config import SmartForkConfig

        config_dir = tmp_path / "new_config_dir"
        config_file = config_dir / "config.toml"

        with patch("smartfork.config.CONFIG_DIR", config_dir), \
             patch("smartfork.config.CONFIG_FILE", config_file), \
             patch("pathlib.Path.home", return_value=tmp_path):
            cfg = SmartForkConfig(theme="ember")
            cfg.save()
            assert config_file.exists()

    def test_load_returns_defaults_when_file_missing(self, tmp_path: Path) -> None:
        from smartfork.config import SmartForkConfig

        nonexistent = tmp_path / "nonexistent.toml"
        with patch("smartfork.config.CONFIG_DIR", tmp_path), \
             patch("smartfork.config.CONFIG_FILE", nonexistent), \
             patch("pathlib.Path.home", return_value=tmp_path):
            cfg = SmartForkConfig.load()
            assert cfg.theme == "obsidian"

    def test_save_produces_valid_toml(self, tmp_path: Path) -> None:
        from smartfork.config import SmartForkConfig

        config_file = tmp_path / "config.toml"
        with patch("smartfork.config.CONFIG_DIR", tmp_path), \
             patch("smartfork.config.CONFIG_FILE", config_file), \
             patch("pathlib.Path.home", return_value=tmp_path):
            cfg = SmartForkConfig(theme="arctic", log_level="DEBUG")
            cfg.save()

            with open(config_file, "rb") as f:
                data = tomli.load(f)
            assert "core" in data
            assert data["core"]["theme"] == "arctic"
            assert data["core"]["log_level"] == "DEBUG"


class TestSecrets:
    """Tests for get_secret / set_secret."""

    def test_get_secret_from_env(self, tmp_path: Path) -> None:
        from smartfork.config import SmartForkConfig

        with patch("smartfork.config.CONFIG_DIR", tmp_path), \
             patch("smartfork.config.SECRETS_FILE", tmp_path / "secrets.env"), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key-value"}, clear=False):
            cfg = SmartForkConfig()
            result = cfg.get_secret("ANTHROPIC_API_KEY")
            assert result == "env-key-value"

    def test_get_secret_from_file(self, tmp_path: Path) -> None:
        from smartfork.config import SmartForkConfig

        secrets_file = tmp_path / "secrets.env"
        secrets_file.write_text("OPENAI_API_KEY=file-key-value\n")

        with patch("smartfork.config.CONFIG_DIR", tmp_path), \
             patch("smartfork.config.SECRETS_FILE", secrets_file), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch.dict(os.environ, {}, clear=True):
            cfg = SmartForkConfig()
            result = cfg.get_secret("OPENAI_API_KEY")
            assert result == "file-key-value"

    def test_get_secret_returns_none_when_missing(self, tmp_path: Path) -> None:
        from smartfork.config import SmartForkConfig

        with patch("smartfork.config.CONFIG_DIR", tmp_path), \
             patch("smartfork.config.SECRETS_FILE", tmp_path / "nonexistent.env"), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch.dict(os.environ, {}, clear=True):
            cfg = SmartForkConfig()
            result = cfg.get_secret("NONEXISTENT_KEY")
            assert result is None

    def test_set_secret_creates_file(self, tmp_path: Path) -> None:
        from smartfork.config import SmartForkConfig

        secrets_file = tmp_path / "secrets.env"
        with patch("smartfork.config.CONFIG_DIR", tmp_path), \
             patch("smartfork.config.SECRETS_FILE", secrets_file), \
             patch("pathlib.Path.home", return_value=tmp_path):
            cfg = SmartForkConfig()
            cfg.set_secret("OPENAI_API_KEY", "my-secret-key")
            content = secrets_file.read_text()
            assert "OPENAI_API_KEY=my-secret-key" in content

    def test_set_secret_preserves_other_entries(self, tmp_path: Path) -> None:
        from smartfork.config import SmartForkConfig

        secrets_file = tmp_path / "secrets.env"
        secrets_file.write_text("ANTHROPIC_API_KEY=existing-key\nOTHER_KEY=other-val\n")

        with patch("smartfork.config.CONFIG_DIR", tmp_path), \
             patch("smartfork.config.SECRETS_FILE", secrets_file), \
             patch("pathlib.Path.home", return_value=tmp_path):
            cfg = SmartForkConfig()
            cfg.set_secret("OPENAI_API_KEY", "new-key")
            content = secrets_file.read_text()
            assert "ANTHROPIC_API_KEY=existing-key" in content
            assert "OPENAI_API_KEY=new-key" in content

    def test_set_secret_updates_existing_key(self, tmp_path: Path) -> None:
        from smartfork.config import SmartForkConfig

        secrets_file = tmp_path / "secrets.env"
        secrets_file.write_text("OPENAI_API_KEY=old-key\n")

        with patch("smartfork.config.CONFIG_DIR", tmp_path), \
             patch("smartfork.config.SECRETS_FILE", secrets_file), \
             patch("pathlib.Path.home", return_value=tmp_path):
            cfg = SmartForkConfig()
            cfg.set_secret("OPENAI_API_KEY", "updated-key")
            content = secrets_file.read_text()
            assert "OPENAI_API_KEY=updated-key" in content
            assert "old-key" not in content


class TestLegacyMigration:
    """Tests for config.json → config.toml migration."""

    def test_migrates_json_to_toml(self, tmp_path: Path) -> None:
        from smartfork.config import SmartForkConfig

        legacy_json = tmp_path / "config.json"
        legacy_json.write_text(json.dumps({
            "theme": "phosphor",
            "kilocode_path": "/old/kilocode/path",
            "ollama_model": "llama3.2:3b",
        }))

        config_toml = tmp_path / "config.toml"

        with patch("smartfork.config.CONFIG_DIR", tmp_path), \
             patch("smartfork.config.CONFIG_FILE", config_toml), \
             patch("pathlib.Path.home", return_value=tmp_path):
            cfg = SmartForkConfig.load()
            assert "kilocode" in cfg.agents
            assert cfg.agents["kilocode"].enabled is True

    def test_no_migration_when_toml_exists(self, tmp_path: Path) -> None:
        from smartfork.config import SmartForkConfig

        legacy_json = tmp_path / "config.json"
        legacy_json.write_text(json.dumps({"theme": "phosphor"}))

        config_toml = tmp_path / "config.toml"
        config_toml.write_text('[core]\ntheme = "iron"\n')

        with patch("smartfork.config.CONFIG_DIR", tmp_path), \
             patch("smartfork.config.CONFIG_FILE", config_toml), \
             patch("pathlib.Path.home", return_value=tmp_path):
            cfg = SmartForkConfig.load()
            assert cfg.theme == "iron"


class TestSingleton:
    """Tests for get_config / reload_config singletons."""

    @patch("pathlib.Path.home", return_value=Path("/tmp/fake_home"))
    def test_get_config_returns_same_instance(self, mock_home: Path) -> None:
        from smartfork import config as config_mod
        # Force fresh state
        config_mod._config = None

        cfg1 = config_mod.get_config()
        cfg2 = config_mod.get_config()
        assert cfg1 is cfg2

    @patch("pathlib.Path.home", return_value=Path("/tmp/fake_home"))
    def test_reload_config_returns_new_instance(self, mock_home: Path) -> None:
        from smartfork import config as config_mod
        config_mod._config = None

        cfg1 = config_mod.get_config()
        cfg2 = config_mod.reload_config()
        assert cfg1 is not cfg2


class TestLegacyProperty:
    """Tests for kilo_code_tasks_path legacy property."""

    @patch("pathlib.Path.home", return_value=Path("/tmp/fake_home"))
    def test_returns_path_when_kilocode_enabled(self, mock_home: Path) -> None:
        from smartfork.config import SmartForkConfig
        from smartfork.models.config import AgentConfig

        agent = AgentConfig(enabled=True, sessions_path="/test/path")
        cfg = SmartForkConfig(agents={"kilocode": agent})
        result = cfg.kilo_code_tasks_path
        assert result == Path("/test/path")

    @patch("pathlib.Path.home", return_value=Path("/tmp/fake_home"))
    def test_returns_default_when_no_kilocode(self, mock_home: Path) -> None:
        from smartfork.config import SmartForkConfig

        cfg = SmartForkConfig(agents={})
        result = cfg.kilo_code_tasks_path
        # Default should be resolvable
        assert isinstance(result, Path)
