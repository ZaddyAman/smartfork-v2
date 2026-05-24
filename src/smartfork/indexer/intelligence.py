"""Index-time intelligence for SmartFork v2 — quality tags, tech tags, summaries."""

import json
from collections.abc import Callable
from typing import cast

from loguru import logger

from smartfork.models.enrichment import SessionEnrichment
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


class IndexIntelligence:
    """Enriches session documents with LLM-powered intelligence.

    When LLM is available: uses 1 structured call for all enrichment.
    When LLM is unavailable: falls back to keyword-based heuristics.

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
        """Enrich a single session with title, summary, quality, and tech tags.

        Args:
            session: The SessionDocument to enrich.
            progress_callback: Optional callback for per-step progress.

        Returns:
            The same SessionDocument, mutated with enriched fields.
        """
        if progress_callback:
            progress_callback(ProgressEvent(
                phase="enriching", enrich_step="structured",
                enrich_done=0, enrich_total=1,
            ))

        if self.llm:
            try:
                enrichment = self._llm_enrich_structured(session)
                session.task_raw = enrichment.title
                session.summary_doc = enrichment.summary
                session.quality_tag = enrichment.quality_tag
                session.tech_tags = enrichment.tech_tags
            except Exception as e:
                logger.warning(f"LLM enrichment failed, using fallback: {e}")
                self._fallback_enrich(session)
        else:
            self._fallback_enrich(session)

        if progress_callback:
            progress_callback(ProgressEvent(
                phase="enriching", enrich_step="done",
                enrich_done=1, enrich_total=1,
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

    def _llm_enrich_structured(self, session: SessionDocument) -> SessionEnrichment:
        """Single structured LLM call for all enrichment.

        Args:
            session: The SessionDocument to enrich.

        Returns:
            A SessionEnrichment with title, summary, quality_tag, and tech_tags.
        """
        if self.llm is None:
            raise RuntimeError("_llm_enrich_structured called without LLM")

        context_parts: list[str] = [
            f"Task: {session.task_raw}",
            f"Files: {', '.join(session.files_edited[:5])}",
            "Reasoning snippets:",
        ]
        for i, reasoning in enumerate(session.reasoning_docs[:2]):
            context_parts.append(f"{i + 1}. {reasoning[:200]}")

        context = "\n".join(context_parts)

        prompt = f"""Analyze this coding session and return structured JSON:

{context}

Return this exact JSON structure:
{{
    "title": "Short descriptive title (max 80 chars)",
    "summary": "3-sentence summary of what happened",
    "quality_tag": "solution_found" or "dead_end" or "partial" or "reference",
    "tech_tags": ["list", "of", "technologies"]
}}

Rules:
- title: Max 80 characters, descriptive
- summary: Exactly 3 sentences covering task, approach, outcome
- quality_tag: Choose the best fit
- tech_tags: Include frameworks, libraries, languages mentioned
"""

        # Use structured output if available
        try:
            result = self.llm.complete_structured(  # type: ignore[attr-defined]
                prompt,
                output_schema=SessionEnrichment,
                temperature=0.1,
            )
            if result is not None:
                return cast(SessionEnrichment, result)
        except AttributeError:
            pass

        # Fallback to text parsing
        text_result = self.llm.complete(prompt, max_tokens=300)  # type: ignore[attr-defined]
        return self._parse_enrichment_result(str(text_result))

    def _parse_enrichment_result(self, text: str) -> SessionEnrichment:
        """Parse text result into SessionEnrichment.

        Args:
            text: Raw text response from LLM.

        Returns:
            SessionEnrichment with parsed or default values.
        """
        try:
            # Try to find JSON in the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                return SessionEnrichment(
                    title=data.get("title", "Untitled Session"),
                    summary=data.get("summary", "No summary available."),
                    quality_tag=QualityTag(data.get("quality_tag", "partial")),
                    tech_tags=data.get("tech_tags", []),
                )
        except (json.JSONDecodeError, ValueError):
            pass

        # Ultimate fallback
        return SessionEnrichment(
            title="Untitled Session",
            summary="No summary available.",
            quality_tag=QualityTag.PARTIAL,
            tech_tags=[],
        )

    def _fallback_enrich(self, session: SessionDocument) -> None:
        """Heuristic enrichment without LLM.

        Args:
            session: The SessionDocument to mutate in place.
        """
        # Title
        if not session.task_raw or session.task_raw == "Untitled Session":
            session.task_raw = _extract_title_fallback(session.task_raw)

        # Summary
        session.summary_doc = _extract_summary_fallback(
            session.reasoning_docs, session.task_raw
        )

        # Quality
        session.quality_tag = _classify_quality(
            session.task_raw, session.reasoning_docs
        )

        # Tech tags
        all_files = session.files_edited + session.files_read + session.files_mentioned
        session.tech_tags = _extract_tech_tags(session.task_raw, all_files)
