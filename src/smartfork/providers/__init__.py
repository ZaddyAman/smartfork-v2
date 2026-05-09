"""SmartFork v2 — Provider implementations."""

from smartfork.providers.helpers import (
    check_ollama_available,
    ensure_ollama_model,
    list_available_ollama_models,
    recommend_model,
)
from smartfork.providers.llm import (
    AnthropicLLM,
    OllamaLLM,
    OpenAILLM,
    get_llm,
)
from smartfork.providers.protocols import (
    EmbeddingProvider,
    LLMProvider,
    SessionAdapter,
)

__all__ = [
    # Factory
    "get_llm",
    # LLM implementations
    "OllamaLLM",
    "AnthropicLLM",
    "OpenAILLM",
    # Protocols
    "LLMProvider",
    "EmbeddingProvider",
    "SessionAdapter",
    # Helpers
    "check_ollama_available",
    "ensure_ollama_model",
    "list_available_ollama_models",
    "recommend_model",
]
