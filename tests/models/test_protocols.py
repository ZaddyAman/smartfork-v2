"""Tests for provider protocols."""

from smartfork.providers.protocols import EmbeddingProvider, LLMProvider
from smartfork.adapters.base import SessionAdapter


class TestLLMProvider:
    def test_has_complete_method(self) -> None:
        assert hasattr(LLMProvider, "complete")

    def test_has_complete_structured_method(self) -> None:
        assert hasattr(LLMProvider, "complete_structured")


class TestEmbeddingProvider:
    def test_has_embed_method(self) -> None:
        assert hasattr(EmbeddingProvider, "embed")

    def test_has_embed_query_method(self) -> None:
        assert hasattr(EmbeddingProvider, "embed_query")

    def test_has_embed_batch_method(self) -> None:
        assert hasattr(EmbeddingProvider, "embed_batch")

    def test_has_get_dimensions_method(self) -> None:
        assert hasattr(EmbeddingProvider, "get_dimensions")


class TestSessionAdapter:
    def test_has_agent_id_attribute(self) -> None:
        assert "agent_id" in SessionAdapter.__annotations__

    def test_has_display_name_attribute(self) -> None:
        assert "display_name" in SessionAdapter.__annotations__

    def test_has_session_type_attribute(self) -> None:
        assert "session_type" in SessionAdapter.__annotations__

    def test_has_is_valid_session_method(self) -> None:
        assert hasattr(SessionAdapter, "is_valid_session")

    def test_has_parse_raw_method(self) -> None:
        assert hasattr(SessionAdapter, "parse_raw")

    def test_has_get_default_sessions_paths_method(self) -> None:
        assert hasattr(SessionAdapter, "get_default_sessions_paths")

    def test_has_get_session_files_method(self) -> None:
        assert hasattr(SessionAdapter, "get_session_files")

    def test_has_get_ide_choices_method(self) -> None:
        assert hasattr(SessionAdapter, "get_ide_choices")
