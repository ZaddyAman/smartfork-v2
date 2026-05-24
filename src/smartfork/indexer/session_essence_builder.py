"""Session essence builder — composes condensed session text for embedding."""

from smartfork.models.session import SessionDocument


class SessionEssenceBuilder:
    """Builds a condensed essence text from a session for embedding.

    Replaces chunk-level embedding with session-level embedding by
    composing task_raw, summary_doc, top reasoning_docs, and tech_tags
    into a single text suitable for embedding models (~500–5000 tokens).
    """

    INSTRUCTION_PREFIX = "Represent this coding session for semantic retrieval: "

    def __init__(
        self,
        max_reasoning_docs: int = 3,
        max_reasoning_length: int = 1500,
        max_total_tokens: int = 5000,
    ) -> None:
        self.max_reasoning_docs = max_reasoning_docs
        self.max_reasoning_length = max_reasoning_length
        self.max_total_tokens = max_total_tokens

    def build_essence(self, session: SessionDocument) -> str:
        """Build an essence string from a ``SessionDocument``.

        The essence is composed of structured sections:
        * Task (always included if non-empty)
        * Summary (always included if non-empty)
        * Reasoning 1..N (top ``max_reasoning_docs``, truncated)
        * Technologies (included if tech_tags are non-empty)

        The total length is kept within ``max_total_tokens`` (approximated as
        4 characters per token).  If the assembled text exceeds the limit,
        reasoning blocks are dropped from the end first; if that is still
        insufficient the result is hard-truncated with an ellipsis.
        """
        parts: list[str] = []

        if session.task_raw:
            parts.append(f"Task: {session.task_raw}")

        if session.summary_doc:
            parts.append(f"Summary: {session.summary_doc}")

        for i, reasoning in enumerate(
            session.reasoning_docs[: self.max_reasoning_docs]
        ):
            stripped = reasoning.strip()
            if not stripped:
                continue
            if len(stripped) > self.max_reasoning_length:
                stripped = stripped[: self.max_reasoning_length] + "..."
            parts.append(f"Reasoning {i + 1}: {stripped}")

        if session.tech_tags:
            parts.append(f"Technologies: {', '.join(session.tech_tags)}")

        essence = "\n\n".join(parts)
        max_chars = self.max_total_tokens * 4

        # Graceful overflow handling: drop reasoning blocks from the end.
        while len(essence) > max_chars and parts:
            # Identify the last reasoning block, if any.
            last_reasoning_index = -1
            for idx, part in enumerate(parts):
                if part.startswith("Reasoning "):
                    last_reasoning_index = idx
            if last_reasoning_index >= 0:
                del parts[last_reasoning_index]
                essence = "\n\n".join(parts)
            else:
                break

        if len(essence) > max_chars:
            essence = essence[: max_chars - 3] + "..."

        return essence

    def build_essence_with_instruction(self, session: SessionDocument) -> str:
        """Build essence with an instruction prefix for instruction-aware models.

        Ollama's instruction-aware embedding models (e.g. qwen3-embedding)
        benefit from a domain-specific prefix that describes the retrieval
        intent.
        """
        return f"{self.INSTRUCTION_PREFIX}{self.build_essence(session)}"
