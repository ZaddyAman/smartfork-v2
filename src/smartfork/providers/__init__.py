"""SmartFork v2 — Provider implementations."""

from smartfork.providers.embedding import (
    EMBED_INSTRUCTIONS,
    QUERY_INSTRUCTION,
    OllamaEmbedder,
    OpenAIEmbedder,
    SentenceTransformerEmbedder,
    check_embedding_model_available,
    get_embedder,
)
from smartfork.providers.guard import EmbeddingModelGuard
from smartfork.providers.helpers import (
    check_ollama_available,
    ensure_ollama_model,
    list_available_ollama_models,
    recommend_model,
)
from smartfork.providers.llm import (
    AnthropicLLM,
    OllamaLLM,
    OpenAICompatibleLLM,
    OpenAILLM,
    get_llm,
)
from smartfork.providers.protocols import (
    EmbeddingProvider,
    LLMProvider,
)

OPENCODE_ECOSYSTEM_PROVIDERS = ("opencode", "go", "zen")

__all__ = [
    # LLM Factory
    "get_llm",
    # LLM implementations
    "OllamaLLM",
    "AnthropicLLM",
    "OpenAILLM",
    "OpenAICompatibleLLM",
    # OpenCode ecosystem
    "OPENCODE_ECOSYSTEM_PROVIDERS",
    # Embedding Factory
    "get_embedder",
    # Embedding implementations
    "OllamaEmbedder",
    "SentenceTransformerEmbedder",
    "OpenAIEmbedder",
    # Embedding instructions
    "EMBED_INSTRUCTIONS",
    "QUERY_INSTRUCTION",
    # Protocols
    "LLMProvider",
    "EmbeddingProvider",
    # Helpers
    "check_ollama_available",
    "ensure_ollama_model",
    "list_available_ollama_models",
    "recommend_model",
    "check_embedding_model_available",
    # Guard
    "EmbeddingModelGuard",
]

