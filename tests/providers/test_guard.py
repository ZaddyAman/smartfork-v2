"""Tests for EmbeddingModelGuard."""

from smartfork.providers.guard import EmbeddingModelGuard


class TestCheckCompatibility:
    def test_same_model_returns_true(self) -> None:
        result = EmbeddingModelGuard.check_compatibility(
            current_model="qwen3-embedding:0.6b",
            current_dims=512,
            new_model="qwen3-embedding:0.6b",
            new_dims=512,
        )
        assert result is True

    def test_different_model_same_dims_returns_true(self) -> None:
        result = EmbeddingModelGuard.check_compatibility(
            current_model="qwen3-embedding:0.6b",
            current_dims=512,
            new_model="nomic-embed-text",
            new_dims=512,
        )
        assert result is True

    def test_different_dims_returns_false(self) -> None:
        result = EmbeddingModelGuard.check_compatibility(
            current_model="qwen3-embedding:0.6b",
            current_dims=512,
            new_model="text-embedding-3-large",
            new_dims=3072,
        )
        assert result is False

    def test_same_model_different_dims_returns_true(self) -> None:
        # Same model name trumps dimension mismatch (it's the same model)
        result = EmbeddingModelGuard.check_compatibility(
            current_model="text-embedding-3-small",
            current_dims=512,
            new_model="text-embedding-3-small",
            new_dims=1536,
        )
        assert result is True


class TestGetWarningMessage:
    def test_contains_model_names(self) -> None:
        msg = EmbeddingModelGuard.get_warning_message(
            current_model="old-model",
            new_model="new-model",
            session_count=42,
        )
        assert "old-model" in msg
        assert "new-model" in msg

    def test_contains_session_count(self) -> None:
        msg = EmbeddingModelGuard.get_warning_message(
            current_model="old",
            new_model="new",
            session_count=1_247,
        )
        assert "1,247" in msg

    def test_contains_reindex_hint(self) -> None:
        msg = EmbeddingModelGuard.get_warning_message(
            current_model="old",
            new_model="new",
            session_count=1,
        )
        assert "--reindex" in msg
        assert "INCOMPATIBLE" in msg

    def test_handles_single_session(self) -> None:
        msg = EmbeddingModelGuard.get_warning_message(
            current_model="old",
            new_model="new",
            session_count=1,
        )
        assert "1 session" in msg
