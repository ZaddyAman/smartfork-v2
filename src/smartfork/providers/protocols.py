"""Provider protocols for SmartFork v2."""

from typing import Protocol


class LLMProvider(Protocol):
    """Protocol for LLM completion providers."""

    def complete(
        self, prompt: str, max_tokens: int = 500, temperature: float = 0.1
    ) -> str: ...

    def complete_structured(
        self, prompt: str, output_schema: type, max_tokens: int = 500
    ) -> object: ...


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers."""

    def embed(self, text: str, doc_type: str = "task_doc") -> list[float]: ...

    def embed_query(self, query: str) -> list[float]: ...

    def embed_batch(
        self, texts: list[str], doc_type: str = "task_doc"
    ) -> list[list[float]]: ...

    def get_dimensions(self) -> int: ...

