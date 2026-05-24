"""Tests for the chunking system."""

from smartfork.indexer.chunker import (
    ChunkingConfig,
    ContextualChunker,
    MessageBoundaryChunker,
    _estimate_tokens,
    _is_code_block,
    _split_at_sentence_boundaries,
    create_chunker,
)
from smartfork.models.session import QualityTag, SessionDocument


def _make_session(**kwargs) -> SessionDocument:
    """Create a test SessionDocument with defaults."""
    defaults = {
        "session_id": "test-sess",
        "agent": "kilocode",
        "project_name": "myproject",
        "project_root": "/home/dev",
        "task_raw": "Fix authentication bug",
        "reasoning_docs": [],
        "summary_doc": "",
        "quality_tag": QualityTag.UNKNOWN,
    }
    defaults.update(kwargs)
    return SessionDocument(**defaults)


class TestHelpers:
    def test_estimate_tokens(self) -> None:
        # ~4 chars per token
        assert _estimate_tokens("hello world") == 2  # 11 chars / 4
        assert _estimate_tokens("") == 0

    def test_is_code_block_fenced(self) -> None:
        assert _is_code_block("```python\nprint('hello')\n```") is True

    def test_is_code_block_not_code(self) -> None:
        assert _is_code_block("This is regular text. No code here.") is False

    def test_is_code_block_code_dense(self) -> None:
        text = "\n".join([
            "def foo():", "    return 42", "def bar():", "    return 43",
            "class Baz:", "    pass", "", "# comment", "x = 1"
        ])
        assert _is_code_block(text) is True

    def test_split_sentence_boundaries(self) -> None:
        text = "First sentence. Second sentence. Third sentence."
        segments = _split_at_sentence_boundaries(text, 5)  # very small max
        assert len(segments) >= 2

    def test_split_short_text_stays_intact(self) -> None:
        text = "Short text."
        segments = _split_at_sentence_boundaries(text, 999)
        assert len(segments) == 1


class TestChunkingConfig:
    def test_defaults(self) -> None:
        cfg = ChunkingConfig()
        assert cfg.chunk_size == 512
        assert cfg.chunk_overlap == 128
        assert cfg.code_block_safe is True


class TestMessageBoundaryChunker:
    def test_chunks_task(self) -> None:
        session = _make_session(task_raw="Fix the auth bug")
        chunker = MessageBoundaryChunker()
        chunks = chunker.chunk(session)
        task_chunks = [c for c in chunks if c.doc_type == "task_doc"]
        assert len(task_chunks) == 1
        assert "Fix the auth bug" in task_chunks[0].content

    def test_chunks_reasoning(self) -> None:
        session = _make_session(
            task_raw="Test",
            reasoning_docs=[
                "The JWT token was expired. We need to refresh it before the next request. "
                "This involves updating the auth middleware to handle the new refresh flow. "
                "Additionally, we should cache the new token to avoid "
                "repeated authentication overhead."
            ]
        )
        chunker = MessageBoundaryChunker()
        chunks = chunker.chunk(session)
        reasoning_chunks = [c for c in chunks if c.doc_type == "reasoning_doc"]
        assert len(reasoning_chunks) >= 1

    def test_splits_long_reasoning(self) -> None:
        long_reasoning = ". ".join([f"Sentence number {i}" for i in range(100)])
        session = _make_session(
            task_raw="Test",
            reasoning_docs=[long_reasoning]
        )
        chunker = MessageBoundaryChunker(ChunkingConfig(chunk_size=50))
        chunks = chunker.chunk(session)
        reasoning_chunks = [c for c in chunks if c.doc_type == "reasoning_doc"]
        assert len(reasoning_chunks) > 1

    def test_skips_empty_content(self) -> None:
        session = _make_session(task_raw="")
        chunker = MessageBoundaryChunker()
        chunks = chunker.chunk(session)
        task_chunks = [c for c in chunks if c.doc_type == "task_doc"]
        assert len(task_chunks) == 0

    def test_chunk_ids_are_unique(self) -> None:
        session = _make_session(
            task_raw="Task",
            reasoning_docs=["Reason 1", "Reason 2"],
            summary_doc="Summary",
        )
        chunker = MessageBoundaryChunker()
        chunks = chunker.chunk(session)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))


class TestContextualChunker:
    def test_adds_context_header(self) -> None:
        session = _make_session(
            task_raw="Fix auth bug",
            project_name="myapp",
        )
        chunker = ContextualChunker()
        chunks = chunker.chunk(session)
        for chunk in chunks:
            assert "[Project: myapp" in chunk.content
            assert "Session: test-sess" in chunk.content


class TestCreateChunker:
    def test_creates_message_boundary(self) -> None:
        chunker = create_chunker("message_boundary")
        assert isinstance(chunker, MessageBoundaryChunker)

    def test_creates_contextual(self) -> None:
        chunker = create_chunker("contextual")
        assert isinstance(chunker, ContextualChunker)

    def test_raises_for_unknown(self) -> None:
        import pytest
        with pytest.raises(ValueError, match="Unknown chunker type"):
            create_chunker("unknown")
