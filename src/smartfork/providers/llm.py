"""LLM provider implementations for SmartFork v2."""

import os
from pathlib import Path
from typing import Any

from loguru import logger

from smartfork.providers.helpers import OLLAMA_AVAILABLE, check_ollama_available
from smartfork.providers.protocols import LLMProvider


def _load_secrets() -> dict[str, str]:
    """Load secrets from ~/.smartfork/secrets.env if available."""
    secrets_path = Path.home() / ".smartfork" / "secrets.env"
    secrets: dict[str, str] = {}
    if secrets_path.exists():
        with open(secrets_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    secrets[key.strip()] = val.strip().strip('"').strip("'")
    return secrets


class OllamaLLM:
    """LLM provider using local Ollama models."""

    def __init__(self, model: str = "qwen2.5-coder:7b") -> None:
        if not OLLAMA_AVAILABLE:
            raise RuntimeError(
                "Ollama Python package is not installed. "
                "Install it with: pip install ollama"
            )
        import ollama as _ollama
        self._client = _ollama.Client(timeout=30)
        self.model = model

        if not check_ollama_available(model):
            raise RuntimeError(
                f"Ollama model '{model}' is not available. "
                f"Ensure Ollama is running and the model is pulled: ollama pull {model}"
            )

    def complete(
        self, prompt: str, max_tokens: int = 500, temperature: float = 0.1
    ) -> str:
        """Send a completion request to Ollama.

        Args:
            prompt: The prompt to send.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.

        Returns:
            The response text, or empty string on error.
        """
        try:
            response = self._client.generate(
                model=self.model,
                prompt=prompt,
                options={
                    "num_predict": max_tokens,
                    "temperature": temperature,
                },
            )
            return str(response.get("response", ""))
        except Exception as e:
            logger.error(f"Ollama completion failed: {e}")
            raise RuntimeError(
                f"Ollama completion failed. Is Ollama running?\nError: {e}"
            ) from e

    def complete_structured(
        self,
        prompt: str,
        output_schema: type,
        max_tokens: int = 500,
        temperature: float = 0.1,
    ) -> Any:
        """Get structured output from Ollama using instructor.

        Uses instructor to patch Ollama's OpenAI-compatible endpoint for
        Pydantic-validated structured output.

        Args:
            prompt: The prompt to send.
            output_schema: A Pydantic model class for structured output.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.

        Returns:
            An instance of output_schema.
        """
        try:
            import instructor
            from openai import OpenAI

            client = instructor.from_openai(
                OpenAI(
                    base_url="http://localhost:11434/v1",
                    api_key="ollama",  # Ollama doesn't require a real key
                ),
                mode=instructor.Mode.JSON,
            )

            response: Any = client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                response_model=output_schema,
                messages=[{"role": "user", "content": prompt}],
            )
            return response
        except ImportError as e:
            logger.error(f"instructor package not installed: {e}")
            raise RuntimeError(
                "The 'instructor' package is required for structured output. "
                "Install it with: pip install instructor"
            ) from e
        except Exception as e:
            logger.error(f"Ollama structured completion failed: {e}")
            raise RuntimeError(
                f"Ollama structured completion failed: {e}"
            ) from e


class AnthropicLLM:
    """LLM provider using Anthropic's Claude API."""

    DEFAULT_MODEL = "claude-3-haiku-20240307"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or self.DEFAULT_MODEL

        if api_key:
            self._api_key = api_key
        else:
            secrets = _load_secrets()
            self._api_key = secrets.get(
                "ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", "")
            )

        if not self._api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not found. Set it in ~/.smartfork/secrets.env or "
                "as an environment variable. Get a key at https://console.anthropic.com/"
            )

    def complete(
        self, prompt: str, max_tokens: int = 500, temperature: float = 0.1
    ) -> str:
        """Send a completion request to Anthropic.

        Args:
            prompt: The prompt to send.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.

        Returns:
            The response text, or empty string on error.
        """
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self._api_key)
            message = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            # Extract text from response blocks
            text_parts: list[str] = []
            for block in message.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
            return "\n".join(text_parts)
        except ImportError as err:
            logger.error("anthropic package is not installed")
            raise RuntimeError(
                "The 'anthropic' package is required for Anthropic LLM. "
                "Install it with: pip install anthropic"
            ) from err
        except Exception as e:
            logger.error(f"Anthropic completion failed: {e}")
            raise RuntimeError(
                f"Anthropic completion failed. Check your API key and network.\nError: {e}"
            ) from e

    def complete_structured(
        self,
        prompt: str,
        output_schema: type,
        max_tokens: int = 500,
        temperature: float = 0.1,
    ) -> Any:
        """Get structured output from Anthropic using instructor.

        Args:
            prompt: The prompt to send.
            output_schema: A Pydantic model class for structured output.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.

        Returns:
            An instance of output_schema.
        """
        try:
            import instructor
            from anthropic import Anthropic

            client = instructor.from_anthropic(Anthropic(api_key=self._api_key))
            response: Any = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                response_model=output_schema,
                messages=[{"role": "user", "content": prompt}],
            )
            return response
        except ImportError as err:
            logger.error(f"instructor package not installed: {err}")
            raise RuntimeError(
                "The 'instructor' package is required for structured output. "
                "Install it with: pip install instructor"
            ) from err
        except Exception as e:
            logger.error(f"Anthropic structured completion failed: {e}")
            raise RuntimeError(
                f"Anthropic structured completion failed: {e}"
            ) from e


class OpenAILLM:
    """LLM provider using OpenAI's API."""

    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or self.DEFAULT_MODEL

        if api_key:
            self._api_key = api_key
        else:
            secrets = _load_secrets()
            self._api_key = secrets.get("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", ""))

        if not self._api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not found. Set it in ~/.smartfork/secrets.env or "
                "as an environment variable. Get a key at https://platform.openai.com/"
            )

    def complete(
        self, prompt: str, max_tokens: int = 500, temperature: float = 0.1
    ) -> str:
        """Send a completion request to OpenAI.

        Args:
            prompt: The prompt to send.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.

        Returns:
            The response text, or empty string on error.
        """
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self._api_key)
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            choice = response.choices[0]
            return choice.message.content or ""
        except ImportError as err:
            logger.error("openai package is not installed")
            raise RuntimeError(
                "The 'openai' package is required for OpenAI LLM. "
                "Install it with: pip install openai"
            ) from err
        except Exception as e:
            logger.error(f"OpenAI completion failed: {e}")
            raise RuntimeError(
                f"OpenAI completion failed. Check your API key and network.\nError: {e}"
            ) from e

    def complete_structured(
        self,
        prompt: str,
        output_schema: type,
        max_tokens: int = 500,
        temperature: float = 0.1,
    ) -> Any:
        """Get structured output from OpenAI using instructor.

        Args:
            prompt: The prompt to send.
            output_schema: A Pydantic model class for structured output.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.

        Returns:
            An instance of output_schema.
        """
        try:
            import instructor
            from openai import OpenAI

            client = instructor.from_openai(OpenAI(api_key=self._api_key))
            response: Any = client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                response_model=output_schema,
                messages=[{"role": "user", "content": prompt}],
            )
            return response
        except ImportError as err:
            logger.error(f"instructor package not installed: {err}")
            raise RuntimeError(
                "The 'instructor' package is required for structured output. "
                "Install it with: pip install instructor"
            ) from err
        except Exception as e:
            logger.error(f"OpenAI structured completion failed: {e}")
            raise RuntimeError(
                f"OpenAI structured completion failed: {e}"
            ) from e


class OpenAICompatibleLLM:
    """LLM provider using an OpenAI-compatible API endpoint."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        provider_name: str = "openai-compatible",
    ) -> None:
        self.model = model
        self._base_url = base_url
        self._provider_name = provider_name

        env_var_name = f"{provider_name.upper().replace('-', '_')}_API_KEY"

        if api_key:
            self._api_key = api_key
        else:
            secrets = _load_secrets()
            self._api_key = secrets.get(env_var_name, os.environ.get(env_var_name, ""))

        if not self._api_key:
            raise RuntimeError(
                f"{env_var_name} not found. Set it in ~/.smartfork/secrets.env or "
                "as an environment variable."
            )

    def complete(
        self, prompt: str, max_tokens: int = 500, temperature: float = 0.1
    ) -> str:
        """Send a completion request to an OpenAI-compatible API.

        Args:
            prompt: The prompt to send.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.

        Returns:
            The response text, or empty string on error.
        """
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self._api_key, base_url=self._base_url)
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            choice = response.choices[0]
            return choice.message.content or ""
        except ImportError as err:
            logger.error("openai package is not installed")
            raise RuntimeError(
                "The 'openai' package is required for OpenAI-compatible LLM. "
                "Install it with: pip install openai"
            ) from err
        except Exception as e:
            logger.error(f"{self._provider_name} completion failed: {e}")
            raise RuntimeError(
                f"{self._provider_name} completion failed. "
                f"Check your API key and network.\nError: {e}"
            ) from e

    def complete_structured(
        self,
        prompt: str,
        output_schema: type,
        max_tokens: int = 500,
        temperature: float = 0.1,
    ) -> Any:
        """Get structured output from an OpenAI-compatible API using instructor.

        Args:
            prompt: The prompt to send.
            output_schema: A Pydantic model class for structured output.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.

        Returns:
            An instance of output_schema.
        """
        try:
            import instructor
            from openai import OpenAI

            client = instructor.from_openai(
                OpenAI(api_key=self._api_key, base_url=self._base_url),
                mode=instructor.Mode.JSON,
            )
            response: Any = client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                response_model=output_schema,
                messages=[{"role": "user", "content": prompt}],
            )
            return response
        except ImportError as err:
            logger.error(f"instructor package not installed: {err}")
            raise RuntimeError(
                "The 'instructor' package is required for structured output. "
                "Install it with: pip install instructor"
            ) from err
        except Exception as e:
            logger.error(f"{self._provider_name} structured completion failed: {e}")
            raise RuntimeError(
                f"{self._provider_name} structured completion failed: {e}"
            ) from e


def get_llm(provider: str = "ollama", model: str | None = None) -> LLMProvider:
    """Factory function returning the correct LLM provider.

    Args:
        provider: One of "ollama", "anthropic", or "openai".
        model: Override the default model name.

    Returns:
        An LLMProvider instance.

    Raises:
        ValueError: If provider is unknown.
    """
    provider = provider.lower()

    if provider == "ollama":
        return OllamaLLM(model=model or "qwen2.5-coder:7b")

    if provider == "anthropic":
        return AnthropicLLM(model=model)

    if provider == "openai":
        return OpenAILLM(model=model)

    raise ValueError(
        f"Unknown LLM provider: '{provider}'. "
        "Valid options: ollama, anthropic, openai"
    )
