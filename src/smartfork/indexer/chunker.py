"""Chunking system for SmartFork v2 — splits SessionDocuments into embeddable chunks."""

import re
from dataclasses import dataclass
from typing import Protocol

from smartfork.models.session import SessionDocument


@dataclass
class Chunk:
    """A single embeddable chunk of session content."""

    chunk_id: str
    session_id: str
    content: str
    doc_type: str  # "task_doc", "summary_doc", "reasoning_doc", "proposition"
    chunk_index: int
    is_code_block: bool = False


@dataclass
class ChunkingConfig:
    """Configuration for chunking behavior."""

    chunk_size: int = 512  # Target tokens per chunk
    chunk_overlap: int = 128  # Overlap tokens between chunks
    code_block_safe: bool = True  # Never split code blocks
    min_chunk_size: int = 50  # Minimum chunk size to keep


class Chunker(Protocol):
    """Protocol for chunking implementations."""

    def chunk(self, session: SessionDocument) -> list[Chunk]:
        ...


# Code fence pattern
CODE_FENCE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)


def _estimate_tokens(text: str) -> int:
    """Rough token estimation: ~4 chars per token."""
    return len(text) // 4


def _is_code_block(text: str) -> bool:
    """Detect if text is a code block based on markers and density."""
    # Check for code fence markers
    if CODE_FENCE_RE.search(text):
        return True

    # Check for high code-line density (>40% code-like lines)
    lines = text.split("\n")
    if not lines:
        return False
    code_lines = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        if any(
            kw in stripped
            for kw in ["def ", "class ", "import ", "from ", "return ", "if ", "for ", "while "]
        ) or stripped.endswith(("{", "}", ";", ":")):
            code_lines += 1
    return (code_lines / len(lines)) >= 0.4


def _split_at_sentence_boundaries(text: str, max_tokens: int) -> list[str]:
    """Split text at sentence boundaries, respecting max token limit.

    Args:
        text: The text to split.
        max_tokens: Maximum tokens per segment.

    Returns:
        List of text segments.
    """
    if _estimate_tokens(text) <= max_tokens:
        return [text]

    # Split on sentence boundaries
    sentences = re.split(r"(?<=[.!?])\s+", text)
    segments: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sentence_tokens = _estimate_tokens(sentence)
        if current_tokens + sentence_tokens > max_tokens and current:
            segments.append(" ".join(current))
            current = [sentence]
            current_tokens = sentence_tokens
        else:
            current.append(sentence)
            current_tokens += sentence_tokens

    if current:
        segments.append(" ".join(current))

    return segments


class MessageBoundaryChunker:
    """Chunker that never splits messages or code blocks.

    Respects conversation turns as natural boundaries.
    """

    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self.config = config or ChunkingConfig()

    def chunk(self, session: SessionDocument) -> list[Chunk]:
        """Chunk a session document into embeddable pieces.

        Args:
            session: The SessionDocument to chunk.

        Returns:
            List of Chunk objects.
        """
        chunks: list[Chunk] = []
        chunk_index = 0

        # 1. Task doc chunk
        if session.task_raw.strip():
            chunks.append(
                Chunk(
                    chunk_id=f"{session.session_id}_task",
                    session_id=session.session_id,
                    content=f"Task: {session.task_raw}",
                    doc_type="task_doc",
                    chunk_index=chunk_index,
                )
            )
            chunk_index += 1

        # 2. Reasoning doc chunks (split at sentence boundaries)
        for reasoning in session.reasoning_docs:
            if not reasoning.strip():
                continue
            segments = _split_at_sentence_boundaries(reasoning, self.config.chunk_size)
            for segment in segments:
                if _estimate_tokens(segment) >= self.config.min_chunk_size:
                    chunks.append(
                        Chunk(
                            chunk_id=f"{session.session_id}_reasoning_{chunk_index}",
                            session_id=session.session_id,
                            content=segment,
                            doc_type="reasoning_doc",
                            chunk_index=chunk_index,
                        )
                    )
                    chunk_index += 1

        # 3. Summary doc chunk
        if session.summary_doc.strip():
            chunks.append(
                Chunk(
                    chunk_id=f"{session.session_id}_summary",
                    session_id=session.session_id,
                    content=session.summary_doc,
                    doc_type="summary_doc",
                    chunk_index=chunk_index,
                )
            )
            chunk_index += 1

        return chunks


class ContextualChunker:
    """Chunker that adds Anthropic-style context headers to each chunk.

    Headers follow the format:
    [Project: {project} | Session: {session_id} | Task: {task_summary}]
    """

    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self.config = config or ChunkingConfig()
        self._base_chunker = MessageBoundaryChunker(config)

    def chunk(self, session: SessionDocument) -> list[Chunk]:
        """Chunk with context headers prepended.

        Args:
            session: The SessionDocument to chunk.

        Returns:
            List of Chunk objects with context headers.
        """
        base_chunks = self._base_chunker.chunk(session)

        # Build context header
        task_summary = session.task_raw[:80] if session.task_raw else "unknown"
        context_header = (
            f"[Project: {session.project_name} | "
            f"Session: {session.session_id} | "
            f"Task: {task_summary}]"
        )

        for chunk in base_chunks:
            chunk.content = f"{context_header}\n\n{chunk.content}"

        return base_chunks


def create_chunker(
    chunker_type: str = "message_boundary",
    config: ChunkingConfig | None = None,
) -> Chunker:
    """Factory function to create a chunker.

    Args:
        chunker_type: "message_boundary" or "contextual".
        config: Optional chunking configuration.

    Returns:
        A Chunker instance.

    Raises:
        ValueError: If chunker_type is unknown.
    """
    if chunker_type == "message_boundary":
        return MessageBoundaryChunker(config)
    if chunker_type == "contextual":
        return ContextualChunker(config)
    raise ValueError(
        f"Unknown chunker type: '{chunker_type}'. "
        "Valid options: message_boundary, contextual"
    )
