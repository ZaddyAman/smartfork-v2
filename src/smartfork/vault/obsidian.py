"""Obsidian vault generator for SmartFork v2."""

from pathlib import Path

from loguru import logger

from smartfork.models.session import SessionDocument


def _escape_yaml(text: str) -> str:
    """Escape special characters for YAML values."""
    special_chars = [
        '"', "'", ":", "#", "{", "}", "[", "]", ",", "&", "*", "?", "|", "-",
        "<", ">", "=", "!", "%", "@", "`",
    ]
    if any(c in text for c in special_chars):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def _generate_frontmatter(session: SessionDocument) -> str:
    """Generate YAML frontmatter for a session note."""
    qt = session.quality_tag
    tag_value = qt.value if hasattr(qt, "value") else qt
    lines = [
        "---",
        f"session_id: {session.session_id}",
        f"agent: {session.agent}",
        f"project: {_escape_yaml(session.project_name)}",
        f"session_start: {session.session_start}",
        f"session_end: {session.session_end}",
        f"duration_minutes: {session.duration_minutes}",
        f"quality_tag: {tag_value}",
        "domains:",
    ]
    for domain in session.domains:
        lines.append(f"  - {domain}")
    lines.append("languages:")
    for lang in session.languages:
        lines.append(f"  - {lang}")
    lines.append("tech_tags:")
    for tag in session.tech_tags:
        lines.append(f"  - {tag}")
    lines.append("files_edited:")
    for f in session.files_edited:
        lines.append(f"  - {_escape_yaml(f)}")
    lines.append("---")
    return "\n".join(lines)


class ObsidianVaultGenerator:
    """Generates an Obsidian-compatible knowledge vault from sessions."""

    def __init__(self) -> None:
        pass

    def generate(
        self,
        sessions: list[SessionDocument],
        vault_dir: str | Path = "./smartfork_vault",
        project_folders: bool = False,
    ) -> Path:
        """Generate an Obsidian vault from session documents.

        Args:
            sessions: List of SessionDocuments to include.
            vault_dir: Directory to create the vault in.
            project_folders: If True, group sessions by project in subfolders.

        Returns:
            Path to the generated vault directory.
        """
        vault_dir = Path(vault_dir)
        vault_dir.mkdir(parents=True, exist_ok=True)

        if not sessions:
            logger.warning("No sessions provided, creating empty vault.")
            self._create_empty_vault(vault_dir)
            return vault_dir

        # Create .obsidian config
        obsidian_dir = vault_dir / ".obsidian"
        obsidian_dir.mkdir(exist_ok=True)
        app_config = '{"newFileLocation": "folder", "newFileFolderPath": "sessions"}\n'
        graph_config = '{"collapse-filter": false, "search": "", "showTags": true}\n'
        (obsidian_dir / "app.json").write_text(app_config)
        (obsidian_dir / "graph.json").write_text(graph_config)

        # Group by project if requested
        if project_folders:
            groups: dict[str, list[SessionDocument]] = {}
            for s in sessions:
                groups.setdefault(s.project_name, []).append(s)
        else:
            groups = {"sessions": sessions}

        # Create session notes
        for group_name, group_sessions in groups.items():
            group_dir = vault_dir / group_name if project_folders else vault_dir
            group_dir.mkdir(exist_ok=True)

            for session in group_sessions:
                note_path = group_dir / f"{session.session_id}.md"
                content = self._generate_note(session)
                note_path.write_text(content, encoding="utf-8")

        # Create MOC (Map of Content)
        moc_content = self._generate_moc(sessions, project_folders)
        (vault_dir / "MOC.md").write_text(moc_content, encoding="utf-8")

        # Create Graph View
        graph_content = self._generate_graph_view(sessions)
        (vault_dir / "Graph View.md").write_text(graph_content, encoding="utf-8")

        logger.info(f"Vault generated at {vault_dir} with {len(sessions)} sessions")
        return vault_dir

    def _create_empty_vault(self, vault_dir: Path) -> None:
        """Create an empty vault with placeholder files."""
        (vault_dir / ".obsidian").mkdir(exist_ok=True)
        (vault_dir / ".obsidian" / "app.json").write_text("{}")
        (vault_dir / "README.md").write_text(
            "# SmartFork Vault\n\nNo sessions indexed yet. Run `smartfork index` to populate.\n"
        )

    def _generate_note(self, session: SessionDocument) -> str:
        """Generate a single session note."""
        lines = [_generate_frontmatter(session)]
        lines.append(f"# {session.task_raw[:60]}")
        lines.append("")
        lines.append(f"**Agent:** {session.agent}")
        lines.append(f"**Project:** [[{session.project_name}]]")
        qt = session.quality_tag
        tag_value = qt.value if hasattr(qt, "value") else qt
        lines.append(f"**Quality:** {tag_value}")
        lines.append(f"**Duration:** {session.duration_minutes} min")
        lines.append("")

        if session.summary_doc:
            lines.append("## Summary")
            lines.append(session.summary_doc)
            lines.append("")

        if session.reasoning_docs:
            lines.append("## Key Decisions")
            for doc in session.reasoning_docs:
                lines.append(f"- {doc}")
            lines.append("")

        if session.files_edited:
            lines.append("## Files Edited")
            for f in session.files_edited:
                lines.append(f"- {f}")
            lines.append("")



        return "\n".join(lines)

    def _generate_moc(self, sessions: list[SessionDocument], project_folders: bool) -> str:
        """Generate Map of Content."""
        lines = [
            "# SmartFork Session Map",
            "",
            "## Sessions",
            "",
            "```dataview",
            "TABLE agent, quality_tag, duration_minutes, session_start",
            'FROM "sessions"',
            "SORT session_start DESC",
            "```",
            "",
            "## Projects",
            "",
        ]

        projects = sorted({s.project_name for s in sessions})
        for project in projects:
            count = sum(1 for s in sessions if s.project_name == project)
            lines.append(f"- [[{project}]] ({count} sessions)")

        lines.append("")
        lines.append("## Quality Breakdown")
        lines.append("")
        lines.append("```dataview")
        lines.append("TABLE rows.file.link as Session, quality_tag")
        lines.append('FROM "sessions"')
        lines.append("GROUP BY quality_tag")
        lines.append("```")
        lines.append("")

        # Mermaid graph
        lines.append("## Connection Graph")
        lines.append("```mermaid")
        lines.append("graph TD")
        for session in sessions:
            sid = session.session_id.replace("-", "_")
            proj = session.project_name.replace("-", "_")
            lines.append(f"    {sid}[{session.task_raw[:20]}] --> {proj}[{session.project_name}]")
            for lang in session.languages[:2]:
                lines.append(f"    {sid} --> lang_{lang}({lang})")
        lines.append("```")

        return "\n".join(lines)

    def _generate_graph_view(self, sessions: list[SessionDocument]) -> str:
        """Generate Graph View with wiki-links."""
        lines = [
            "# Graph View",
            "",
            "## All Sessions",
            "",
        ]
        for session in sessions:
            lines.append(f"- [[{session.session_id}|{session.task_raw[:40]}]]")
        lines.append("")
        lines.append("## By Project")
        lines.append("")
        projects = sorted({s.project_name for s in sessions})
        for project in projects:
            lines.append(f"### {project}")
            for session in sessions:
                if session.project_name == project:
                    lines.append(f"- [[{session.session_id}|{session.task_raw[:40]}]]")
            lines.append("")
        return "\n".join(lines)
