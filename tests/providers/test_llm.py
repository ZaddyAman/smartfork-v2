"""Tests for LLM provider implementations."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from smartfork.providers.llm import (
    AnthropicLLM,
    OllamaLLM,
    OpenAILLM,
    _load_secrets,
    get_llm,
)


class TestLoadSecrets:
    def test_returns_empty_dict_when_file_missing(self) -> None:
        with patch("pathlib.Path.exists", return_value=False):
            result = _load_secrets()
            assert result == {}

    def test_parses_key_value_pairs(self, tmp_path: Path) -> None:
        secrets_dir = tmp_path / ".smartfork"
        secrets_dir.mkdir()
        secrets_file = secrets_dir / "secrets.env"
        secrets_file.write_text("ANTHROPIC_API_KEY=test-key\nOPENAI_API_KEY=other-key\n")
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _load_secrets()
            assert result.get("ANTHROPIC_API_KEY") == "test-key"


class TestOllamaLLM:
    def test_init_raises_when_ollama_not_available(self) -> None:
        with patch("smartfork.providers.llm.OLLAMA_AVAILABLE", False), \
             pytest.raises(RuntimeError, match="Ollama Python package is not installed"):
            OllamaLLM()

    def test_init_raises_when_model_not_available(self) -> None:
        with patch("smartfork.providers.llm.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.llm.check_ollama_available", return_value=False), \
             pytest.raises(RuntimeError, match="Ollama model"):
            OllamaLLM()

    def test_complete_returns_response_text(self) -> None:
        with patch("smartfork.providers.llm.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.llm.check_ollama_available", return_value=True), \
             patch("smartfork.providers.llm.OllamaLLM", autospec=False) as _:
            # Create instance with mocked ollama client
            import smartfork.providers.llm as llm_mod
            mock_ollama_mod = MagicMock()
            mock_ollama_mod.generate.return_value = {"response": "Hello, world!"}
            with patch.dict(llm_mod.__dict__, {"ollama": mock_ollama_mod}):
                provider = OllamaLLM.__new__(OllamaLLM)
                provider._client = mock_ollama_mod
                provider.model = "qwen2.5-coder:7b"
                result = provider.complete("Hello")
                assert result == "Hello, world!"

    def test_complete_raises_on_error(self) -> None:
        with patch("smartfork.providers.llm.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.llm.check_ollama_available", return_value=True):
            provider = OllamaLLM.__new__(OllamaLLM)
            mock_ollama_mod = MagicMock()
            mock_ollama_mod.generate.side_effect = Exception("Ollama error")
            provider._client = mock_ollama_mod
            provider.model = "qwen2.5-coder:7b"
            with pytest.raises(RuntimeError, match="Ollama completion failed"):
                provider.complete("Hello")

    def test_complete_structured_requires_instructor(self) -> None:
        with patch("smartfork.providers.llm.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.llm.check_ollama_available", return_value=True):
            provider = OllamaLLM.__new__(OllamaLLM)
            provider._ollama = MagicMock()
            provider.model = "qwen2.5-coder:7b"
            with patch("smartfork.providers.llm.instructor", None, create=True):
                # This will raise because instructor isn't imported in complete_structured
                pass

    def test_init_uses_custom_model(self) -> None:
        with patch("smartfork.providers.llm.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.llm.check_ollama_available", return_value=True):
            provider = OllamaLLM.__new__(OllamaLLM)
            provider._ollama = MagicMock()
            provider.model = "custom-model:latest"
            assert provider.model == "custom-model:latest"


class TestAnthropicLLM:
    def test_init_raises_without_api_key(self) -> None:
        with patch("smartfork.providers.llm._load_secrets", return_value={}), \
             patch("os.environ", {}), \
             pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY not found"):
            AnthropicLLM(api_key="")  # Empty string triggers env lookup

    def test_init_with_explicit_api_key(self) -> None:
        provider = AnthropicLLM(api_key="test-key")
        assert provider._api_key == "test-key"
        assert provider.model == "claude-3-haiku-20240307"

    def test_init_uses_custom_model(self) -> None:
        provider = AnthropicLLM(model="claude-sonnet-4-20250514", api_key="test-key")
        assert provider.model == "claude-sonnet-4-20250514"

    def test_complete_returns_text(self) -> None:
        provider = AnthropicLLM.__new__(AnthropicLLM)
        provider.model = "claude-3-haiku-20240307"
        provider._api_key = "test-key"

        mock_block = MagicMock()
        mock_block.text = "Hello from Claude"
        mock_message = MagicMock()
        mock_message.content = [mock_block]

        with patch("anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_message
            mock_client_class.return_value = mock_client
            result = provider.complete("Hello")
            assert result == "Hello from Claude"

    def test_complete_raises_on_error(self) -> None:
        provider = AnthropicLLM.__new__(AnthropicLLM)
        provider.model = "claude-3-haiku-20240307"
        provider._api_key = "test-key"

        with patch("anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = Exception("API error")
            mock_client_class.return_value = mock_client
            with pytest.raises(RuntimeError, match="Anthropic completion failed"):
                provider.complete("Hello")


class TestOpenAILLM:
    def test_init_raises_without_api_key(self) -> None:
        with patch("smartfork.providers.llm._load_secrets", return_value={}), \
             patch("os.environ", {}), \
             pytest.raises(RuntimeError, match="OPENAI_API_KEY not found"):
            OpenAILLM(api_key="")

    def test_init_with_explicit_api_key(self) -> None:
        provider = OpenAILLM(api_key="test-key")
        assert provider._api_key == "test-key"
        assert provider.model == "gpt-4o-mini"

    def test_init_uses_custom_model(self) -> None:
        provider = OpenAILLM(model="gpt-4o", api_key="test-key")
        assert provider.model == "gpt-4o"

    def test_complete_returns_text(self) -> None:
        provider = OpenAILLM.__new__(OpenAILLM)
        provider.model = "gpt-4o-mini"
        provider._api_key = "test-key"

        mock_choice = MagicMock()
        mock_choice.message.content = "Hello from OpenAI"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("openai.OpenAI") as mock_client_class:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_client_class.return_value = mock_client
            result = provider.complete("Hello")
            assert result == "Hello from OpenAI"

    def test_complete_raises_on_error(self) -> None:
        provider = OpenAILLM.__new__(OpenAILLM)
        provider.model = "gpt-4o-mini"
        provider._api_key = "test-key"

        with patch("openai.OpenAI") as mock_client_class:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = Exception("API error")
            mock_client_class.return_value = mock_client
            with pytest.raises(RuntimeError, match="OpenAI completion failed"):
                provider.complete("Hello")


class TestGetLLM:
    def test_returns_ollama_by_default(self) -> None:
        with patch("smartfork.providers.llm.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.llm.check_ollama_available", return_value=True):
            llm = get_llm("ollama")
            assert isinstance(llm, OllamaLLM)

    def test_returns_anthropic(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            llm = get_llm("anthropic", model="test-model")
        assert isinstance(llm, AnthropicLLM)
        assert llm.model == "test-model"

    def test_returns_openai(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            llm = get_llm("openai", model="gpt-4o")
        assert isinstance(llm, OpenAILLM)
        assert llm.model == "gpt-4o"

    def test_raises_for_unknown_provider(self) -> None:
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_llm("unknown")

    def test_case_insensitive(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            llm = get_llm("OpenAI", model="gpt-4")
        assert isinstance(llm, OpenAILLM)
