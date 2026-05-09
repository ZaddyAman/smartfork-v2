"""Fork assembly system for SmartFork v2 — context cloning for new sessions."""

from pathlib import Path
from typing import Any

from loguru import logger

from smartfork.models.fork import ForkIntent
from smartfork.models.session import SessionDocument


class ArtifactDetector:
    """Detects external artifacts (PRDs, commits, issues, ADRs) from session context."""

    @staticmethod
    def detect(files: list[str], task_raw: str) -> list[dict[str, str]]:
        """Find referenced external artifacts.

        Args:
            files: List of file paths from the session.
            task_raw: The raw task description.

        Returns:
            List of {type, path/url, description} dicts.
        """
        artifacts: list[dict[str, str]] = []

        # Detect spec files
        spec_patterns = ["spec", "prd", ".md", "architecture", "design", "ADR"]
        for f in files:
            for pattern in spec_patterns:
                if pattern.lower() in f.lower():
                    artifacts.append({
                        "type": "spec",
                        "path": f,
                        "description": f"Specification document: {Path(f).name}",
                    })
                    break

        # Detect config files
        config_patterns = [".toml", ".yaml", ".json", ".ini", ".cfg", ".env"]
        for f in files:
            if any(f.lower().endswith(p) for p in config_patterns):
                artifacts.append({
                    "type": "config",
                    "path": f,
                    "description": f"Configuration file: {Path(f).name}",
                })

        return artifacts


class ForkAssembler:
    """Assembles fork context documents for priming new sessions.

    Follows the hybrid approach:
    1. Reference external artifacts (never duplicate)
    2. Extract session-specific reasoning (SmartFork's unique value)
    """

    def __init__(self, llm: Any | None = None) -> None:
        self.llm = llm
        self.detector = ArtifactDetector()

    def assemble(
        self,
        session: SessionDocument,
        intent: ForkIntent = ForkIntent.CONTINUE,
        user_query: str = "",
        supersession_warning: str = "",
    ) -> str:
        """Assemble a fork handoff document.

        Args:
            session: The SessionDocument to fork from.
            intent: The fork intent (CONTINUE, REFERENCE, DEBUG, SYNTHESIZE).
            user_query: Optional user query for focus-driven handoffs.
            supersession_warning: Warning if session was superseded.

        Returns:
            A markdown handoff document string.
        """
        if self.llm:
            try:
                return self._llm_assemble(session, intent, user_query, supersession_warning)
            except Exception as e:
                logger.warning(f"LLM fork assembly failed, using fallback: {e}")

        return self._raw_assemble(session, intent, user_query, supersession_warning)

    def _raw_assemble(
        self,
        session: SessionDocument,
        intent: ForkIntent,
        user_query: str,
        supersession_warning: str,
    ) -> str:
        """Assemble handoff without LLM — structured template."""
        artifacts = self.detector.detect(
            session.files_edited + session.files_read, session.task_raw
        )

        lines: list[str] = []
        lines.append(f"# Handoff: {session.project_name} — {session.task_raw[:60]}")
        lines.append(f"**Intent:** {intent.value} | **Session:** {session.session_id}")
        lines.append("")

        if supersession_warning:
            lines.append(f"> ⚠️ {supersession_warning}")
            lines.append("")

        # Section 1: Artifacts to Reference
        lines.append("## Artifacts to Reference")
        if artifacts:
            for a in artifacts:
                lines.append(f"- [{a['type']}] **{Path(a['path']).name}**: {a['path']}")
        else:
            lines.append("- No external artifacts detected.")
        lines.append("")

        # Section 2: What Was Happening
        lines.append("## What Was Happening")
        lines.append(session.task_raw or "No task description available.")
        if session.summary_doc:
            lines.append(f"\n{session.summary_doc}")
        lines.append("")

        # Section 3: Decisions Made
        lines.append("## Decisions Made")
        if session.reasoning_docs:
            for doc in session.reasoning_docs[:3]:
                lines.append(f"- {doc}")
        else:
            lines.append("- No decisions recorded.")
        lines.append("")

        # Section 4: Current State (checklist)
        lines.append("## Current State")
        sf = "x" if session.quality_tag.value == "solution_found" else " "
        lines.append(f"- [{sf}] Solution Found")
        lines.append(f"- [{'x' if session.edit_count > 0 else ' '}] Code Changes Made")
        lines.append(f"- [{'x' if len(session.final_files) > 0 else ' '}] Final Files Produced")
        lines.append("")

        # Section 5: Key Files
        lines.append("## Key Files")
        all_files = set(session.files_edited + session.files_read)
        for f in sorted(all_files)[:10]:
            lines.append(f"- {f}")
        lines.append("")

        # Section 6: Gotchas/Warnings
        lines.append("## Gotchas & Warnings")
        if session.propositions:
            for prop in session.propositions[:3]:
                lines.append(f"- ⚠️ {prop}")
        else:
            lines.append("- None noted.")
        lines.append("")

        # Intent-specific sections
        if intent == ForkIntent.DEBUG:
            lines.append("## Debug Context")
            lines.append("### Error Encountered")
            lines.append(session.task_raw or "Unknown error")
            lines.append("")
            lines.append("### What Was Tried")
            for doc in session.reasoning_docs[:2]:
                lines.append(f"- {doc}")
            lines.append("")
            lines.append("### Root Cause")
            lines.append("(Not determined — review reasoning above)")
            lines.append("")
            lines.append("### Fix Applied")
            if session.quality_tag.value == "solution_found":
                lines.append("A fix was applied and the issue was resolved.")
            else:
                lines.append("No fix was confirmed applied.")
            lines.append("")
            lines.append("### Prevention")
            lines.append("Consider adding tests and error handling for this scenario.")
            lines.append("")

        elif intent == ForkIntent.SYNTHESIZE:
            lines.append("## Overview")
            lines.append(session.summary_doc or session.task_raw)
            lines.append("")
            lines.append("## Timeline")
            lines.append(f"- Session started: {session.session_start}")
            lines.append(f"- Duration: {session.duration_minutes}min")
            lines.append("")
            lines.append("## Architectural Shifts")
            if session.reasoning_docs:
                for doc in session.reasoning_docs[:3]:
                    lines.append(f"- {doc}")
            lines.append("")

        elif intent == ForkIntent.CONTINUE:
            lines.append("## Next Steps")
            if user_query:
                lines.append(f"User goal: {user_query}")
            lines.append("- Review the artifacts and key files above")
            lines.append("- Assess current state checklist")
            lines.append("- Continue from where the session left off")
            lines.append("")

        elif intent == ForkIntent.REFERENCE:
            lines.append("## Skills Suggested")
            for lang in session.languages:
                lines.append(f"- {lang} programming")
            for domain in session.domains:
                lines.append(f"- {domain} domain knowledge")
            lines.append("")

        lines.append("---")
        lines.append(f"Generated by SmartFork v2 | Session: {session.session_id}")
        return "\n".join(lines)

    def _llm_assemble(
        self,
        session: SessionDocument,
        intent: ForkIntent,
        user_query: str,
        supersession_warning: str,
    ) -> str:
        """Assemble handoff using LLM for natural language explanations."""
        assert self.llm is not None
        prompt = (
            f"Create a structured handoff document for this coding session:\n"
            f"Intent: {intent.value}\n"
            f"Project: {session.project_name}\n"
            f"Task: {session.task_raw}\n"
            f"Summary: {session.summary_doc}\n"
            f"Key files: {', '.join(session.files_edited[:10])}\n"
            f"Languages: {', '.join(session.languages)}\n"
        )
        result = self.llm.complete(prompt, max_tokens=500)
        return str(result) if result else self._raw_assemble(
            session, intent, user_query, supersession_warning
        )


class ForkExporter:
    """Exports fork handoff documents to various destinations."""

    @staticmethod
    def save_to_file(
        content: str,
        session_id: str,
        intent: ForkIntent,
        output_dir: str | Path = ".",
    ) -> Path:
        """Save handoff to a markdown file.

        Args:
            content: The handoff markdown content.
            session_id: Session identifier.
            intent: Fork intent.
            output_dir: Directory to save to.

        Returns:
            Path to the saved file.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"handoff_{session_id}_{intent.value}.md"
        path = output_dir / filename
        path.write_text(content, encoding="utf-8")
        logger.info(f"Handoff saved to {path}")
        return path
