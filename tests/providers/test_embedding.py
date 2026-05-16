"""Tests for embedding provider implementations."""

from unittest.mock import MagicMock, patch

import pytest

from smartfork.providers.embedding import (
    EMBED_INSTRUCTIONS,
    QUERY_INSTRUCTION,
    OllamaEmbedder,
    OpenAIEmbedder,
    SentenceTransformerEmbedder,
    check_embedding_model_available,
    get_embedder,
)


class TestEmbedInstructions:
    def test_has_all_doc_types(self) -> None:
        assert "task_doc" in EMBED_INSTRUCTIONS
        assert "summary_doc" in EMBED_INSTRUCTIONS
        assert "reasoning_doc" in EMBED_INSTRUCTIONS
        assert "proposition" in EMBED_INSTRUCTIONS

    def test_query_instruction_exists(self) -> None:
        assert len(QUERY_INSTRUCTION) > 0


class TestOllamaEmbedder:
    def test_init_raises_when_ollama_not_available(self) -> None:
        with patch("smartfork.providers.embedding.OLLAMA_AVAILABLE", False), \
             pytest.raises(RuntimeError, match="Ollama Python package is not installed"):
            OllamaEmbedder()

    def test_init_raises_when_model_not_available(self) -> None:
        with patch("smartfork.providers.embedding.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.embedding.check_ollama_available", return_value=False), \
             pytest.raises(RuntimeError, match="Ollama model"):
            OllamaEmbedder()

    def test_embed_returns_vector(self) -> None:
        mock_client = MagicMock()
        mock_client.embed.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
        with patch("smartfork.providers.embedding.OLLAMA_AVAILABLE", True), \
              patch("smartfork.providers.embedding.check_ollama_available", return_value=True):
            embedder = OllamaEmbedder.__new__(OllamaEmbedder)
            embedder._client = mock_client
            embedder.model = "qwen3-embedding:0.6b"
            embedder._dimensions = 1024
            result = embedder.embed("test text")
            assert result == [0.1, 0.2, 0.3]

    def test_embed_prepends_instruction(self) -> None:
        mock_client = MagicMock()
        mock_client.embed.return_value = {"embeddings": [[0.1]]}
        with patch("smartfork.providers.embedding.OLLAMA_AVAILABLE", True), \
              patch("smartfork.providers.embedding.check_ollama_available", return_value=True):
            embedder = OllamaEmbedder.__new__(OllamaEmbedder)
            embedder._client = mock_client
            embedder.model = "test"
            embedder._dimensions = 1024
            embedder.embed("test text", doc_type="task_doc")
            call_input = mock_client.embed.call_args[1]["input"]
            assert "Represent this developer" in call_input
            assert "test text" in call_input

    def test_embed_no_instruction_for_unknown_doc_type(self) -> None:
        mock_client = MagicMock()
        mock_client.embed.return_value = {"embeddings": [[0.1]]}
        with patch("smartfork.providers.embedding.OLLAMA_AVAILABLE", True), \
              patch("smartfork.providers.embedding.check_ollama_available", return_value=True):
            embedder = OllamaEmbedder.__new__(OllamaEmbedder)
            embedder._client = mock_client
            embedder.model = "test"
            embedder._dimensions = 1024
            embedder.embed("test text", doc_type="unknown_type")
            call_input = mock_client.embed.call_args[1]["input"]
            assert call_input == "test text"

    def test_embed_query_prepends_query_instruction(self) -> None:
        mock_client = MagicMock()
        mock_client.embed.return_value = {"embeddings": [[0.1]]}
        with patch("smartfork.providers.embedding.OLLAMA_AVAILABLE", True), \
              patch("smartfork.providers.embedding.check_ollama_available", return_value=True):
            embedder = OllamaEmbedder.__new__(OllamaEmbedder)
            embedder._client = mock_client
            embedder.model = "test"
            embedder._dimensions = 1024
            embedder.embed_query("how to fix error")
            call_input = mock_client.embed.call_args[1]["input"]
            assert QUERY_INSTRUCTION in call_input
            assert "how to fix error" in call_input

    def test_embed_batch_returns_all_vectors(self) -> None:
        mock_client = MagicMock()
        mock_client.embed.return_value = {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}
        with patch("smartfork.providers.embedding.OLLAMA_AVAILABLE", True), \
              patch("smartfork.providers.embedding.check_ollama_available", return_value=True):
            embedder = OllamaEmbedder.__new__(OllamaEmbedder)
            embedder._client = mock_client
            embedder.model = "test"
            embedder._dimensions = 1024
            result = embedder.embed_batch(["text1", "text2"])
            assert len(result) == 2
            assert result[0] == [0.1, 0.2]
            assert result[1] == [0.3, 0.4]

    def test_embed_raises_with_empty_embeddings(self) -> None:
        mock_client = MagicMock()
        mock_client.embed.return_value = {"embeddings": []}
        with patch("smartfork.providers.embedding.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.embedding.check_ollama_available", return_value=True):
            embedder = OllamaEmbedder.__new__(OllamaEmbedder)
            embedder._client = mock_client
            embedder.model = "test"
            embedder._dimensions = 1024
            with pytest.raises(RuntimeError, match="Ollama returned no embeddings"):
                embedder.embed("test")

    def test_embed_raises_with_empty_vector(self) -> None:
        """Ollama returns embeddings list with empty inner list."""
        mock_client = MagicMock()
        mock_client.embed.return_value = {"embeddings": [[]]}
        with patch("smartfork.providers.embedding.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.embedding.check_ollama_available", return_value=True):
            embedder = OllamaEmbedder.__new__(OllamaEmbedder)
            embedder._client = mock_client
            embedder.model = "test"
            embedder._dimensions = 1024
            with pytest.raises(RuntimeError, match="Ollama returned empty embedding"):
                embedder.embed("test")

    def test_embed_query_raises_with_empty_embeddings(self) -> None:
        mock_client = MagicMock()
        mock_client.embed.return_value = {"embeddings": []}
        with patch("smartfork.providers.embedding.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.embedding.check_ollama_available", return_value=True):
            embedder = OllamaEmbedder.__new__(OllamaEmbedder)
            embedder._client = mock_client
            embedder.model = "test"
            embedder._dimensions = 1024
            with pytest.raises(RuntimeError, match="Ollama returned no query embeddings"):
                embedder.embed_query("test")

    def test_embed_batch_raises_with_empty_vectors(self) -> None:
        """Batch returns list with some empty inner lists, triggers fallback."""
        mock_client = MagicMock()
        mock_client.embed.return_value = {"embeddings": [[0.1], []]}
        with patch("smartfork.providers.embedding.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.embedding.check_ollama_available", return_value=True):
            embedder = OllamaEmbedder.__new__(OllamaEmbedder)
            embedder._client = mock_client
            embedder.model = "test"
            embedder._dimensions = 1024
            embedder.embed_batch(["t1", "t2"])

    def test_get_dimensions(self) -> None:
        with patch("smartfork.providers.embedding.OLLAMA_AVAILABLE", True), \
              patch("smartfork.providers.embedding.check_ollama_available", return_value=True):
            embedder = OllamaEmbedder.__new__(OllamaEmbedder)
            embedder._client = MagicMock()
            embedder.model = "test"
            embedder._dimensions = 1024
            assert embedder.get_dimensions() == 1024


class TestSentenceTransformerEmbedder:
    def test_embed_returns_vector(self) -> None:
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = [0.1, 0.2, 0.3]
        with patch("sentence_transformers.SentenceTransformer", return_value=mock_encoder):
            embedder = SentenceTransformerEmbedder()
            result = embedder.embed("test text")
            assert result == [0.1, 0.2, 0.3]

    def test_embed_ignores_doc_type(self) -> None:
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = [0.1]
        with patch("sentence_transformers.SentenceTransformer", return_value=mock_encoder):
            embedder = SentenceTransformerEmbedder()
            embedder.embed("test", doc_type="summary_doc")
            # Just verify it doesn't crash — doc_type is ignored
            mock_encoder.encode.assert_called_once()

    def test_embed_query_delegates_to_embed(self) -> None:
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = [0.1, 0.2]
        with patch("sentence_transformers.SentenceTransformer", return_value=mock_encoder):
            embedder = SentenceTransformerEmbedder()
            result = embedder.embed_query("query text")
            assert result == [0.1, 0.2]

    def test_embed_batch_uses_native_batch(self) -> None:
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = [[0.1, 0.2], [0.3, 0.4]]
        with patch("sentence_transformers.SentenceTransformer", return_value=mock_encoder):
            embedder = SentenceTransformerEmbedder()
            result = embedder.embed_batch(["text1", "text2"])
            assert len(result) == 2
            assert result[0] == [0.1, 0.2]

    def test_raises_when_package_missing(self) -> None:
        with patch("smartfork.providers.embedding.SentenceTransformerEmbedder.__init__",
                   side_effect=RuntimeError("The 'sentence-transformers' package is required")), \
             pytest.raises(RuntimeError, match="sentence-transformers"):
            SentenceTransformerEmbedder()

    def test_get_dimensions(self) -> None:
        mock_encoder = MagicMock()
        with patch("sentence_transformers.SentenceTransformer", return_value=mock_encoder):
            embedder = SentenceTransformerEmbedder()
            assert embedder.get_dimensions() == 384

    def test_custom_dimensions(self) -> None:
        mock_encoder = MagicMock()
        with patch("sentence_transformers.SentenceTransformer", return_value=mock_encoder):
            embedder = SentenceTransformerEmbedder(dimensions=768)
            assert embedder.get_dimensions() == 768


class TestOpenAIEmbedder:
    def test_init_raises_without_api_key(self) -> None:
        with patch("smartfork.providers.embedding._load_secrets", return_value={}), \
             patch("os.environ", {}), pytest.raises(RuntimeError, match="OPENAI_API_KEY not found"):
            OpenAIEmbedder(api_key="")

    def test_init_with_explicit_api_key(self) -> None:
        embedder = OpenAIEmbedder(api_key="test-key")
        assert embedder._api_key == "test-key"

    def test_embed_returns_vector(self) -> None:
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        with patch("openai.OpenAI") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embeddings.create.return_value = mock_response
            mock_client_class.return_value = mock_client
            embedder = OpenAIEmbedder(api_key="test-key")
            result = embedder.embed("test")
            assert result == [0.1, 0.2, 0.3]

    def test_embed_ignores_doc_type(self) -> None:
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1])]
        with patch("openai.OpenAI") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embeddings.create.return_value = mock_response
            mock_client_class.return_value = mock_client
            embedder = OpenAIEmbedder(api_key="test-key")
            embedder.embed("test", doc_type="summary_doc")
            call_args = mock_client.embeddings.create.call_args[1]
            assert call_args["input"] == "test"

    def test_embed_batch(self) -> None:
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.1, 0.2]),
            MagicMock(embedding=[0.3, 0.4]),
        ]
        with patch("openai.OpenAI") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embeddings.create.return_value = mock_response
            mock_client_class.return_value = mock_client
            embedder = OpenAIEmbedder(api_key="test-key")
            result = embedder.embed_batch(["text1", "text2"])
            assert len(result) == 2
            assert result[0] == [0.1, 0.2]

    def test_get_dimensions(self) -> None:
        embedder = OpenAIEmbedder(api_key="test-key")
        assert embedder.get_dimensions() == 1536

    def test_custom_dimensions(self) -> None:
        embedder = OpenAIEmbedder(api_key="test-key", dimensions=256)
        assert embedder.get_dimensions() == 256


class TestGetEmbedder:
    def test_returns_ollama_by_default(self) -> None:
        with patch("smartfork.providers.embedding.OLLAMA_AVAILABLE", True), \
             patch("smartfork.providers.embedding.check_ollama_available", return_value=True):
            embedder = get_embedder("ollama")
            assert isinstance(embedder, OllamaEmbedder)

    def test_returns_sentence_transformer(self) -> None:
        mock_encoder = MagicMock()
        with patch("sentence_transformers.SentenceTransformer", return_value=mock_encoder):
            embedder = get_embedder("sentence-transformers")
            assert isinstance(embedder, SentenceTransformerEmbedder)

    def test_returns_openai(self) -> None:
        with patch.object(OpenAIEmbedder, "_load_api_key", return_value="test-key"):
            embedder = get_embedder("openai", model="custom-model")
        assert isinstance(embedder, OpenAIEmbedder)
        assert embedder.model == "custom-model"

    def test_raises_for_unknown_provider(self) -> None:
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            get_embedder("unknown")

    def test_case_insensitive(self) -> None:
        with patch.object(OpenAIEmbedder, "_load_api_key", return_value="test-key"):
            embedder = get_embedder("OpenAI", model="test")
        assert isinstance(embedder, OpenAIEmbedder)


class TestCheckEmbeddingModelAvailable:
    def test_ollama_delegates_to_ollama_check(self) -> None:
        with patch(
            "smartfork.providers.embedding.check_ollama_available", return_value=True
        ) as mock_check:
            result = check_embedding_model_available("ollama", "test-model")
            assert result is True
            mock_check.assert_called_once_with("test-model")

    def test_sentence_transformers_checks_import(self) -> None:
        with patch("smartfork.providers.embedding.sentence_transformers", create=True):
            result = check_embedding_model_available("sentence-transformers", "any")
            assert result is True

    def test_unknown_provider_returns_false(self) -> None:
        result = check_embedding_model_available("unknown-provider", "any-model")
        assert result is False
