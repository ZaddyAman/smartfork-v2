"""Index-time intelligence for SmartFork v2 — quality tags, tech tags, summaries."""

import re
from collections.abc import Callable

from loguru import logger

from smartfork.models.progress import ProgressEvent
from smartfork.models.session import QualityTag, SessionDocument

# Known tech/framework keywords for fallback extraction
KNOWN_TECH: dict[str, str] = {
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "react": "React",
    "vue": "Vue",
    "angular": "Angular",
    "svelte": "Svelte",
    "next": "Next.js",
    "nuxt": "Nuxt",
    "express": "Express",
    "pydantic": "Pydantic",
    "sqlalchemy": "SQLAlchemy",
    "prisma": "Prisma",
    "drizzle": "Drizzle",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "sqlite": "SQLite",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "terraform": "Terraform",
    "jwt": "JWT",
    "oauth": "OAuth",
    "graphql": "GraphQL",
    "grpc": "gRPC",
    "websocket": "WebSocket",
    "celery": "Celery",
    "rabbitmq": "RabbitMQ",
    "kafka": "Kafka",
    "pytest": "pytest",
    "jest": "Jest",
    "cypress": "Cypress",
    "tailwind": "Tailwind",
    "bootstrap": "Bootstrap",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "transformers": "Transformers",
    "langchain": "LangChain",
    "chromadb": "ChromaDB",
}


def _extract_title_fallback(task_raw: str) -> str:
    """Extract a title from task_raw without LLM."""
    if not task_raw.strip():
        return "Untitled Session"
    # Take first sentence, max 80 chars
    first = task_raw.split(".")[0].strip()
    if len(first) > 80:
        first = first[:77] + "..."
    return first


def _extract_summary_fallback(reasoning_docs: list[str], task_raw: str) -> str:
    """Create a summary from reasoning docs without LLM."""
    parts: list[str] = []
    if task_raw:
        parts.append(f"Task: {task_raw}.")
    if reasoning_docs:
        # Take first 2 reasoning blocks for summary
        for doc in reasoning_docs[:2]:
            first_sentence = doc.split(".")[0].strip()
            if first_sentence and len(parts) < 3:
                parts.append(first_sentence)
    return " ".join(parts) if parts else "No summary available."


def _classify_quality(task_raw: str, reasoning_docs: list[str]) -> QualityTag:
    """Classify session quality without LLM using keyword heuristics."""
    combined = (task_raw + " " + " ".join(reasoning_docs)).lower()

    # Strong solution indicators
    solution_keywords = [
        "fixed", "solved", "resolved", "working", "completed",
        "implemented", "deployed", "merged", "finished",
    ]
    if any(kw in combined for kw in solution_keywords):
        return QualityTag.SOLUTION_FOUND

    # Dead end indicators
    dead_end_keywords = [
        "could not", "unable to", "didn't work", "abandoned",
        "gave up", "not possible", "blocked", "stuck",
    ]
    if any(kw in combined for kw in dead_end_keywords):
        return QualityTag.DEAD_END

    # Partial indicators
    partial_keywords = [
        "partial", "in progress", "wip", "still need",
        "remaining", "todo", "not yet",
    ]
    if any(kw in combined for kw in partial_keywords):
        return QualityTag.PARTIAL

    # Reference indicators
    reference_keywords = [
        "setup", "install", "configure", "document", "readme",
        "reference", "example", "template",
    ]
    if any(kw in combined for kw in reference_keywords):
        return QualityTag.REFERENCE

    return QualityTag.PARTIAL  # Default to partial rather than unknown


def _extract_tech_tags(task_raw: str, files: list[str]) -> list[str]:
    """Extract tech tags from task and file names without LLM."""
    combined = (task_raw + " " + " ".join(files)).lower()
    tags: set[str] = set()
    for keyword, tag in KNOWN_TECH.items():
        if keyword in combined:
            tags.add(tag)
    return sorted(tags)


def _extract_propositions(reasoning_docs: list[str]) -> list[str]:
    """Extract atomic facts from reasoning docs without LLM."""
    propositions: list[str] = []
    for doc in reasoning_docs[:3]:
        # Take first sentence of each reasoning block
        sentences = re.split(r"[.!?]\s+", doc)
        if sentences:
            first = sentences[0].strip()
            if len(first) > 10 and len(first) < 200:
                propositions.append(first)
    return propositions[:3]


class IndexIntelligence:
    """Enriches session documents with LLM-powered intelligence.

    When LLM is available, uses it for high-quality enrichment.
    When LLM is unavailable, falls back to keyword-based heuristics.

    The class is designed so that enrich() is always safe to call —
    it will never raise an error, even if LLM is completely unavailable.
    """

    def __init__(self, llm: object | None = None) -> None:
        """Initialize with an optional LLM provider.

        Args:
            llm: An LLMProvider instance, or None for fallback-only mode.
        """
        self.llm = llm

    def enrich(
        self,
        session: SessionDocument,
        progress_callback: Callable[[ProgressEvent], None] | None = None,
    ) -> SessionDocument:
        """Enrich a single session with title, summary, quality, tech tags, propositions.

        Args:
            session: The SessionDocument to enrich.
            progress_callback: Optional callback for per-step progress (title,
                summary, tags, quality, propositions).

        Returns:
            The same SessionDocument, mutated with enriched fields.
        """
        steps_total = 5

        # ── Title ──
        if progress_callback:
            progress_callback(ProgressEvent(
                phase="enriching", enrich_step="title",
                enrich_done=0, enrich_total=steps_total,
            ))
        if self.llm:
            try:
                session.task_raw = self._llm_title(session.task_raw)
            except Exception as e:
                logger.warning(f"LLM titling failed, using fallback: {e}")
                session.task_raw = _extract_title_fallback(session.task_raw)
        else:
            session.task_raw = _extract_title_fallback(session.task_raw)

        # ── Summary ──
        if progress_callback:
            progress_callback(ProgressEvent(
                phase="enriching", enrich_step="summary",
                enrich_done=1, enrich_total=steps_total,
            ))
        if self.llm:
            try:
                session.summary_doc = self._llm_summary(session)
            except Exception as e:
                logger.warning(f"LLM summary failed, using fallback: {e}")
                session.summary_doc = _extract_summary_fallback(
                    session.reasoning_docs, session.task_raw
                )
        else:
            session.summary_doc = _extract_summary_fallback(
                session.reasoning_docs, session.task_raw
            )

        # ── Tags ──
        if progress_callback:
            progress_callback(ProgressEvent(
                phase="enriching", enrich_step="tags",
                enrich_done=2, enrich_total=steps_total,
            ))
        all_files = session.files_edited + session.files_read + session.files_mentioned
        if self.llm:
            try:
                session.tech_tags = self._llm_tech_tags(session.task_raw, all_files)
            except Exception as e:
                logger.warning(f"LLM tech tagging failed, using fallback: {e}")
                session.tech_tags = _extract_tech_tags(session.task_raw, all_files)
        else:
            session.tech_tags = _extract_tech_tags(session.task_raw, all_files)

        # ── Quality ──
        if progress_callback:
            progress_callback(ProgressEvent(
                phase="enriching", enrich_step="quality",
                enrich_done=3, enrich_total=steps_total,
            ))
        if self.llm:
            try:
                session.quality_tag = self._llm_quality(session)
            except Exception as e:
                logger.warning(f"LLM quality tagging failed, using fallback: {e}")
                session.quality_tag = _classify_quality(
                    session.task_raw, session.reasoning_docs
                )
        else:
            session.quality_tag = _classify_quality(
                session.task_raw, session.reasoning_docs
            )

        # ── Propositions ──
        if progress_callback:
            progress_callback(ProgressEvent(
                phase="enriching", enrich_step="propositions",
                enrich_done=4, enrich_total=steps_total,
            ))
        if self.llm:
            try:
                session.propositions = self._llm_propositions(session.reasoning_docs)
            except Exception as e:
                logger.warning(f"LLM proposition extraction failed, using fallback: {e}")
                session.propositions = _extract_propositions(session.reasoning_docs)
        else:
            session.propositions = _extract_propositions(session.reasoning_docs)

        if progress_callback:
            progress_callback(ProgressEvent(
                phase="enriching", enrich_step="done",
                enrich_done=steps_total, enrich_total=steps_total,
            ))

        return session

    def enrich_batch(
        self,
        sessions: list[SessionDocument],
        progress_callback: Callable[[ProgressEvent], None] | None = None,
    ) -> list[SessionDocument]:
        """Enrich a batch of sessions.

        Args:
            sessions: List of SessionDocuments to enrich.
            progress_callback: Optional callback(ProgressEvent) for progress.

        Returns:
            The enriched sessions (same objects, mutated in place).
        """
        for session in sessions:
            self.enrich(session, progress_callback=progress_callback)
        return sessions

    # LLM-based methods (stubs — will call self.llm when available)
    def _llm_title(self, task_raw: str) -> str:
        """Generate a title using LLM."""
        prompt = (
            f"Generate a short, descriptive title (max 80 chars) for this coding task:\n\n"
            f"{task_raw}\n\nTitle:"
        )
        result = self.llm.complete(prompt, max_tokens=20)  # type: ignore[union-attr]
        return str(result).strip() if result else _extract_title_fallback(task_raw)

    def _llm_summary(self, session: SessionDocument) -> str:
        """Generate a 3-sentence summary using LLM."""
        context = f"Task: {session.task_raw}\n"
        if session.reasoning_docs:
            context += f"Key points: {' '.join(session.reasoning_docs[:2])}"
        prompt = (
            f"Summarize this coding session in 3 sentences:\n\n{context}\n\nSummary:"
        )
        result = self.llm.complete(prompt, max_tokens=150)  # type: ignore[union-attr]
        return str(result).strip() if result else _extract_summary_fallback(
            session.reasoning_docs, session.task_raw
        )

    def _llm_quality(self, session: SessionDocument) -> QualityTag:
        """Classify session quality using LLM."""
        prompt = (
            f"Classify this coding session outcome as one of: "
            f"solution_found, dead_end, partial, reference.\n\n"
            f"Task: {session.task_raw}\n"
            f"Summary: {session.summary_doc}\n\n"
            f"Classification:"
        )
        result = self.llm.complete(prompt, max_tokens=10)  # type: ignore[union-attr]
        result_str = str(result).strip().lower()
        for tag in QualityTag:
            if tag.value in result_str:
                return tag
        return _classify_quality(session.task_raw, session.reasoning_docs)

    def _llm_tech_tags(self, task_raw: str, files: list[str]) -> list[str]:
        """Extract tech tags using LLM."""
        prompt = (
            f"List the technologies, frameworks, and libraries mentioned, "
            f"comma-separated:\n\nTask: {task_raw}\nFiles: {', '.join(files[:10])}\n\nTags:"
        )
        result = self.llm.complete(prompt, max_tokens=50)  # type: ignore[union-attr]
        if result:
            return [t.strip() for t in str(result).split(",") if t.strip()]
        return _extract_tech_tags(task_raw, files)

    def _llm_propositions(self, reasoning_docs: list[str]) -> list[str]:
        """Extract atomic facts using LLM."""
        if not reasoning_docs:
            return []
        prompt = (
            f"Extract up to 3 atomic factual statements from these coding session notes, "
            f"one per line:\n\n{' '.join(reasoning_docs[:2])}\n\nFacts:"
        )
        result = self.llm.complete(prompt, max_tokens=100)  # type: ignore[union-attr]
        if result:
            lines = [line.strip("- ").strip() for line in str(result).split("\n") if line.strip()]
            return lines[:3]
        return _extract_propositions(reasoning_docs)
