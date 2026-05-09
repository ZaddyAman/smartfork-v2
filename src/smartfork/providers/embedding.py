"""Embedding provider implementations for SmartFork v2."""

from smartfork.providers.helpers import OLLAMA_AVAILABLE, check_ollama_available
from smartfork.providers.llm import _load_secrets
from smartfork.providers.protocols import EmbeddingProvider

# Instruction prefixes (Anthropic's Contextual Retrieval technique)
EMBED_INSTRUCTIONS: dict[str, str] = {
    "task_doc": "Represent this developer task description for session retrieval",
    "summary_doc": "Represent this coding session summary for intelligent search",
    "reasoning_doc": "Represent this technical decision and rationale for retrieval",
    "proposition": "Represent this factual statement about a coding session for retrieval",
}
QUERY_INSTRUCTION = "Find coding sessions relevant to this developer query"


class OllamaEmbedder:
    """Embedding provider using local Ollama models with instruction prefixes."""

    def __init__(self, model: str = "qwen3-embedding:0.6b", dimensions: int = 512) -> None:
        if not OLLAMA_AVAILABLE:
            raise RuntimeError(
                "Ollama Python package is not installed. "
                "Install it with: pip install ollama"
            )
        import ollama as _ollama
        self._ollama = _ollama
        self.model = model
        self._dimensions = dimensions

        if not check_ollama_available(model):
            raise RuntimeError(
                f"Ollama model '{model}' is not available. "
                f"Ensure Ollama is running and the model is pulled: ollama pull {model}"
            )

    def _build_prompt(self, text: str, doc_type: str) -> str:
        """Build an instruction-prefixed prompt for embedding."""
        instruction = EMBED_INSTRUCTIONS.get(doc_type, "")
        if instruction:
            return f"{instruction}: {text}"
        return text

    def embed(self, text: str, doc_type: str = "task_doc") -> list[float]:
        """Embed text with instruction prefix based on doc_type.

        Args:
            text: The text to embed.
            doc_type: One of "task_doc", "summary_doc", "reasoning_doc", "proposition".

        Returns:
            Embedding vector as a list of floats.
        """
        try:
            prompt = self._build_prompt(text, doc_type)
            response = self._ollama.embed(model=self.model, input=prompt)
            embeddings = response.get("embeddings", [])
            if embeddings:
                return embeddings[0]  # type: ignore[no-any-return]
            return []
        except Exception as e:
            raise RuntimeError(
                f"Ollama embedding failed for model '{self.model}': {e}"
            ) from e

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query with query-specific instruction.

        Args:
            query: The search query text.

        Returns:
            Embedding vector as a list of floats.
        """
        try:
            prompt = f"{QUERY_INSTRUCTION}: {query}"
            response = self._ollama.embed(model=self.model, input=prompt)
            embeddings = response.get("embeddings", [])
            if embeddings:
                return embeddings[0]  # type: ignore[no-any-return]
            return []
        except Exception as e:
            raise RuntimeError(
                f"Ollama query embedding failed for model '{self.model}': {e}"
            ) from e

    def embed_batch(self, texts: list[str], doc_type: str = "task_doc") -> list[list[float]]:
        """Embed a batch of texts with the same instruction prefix.

        Args:
            texts: List of texts to embed.
            doc_type: The document type for instruction prefixing.

        Returns:
            List of embedding vectors.
        """
        results: list[list[float]] = []
        for text in texts:
            results.append(self.embed(text, doc_type=doc_type))
        return results

    def get_dimensions(self) -> int:
        """Return the embedding dimension size."""
        return self._dimensions


class SentenceTransformerEmbedder:
    """Embedding provider using SentenceTransformers (offline, no instruction prefixes)."""

    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    DEFAULT_DIMENSIONS = 384

    def __init__(self, model: str | None = None, dimensions: int | None = None) -> None:
        self.model = model or self.DEFAULT_MODEL
        self._dimensions = dimensions or self.DEFAULT_DIMENSIONS

        try:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(self.model)
        except ImportError:
            raise RuntimeError(
                "The 'sentence-transformers' package is required. "
                "Install it with: pip install sentence-transformers"
            ) from None
        except Exception as e:
            raise RuntimeError(
                f"Failed to load SentenceTransformer model '{self.model}': {e}"
            ) from e

    def embed(self, text: str, doc_type: str = "task_doc") -> list[float]:
        """Embed a single text. doc_type is ignored (not instruction-aware).

        Args:
            text: The text to embed.
            doc_type: Ignored for SentenceTransformer (no instruction support).

        Returns:
            Embedding vector as a list of floats.
        """
        try:
            result = self._encoder.encode(text, convert_to_tensor=False)
            return list(result)
        except Exception as e:
            raise RuntimeError(
                f"SentenceTransformer embedding failed: {e}"
            ) from e

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query. Identical to embed() for SentenceTransformer.

        Args:
            query: The search query text.

        Returns:
            Embedding vector as a list of floats.
        """
        return self.embed(query)

    def embed_batch(self, texts: list[str], doc_type: str = "task_doc") -> list[list[float]]:
        """Embed a batch of texts using native batch encoding.

        Args:
            texts: List of texts to embed.
            doc_type: Ignored for SentenceTransformer.

        Returns:
            List of embedding vectors.
        """
        try:
            results = self._encoder.encode(texts, convert_to_tensor=False)
            return [list(r) for r in results]
        except Exception as e:
            raise RuntimeError(
                f"SentenceTransformer batch embedding failed: {e}"
            ) from e

    def get_dimensions(self) -> int:
        """Return the embedding dimension size."""
        return self._dimensions


class OpenAIEmbedder:
    """Embedding provider using OpenAI's API (not instruction-aware)."""

    DEFAULT_MODEL = "text-embedding-3-small"
    DEFAULT_DIMENSIONS = 1536

    def __init__(
        self,
        model: str | None = None,
        dimensions: int | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model or self.DEFAULT_MODEL
        self._dimensions = dimensions or self.DEFAULT_DIMENSIONS

        if api_key is not None:
            self._api_key = api_key if api_key else self._load_api_key()
        else:
            self._api_key = self._load_api_key()

        if not self._api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not found. Set it in ~/.smartfork/secrets.env or "
                "as an environment variable. Get a key at https://platform.openai.com/"
            )

    @staticmethod
    def _load_api_key() -> str:
        """Load OpenAI API key from secrets or environment."""
        import os
        secrets = _load_secrets()
        return secrets.get("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", ""))

    def embed(self, text: str, doc_type: str = "task_doc") -> list[float]:
        """Embed a single text via OpenAI API. doc_type is ignored.

        Args:
            text: The text to embed.
            doc_type: Ignored for OpenAI (no instruction support).

        Returns:
            Embedding vector as a list of floats.
        """
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self._api_key)
            response = client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self._dimensions,
            )
            return list(response.data[0].embedding)
        except ImportError:
            raise RuntimeError(
                "The 'openai' package is required. Install it with: pip install openai"
            ) from None
        except Exception as e:
            raise RuntimeError(
                f"OpenAI embedding failed: {e}"
            ) from e

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query via OpenAI API.

        Args:
            query: The search query text.

        Returns:
            Embedding vector as a list of floats.
        """
        return self.embed(query)

    def embed_batch(self, texts: list[str], doc_type: str = "task_doc") -> list[list[float]]:
        """Embed a batch of texts via OpenAI API.

        Args:
            texts: List of texts to embed.
            doc_type: Ignored for OpenAI.

        Returns:
            List of embedding vectors.
        """
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self._api_key)
            response = client.embeddings.create(
                model=self.model,
                input=texts,
                dimensions=self._dimensions,
            )
            return [list(d.embedding) for d in response.data]
        except ImportError:
            raise RuntimeError(
                "The 'openai' package is required. Install it with: pip install openai"
            ) from None
        except Exception as e:
            raise RuntimeError(
                f"OpenAI batch embedding failed: {e}"
            ) from e

    def get_dimensions(self) -> int:
        """Return the embedding dimension size."""
        return self._dimensions


def get_embedder(provider: str = "ollama", model: str | None = None) -> EmbeddingProvider:
    """Factory function returning the correct embedding provider.

    Args:
        provider: One of "ollama", "sentence-transformers", or "openai".
        model: Override the default model name.

    Returns:
        An EmbeddingProvider instance.

    Raises:
        ValueError: If provider is unknown.
    """
    provider = provider.lower()

    if provider == "ollama":
        return OllamaEmbedder(model=model or "qwen3-embedding:0.6b")

    if provider == "sentence-transformers":
        return SentenceTransformerEmbedder(model=model)

    if provider == "openai":
        return OpenAIEmbedder(model=model)

    raise ValueError(
        f"Unknown embedding provider: '{provider}'. "
        "Valid options: ollama, sentence-transformers, openai"
    )


def check_embedding_model_available(provider: str, model: str) -> bool:
    """Generic health check for any embedding provider.

    Args:
        provider: The provider name.
        model: The model name to check.

    Returns:
        True if the model is available, False otherwise.
    """
    if provider.lower() == "ollama":
        return check_ollama_available(model)

    # For cloud/local library providers, just check the package is importable
    if provider.lower() == "sentence-transformers":
        try:
            import sentence_transformers  # noqa: F401
            return True
        except ImportError:
            return False

    if provider.lower() == "openai":
        try:
            import openai  # noqa: F401
            return True
        except ImportError:
            return False

    return False
