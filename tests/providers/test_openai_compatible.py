"""Tests for OpenAICompatibleLLM provider."""

from unittest.mock import MagicMock, patch

import instructor
import pytest
from pydantic import BaseModel

from smartfork.providers.llm import OpenAICompatibleLLM


class DummyOutput(BaseModel):
    answer: str


class TestOpenAICompatibleLLMInit:
    def test_init_raises_without_api_key(self) -> None:
        with (
            patch("smartfork.providers.llm._load_secrets", return_value={}),
            patch("os.environ", {}),
            pytest.raises(RuntimeError, match="OPENAI_COMPATIBLE_API_KEY not found"),
        ):
            OpenAICompatibleLLM(model="test-model")

    def test_init_with_explicit_api_key(self) -> None:
        provider = OpenAICompatibleLLM(model="test-model", api_key="explicit-key")
        assert provider._api_key == "explicit-key"
        assert provider.model == "test-model"
        assert provider._base_url is None
        assert provider._provider_name == "openai-compatible"

    def test_init_reads_from_secrets(self) -> None:
        with (
            patch(
                "smartfork.providers.llm._load_secrets",
                return_value={"OPENAI_COMPATIBLE_API_KEY": "secret-key"},
            ),
            patch("os.environ", {}),
        ):
            provider = OpenAICompatibleLLM(model="test-model")
            assert provider._api_key == "secret-key"

    def test_init_reads_from_env(self) -> None:
        with patch.dict("os.environ", {"OPENAI_COMPATIBLE_API_KEY": "env-key"}):
            provider = OpenAICompatibleLLM(model="test-model")
            assert provider._api_key == "env-key"

    def test_init_custom_provider_name_env_var(self) -> None:
        with patch.dict("os.environ", {"MY_PROVIDER_API_KEY": "my-key"}):
            provider = OpenAICompatibleLLM(
                model="test-model", provider_name="my-provider"
            )
            assert provider._api_key == "my-key"
            assert provider._provider_name == "my-provider"

    def test_init_custom_provider_name_raises_without_key(self) -> None:
        with (
            patch("smartfork.providers.llm._load_secrets", return_value={}),
            patch("os.environ", {}),
            pytest.raises(RuntimeError, match="MY_PROVIDER_API_KEY not found"),
        ):
            OpenAICompatibleLLM(model="test-model", provider_name="my-provider")

    def test_init_base_url_stored(self) -> None:
        provider = OpenAICompatibleLLM(
            model="test-model",
            api_key="key",
            base_url="http://localhost:1234/v1",
        )
        assert provider._base_url == "http://localhost:1234/v1"


class TestOpenAICompatibleLLMComplete:
    def test_complete_returns_text(self) -> None:
        provider = OpenAICompatibleLLM.__new__(OpenAICompatibleLLM)
        provider.model = "test-model"
        provider._api_key = "test-key"
        provider._base_url = "http://localhost:1234/v1"
        provider._provider_name = "openai-compatible"

        mock_choice = MagicMock()
        mock_choice.message.content = "Hello from compatible API"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("openai.OpenAI") as mock_client_class:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = provider.complete("Hello")
            assert result == "Hello from compatible API"
            mock_client_class.assert_called_once_with(
                api_key="test-key", base_url="http://localhost:1234/v1"
            )
            mock_client.chat.completions.create.assert_called_once_with(
                model="test-model",
                max_tokens=500,
                temperature=0.1,
                messages=[{"role": "user", "content": "Hello"}],
            )

    def test_complete_raises_on_error(self) -> None:
        provider = OpenAICompatibleLLM.__new__(OpenAICompatibleLLM)
        provider.model = "test-model"
        provider._api_key = "test-key"
        provider._base_url = None
        provider._provider_name = "openai-compatible"

        with patch("openai.OpenAI") as mock_client_class:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = Exception("API error")
            mock_client_class.return_value = mock_client

            with pytest.raises(
                RuntimeError, match="openai-compatible completion failed"
            ):
                provider.complete("Hello")


class TestOpenAICompatibleLLMCompleteStructured:
    def test_complete_structured_returns_pydantic_model(self) -> None:
        provider = OpenAICompatibleLLM.__new__(OpenAICompatibleLLM)
        provider.model = "test-model"
        provider._api_key = "test-key"
        provider._base_url = "http://localhost:1234/v1"
        provider._provider_name = "openai-compatible"

        dummy_instance = DummyOutput(answer="42")

        with patch("instructor.from_openai") as mock_from_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = dummy_instance
            mock_from_openai.return_value = mock_client

            result = provider.complete_structured("What is the answer?", DummyOutput)
            assert isinstance(result, DummyOutput)
            assert result.answer == "42"
            mock_from_openai.assert_called_once()
            _, kwargs = mock_from_openai.call_args
            assert kwargs.get("mode") == instructor.Mode.JSON

    def test_complete_structured_raises_on_error(self) -> None:
        provider = OpenAICompatibleLLM.__new__(OpenAICompatibleLLM)
        provider.model = "test-model"
        provider._api_key = "test-key"
        provider._base_url = None
        provider._provider_name = "openai-compatible"

        with patch("instructor.from_openai") as mock_from_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = Exception(
                "structured error"
            )
            mock_from_openai.return_value = mock_client

            with pytest.raises(
                RuntimeError, match="openai-compatible structured completion failed"
            ):
                provider.complete_structured("prompt", DummyOutput)
