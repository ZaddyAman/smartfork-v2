"""Tests for Ollama helper utilities."""

from unittest.mock import MagicMock, patch

import pytest

from smartfork.providers.helpers import (
    check_ollama_available,
    ensure_ollama_model,
    list_available_ollama_models,
    recommend_model,
)


class TestCheckOllamaAvailable:
    def test_returns_true_when_model_found(self) -> None:
        with patch("smartfork.providers.helpers.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.helpers.shutil.which", return_value="/usr/bin/ollama"), \
             patch("smartfork.providers.helpers.ollama") as mock_ollama:
            mock_ollama.list.return_value = {
                "models": [{"name": "qwen2.5-coder:7b"}]
            }
            result = check_ollama_available("qwen2.5-coder:7b")
            assert result is True

    def test_returns_true_when_model_base_matches(self) -> None:
        with patch("smartfork.providers.helpers.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.helpers.shutil.which", return_value="/usr/bin/ollama"), \
             patch("smartfork.providers.helpers.ollama") as mock_ollama:
            mock_ollama.list.return_value = {
                "models": [{"name": "qwen2.5-coder:latest"}]
            }
            result = check_ollama_available("qwen2.5-coder:7b")
            assert result is True

    def test_returns_false_when_model_not_found(self) -> None:
        with patch("smartfork.providers.helpers.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.helpers.shutil.which", return_value="/usr/bin/ollama"), \
             patch("smartfork.providers.helpers.ollama") as mock_ollama:
            mock_ollama.list.return_value = {
                "models": [{"name": "llama3.2:3b"}]
            }
            result = check_ollama_available("qwen2.5-coder:7b")
            assert result is False

    def test_returns_false_when_ollama_package_missing(self) -> None:
        with patch("smartfork.providers.helpers.OLLAMA_AVAILABLE", False):
            result = check_ollama_available("any-model")
            assert result is False

    def test_returns_false_when_ollama_binary_missing(self) -> None:
        with patch("smartfork.providers.helpers.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.helpers.shutil.which", return_value=None):
            result = check_ollama_available("any-model")
            assert result is False

    def test_returns_false_when_connection_fails(self) -> None:
        with patch("smartfork.providers.helpers.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.helpers.shutil.which", return_value="/usr/bin/ollama"), \
             patch("smartfork.providers.helpers.ollama") as mock_ollama:
            mock_ollama.list.side_effect = ConnectionError("Connection refused")
            result = check_ollama_available("qwen2.5-coder:7b")
            assert result is False


class TestEnsureOllamaModel:
    def test_returns_when_model_already_available(self) -> None:
        with patch("smartfork.providers.helpers.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.helpers.shutil.which", return_value="/usr/bin/ollama"), \
             patch("smartfork.providers.helpers.ollama") as mock_ollama:
            mock_ollama.list.return_value = {
                "models": [{"name": "qwen2.5-coder:7b"}]
            }
            # Should not raise
            ensure_ollama_model("qwen2.5-coder:7b")
            mock_ollama.pull.assert_not_called()

    def test_pulls_model_when_not_available(self) -> None:
        with patch("smartfork.providers.helpers.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.helpers.shutil.which", return_value="/usr/bin/ollama"), \
             patch("smartfork.providers.helpers.ollama") as mock_ollama:
            mock_ollama.list.return_value = {
                "models": [{"name": "llama3.2:3b"}]
            }
            ensure_ollama_model("qwen2.5-coder:7b")
            mock_ollama.pull.assert_called_once_with("qwen2.5-coder:7b")

    def test_raises_when_ollama_package_missing(self) -> None:
        with patch("smartfork.providers.helpers.OLLAMA_AVAILABLE", False), \
             pytest.raises(RuntimeError, match="Ollama Python package is not installed"):
            ensure_ollama_model("qwen2.5-coder:7b")

    def test_raises_when_ollama_binary_missing(self) -> None:
        with patch("smartfork.providers.helpers.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.helpers.shutil.which", return_value=None), \
             pytest.raises(RuntimeError, match="Ollama binary not found"):
            ensure_ollama_model("qwen2.5-coder:7b")

    def test_raises_when_pull_fails(self) -> None:
        with patch("smartfork.providers.helpers.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.helpers.shutil.which", return_value="/usr/bin/ollama"), \
             patch("smartfork.providers.helpers.ollama") as mock_ollama:
            mock_ollama.list.return_value = {"models": []}
            mock_ollama.pull.side_effect = RuntimeError("Network error")
            with pytest.raises(RuntimeError, match="Failed to pull model"):
                ensure_ollama_model("qwen2.5-coder:7b")


class TestListAvailableOllamaModels:
    def test_returns_models_list(self) -> None:
        with patch("smartfork.providers.helpers.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.helpers.shutil.which", return_value="/usr/bin/ollama"), \
             patch("smartfork.providers.helpers.ollama") as mock_ollama:
            mock_ollama.list.return_value = {
                "models": [
                    {"name": "qwen2.5-coder:7b"},
                    {"name": "llama3.2:3b"},
                ]
            }
            result = list_available_ollama_models()
            assert result == ["qwen2.5-coder:7b", "llama3.2:3b"]

    def test_returns_empty_when_ollama_unavailable(self) -> None:
        with patch("smartfork.providers.helpers.OLLAMA_AVAILABLE", False):
            result = list_available_ollama_models()
            assert result == []

    def test_returns_empty_when_connection_fails(self) -> None:
        with patch("smartfork.providers.helpers.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.helpers.shutil.which", return_value="/usr/bin/ollama"), \
             patch("smartfork.providers.helpers.ollama") as mock_ollama:
            mock_ollama.list.side_effect = Exception("Connection refused")
            result = list_available_ollama_models()
            assert result == []


class TestRecommendModel:
    @patch("smartfork.providers.helpers.shutil.which", return_value=None)
    def test_returns_default_model(self, mock_which: MagicMock) -> None:
        result = recommend_model()
        assert isinstance(result, str)
        assert "coder" in result or "qwen" in result
