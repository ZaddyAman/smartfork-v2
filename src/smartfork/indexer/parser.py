"""Session parser — converts RawSessionData to SessionDocument."""

import re
from pathlib import Path

from smartfork.models.session import QualityTag, RawSessionData, RawTurn, SessionDocument

# -- Domain extraction --------------------------------------------------------

DOMAIN_PATTERNS: dict[str, str] = {
    "auth": "auth",
    "login": "auth",
    "jwt": "auth",
    "oauth": "auth",
    "session": "auth",
    "token": "auth",
    "permission": "auth",
    "backend": "backend",
    "api": "backend",
    "server": "backend",
    "routes": "backend",
    "controllers": "backend",
    "services": "backend",
    "models": "backend",
    "middleware": "backend",
    "frontend": "frontend",
    "components": "frontend",
    "pages": "frontend",
    "views": "frontend",
    "hooks": "frontend",
    "styles": "frontend",
    "css": "frontend",
    "assets": "frontend",
    "database": "database",
    "db": "database",
    "migrations": "database",
    "schema": "database",
    "sql": "database",
    "queries": "database",
    "orm": "database",
    "rag": "rag",
    "retrieval": "rag",
    "embedding": "rag",
    "vector": "rag",
    "chunk": "rag",
    "search": "rag",
    "pipeline": "rag",
    "ingest": "ingest",
    "load": "ingest",
    "import": "ingest",
    "parse": "ingest",
    "extract": "ingest",
    "crawl": "ingest",
    "scraper": "ingest",
    "testing": "testing",
    "test": "testing",
    "spec": "testing",
    "mock": "testing",
    "fixture": "testing",
    "conftest": "testing",
    "devops": "devops",
    "docker": "devops",
    "k8s": "devops",
    "deploy": "devops",
    "ci": "devops",
    "cd": "devops",
    "github/workflows": "devops",
    "terraform": "devops",
    "config": "config",
    "settings": "config",
    "env": "config",
    "toml": "config",
    "yaml": "config",
    "json": "config",
    "cli": "cli",
    "command": "cli",
    "typer": "cli",
    "click": "cli",
    "argparse": "cli",
}

# -- Language extraction ------------------------------------------------------

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyx": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".c": "c",
    ".h": "c",
    ".cpp": "c++",
    ".hpp": "c++",
    ".cc": "c++",
    ".cxx": "c++",
    ".cs": "c#",
    ".rb": "ruby",
    ".php": "php",
    ".sql": "sql",
    ".psql": "sql",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".ps1": "powershell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".xml": "markup",
    ".html": "markup",
    ".htm": "markup",
    ".css": "css",
    ".scss": "css",
    ".sass": "css",
    ".less": "css",
    ".md": "markdown",
    ".mdx": "markdown",
    ".rst": "markdown",
    ".dockerfile": "docker",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".proto": "protobuf",
    ".tf": "terraform",
    ".r": "r",
    ".dart": "dart",
    ".lua": "lua",
    ".zig": "zig",
    ".nim": "nim",
    ".vue": "vue",
    ".svelte": "svelte",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hs": "haskell",
}

CODE_LANGUAGES: set[str] = {
    "python",
    "javascript",
    "typescript",
    "rust",
    "go",
    "java",
    "kotlin",
    "swift",
    "c",
    "c++",
    "c#",
    "ruby",
    "php",
    "sql",
    "elixir",
    "erlang",
    "haskell",
    "lua",
    "r",
    "dart",
    "zig",
    "nim",
    "scala",
}

CODE_EXTENSIONS: set[str] = {
    ext for ext, lang in EXTENSION_TO_LANGUAGE.items() if lang in CODE_LANGUAGES
}

CONFIG_EXTENSIONS: set[str] = {".yaml", ".yml", ".json", ".toml", ".env", ".ini", ".cfg"}

# -- Layer extraction ---------------------------------------------------------

FRONTEND_PATTERNS = [
    "/components/",
    "/pages/",
    "/views/",
    "/hooks/",
    "/styles/",
    ".tsx",
    ".jsx",
    ".css",
]

BACKEND_PATTERNS = [
    "/api/",
    "/server/",
    "/routes/",
    "/controllers/",
    "/services/",
    "/models/",
]

_DRIVE_RE = re.compile(r"^[A-Za-z]:\\?$")


def derive_project_name(workspace_dir: str, file_paths: list[str]) -> str:
    """Derive a project name from workspace directory or file paths.

    Priority:
        1. Basename of ``workspace_dir`` if non-empty.
        2. Common root folder shared by ``file_paths``.
        3. First directory component of the first file path.
        4. ``"unknown_project"``
    """
    if workspace_dir:
        name = Path(workspace_dir).name
        if name:
            return name

    if not file_paths:
        return "unknown_project"

    # Find common root folder
    paths = [Path(f) for f in file_paths]
    min_len = min(len(p.parts) for p in paths)
    common_parts: list[str] = []
    for i in range(min_len):
        part = paths[0].parts[i]
        if all(p.parts[i] == part for p in paths):
            common_parts.append(part)
        else:
            break

    cleaned = [
        p for p in common_parts
        if p not in ("/", "\\", ".", "..") and not _DRIVE_RE.match(p)
    ]
    if cleaned:
        return cleaned[-1]

    # Fallback to first directory in first file
    first_parts = [
        p for p in paths[0].parts
        if p not in ("/", "\\", ".", "..") and not _DRIVE_RE.match(p)
    ]
    if len(first_parts) >= 2:
        return first_parts[0]

    return "unknown_project"


def extract_domains(file_paths: list[str]) -> list[str]:
    """Extract domain tags from file paths.

    Args:
        file_paths: List of file paths.

    Returns:
        Sorted list of unique domain strings.
    """
    domains: set[str] = set()
    combined = " ".join(file_paths).lower()

    for keyword, domain in DOMAIN_PATTERNS.items():
        if keyword in combined:
            domains.add(domain)

    return sorted(domains)


def extract_languages(file_paths: list[str]) -> list[str]:
    """Extract programming languages from file extensions.

    Args:
        file_paths: List of file paths.

    Returns:
        Sorted list of unique language strings.
    """
    languages: set[str] = set()
    for f in file_paths:
        suffix = Path(f).suffix.lower()
        if suffix in EXTENSION_TO_LANGUAGE:
            languages.add(EXTENSION_TO_LANGUAGE[suffix])
    return sorted(languages)


def extract_layers(file_paths: list[str]) -> list[str]:
    """Detect frontend/backend layers from file paths.

    Args:
        file_paths: List of file paths.

    Returns:
        List of layer strings (e.g., ``["backend", "frontend"]``).
    """
    layers: set[str] = set()

    for f in file_paths:
        f_lower = f.lower().replace("\\", "/")

        if any(p in f_lower for p in FRONTEND_PATTERNS):
            layers.add("frontend")
        if any(p in f_lower for p in BACKEND_PATTERNS) or (
            f_lower.endswith(".py")
            and not any(
                p in f_lower for p in ("/components/", "/pages/", "/views/", "/hooks/", "/styles/")
            )
        ):
            layers.add("backend")

    return sorted(layers)


def classify_session_pattern(
    turns: list[RawTurn],
    files_edited: list[str],
    user_edit_count: int,
    edit_count: int,
    task_raw: str = "",
) -> str:
    """Classify the session pattern based on tool calls and edit signals.

    Args:
        turns: Conversation turns (tool calls are read from ``is_tool_call``).
        files_edited: List of edited file paths.
        user_edit_count: Number of user edits.
        edit_count: Number of agent edits.
        task_raw: Raw task description for keyword heuristics.

    Returns:
        One of: ``debugging_session``, ``exploration_session``,
        ``refactoring_session``, ``configuration_session``,
        ``standard_implementation``.
    """
    # Extract tool names from explicit tool-call turns
    tool_names: list[str] = []
    for turn in turns:
        if turn.is_tool_call and turn.tool_name:
            tool_names.append(turn.tool_name.lower())

    read_search_tools = {"read_file", "search_files", "search", "list_files", "list"}
    write_edit_tools = {
        "write_to_file", "write", "replace_in_file", "replace",
        "edit", "insert_code_block", "insert",
    }
    replace_tools = {"replace_in_file", "replace"}

    read_search = sum(1 for t in tool_names if t in read_search_tools)
    write_edit = sum(1 for t in tool_names if t in write_edit_tools)
    replace_count = sum(1 for t in tool_names if t in replace_tools)

    # --- Configuration session ------------------------------------------------
    if files_edited:
        has_config = any(Path(f).suffix.lower() in CONFIG_EXTENSIONS for f in files_edited)
        has_code = any(Path(f).suffix.lower() in CODE_EXTENSIONS for f in files_edited)
        if has_config and not has_code:
            return "configuration_session"

    # --- Refactoring session --------------------------------------------------
    if replace_count >= 5 or edit_count >= 5 or len(files_edited) > 3:
        return "refactoring_session"

    # --- Exploration session --------------------------------------------------
    if (read_search > 0 or replace_count > 0) and write_edit == 0 and edit_count < 3:
        return "exploration_session"

    # --- Debugging session ----------------------------------------------------
    task_lower = task_raw.lower()
    error_keywords = {
        "error", "bug", "fix", "crash", "broken", "issue", "debug",
        "exception", "fail", "traceback", "wrong", "panic",
    }
    has_error_keywords = any(kw in task_lower for kw in error_keywords)

    high_read_ratio = (
        read_search > 0
        and (write_edit == 0 or read_search / write_edit > 3)
    )
    if high_read_ratio or has_error_keywords:
        return "debugging_session"

    return "standard_implementation"


def extract_reasoning(turns: list[RawTurn]) -> list[str]:
    """Extract reasoning content with deduplication.

    Filters assistant turns that are not tool calls, with content
    longer than 30 characters.  Deduplicates by the first 100 chars.

    Args:
        turns: List of RawTurn objects.

    Returns:
        Deduplicated list of reasoning strings.
    """
    reasoning: list[str] = []
    seen: set[str] = set()

    for turn in turns:
        if turn.role != "assistant" or turn.is_tool_call:
            continue
        content = turn.content.strip()
        if not content or len(content) <= 30:
            continue
        key = content[:100]
        if key not in seen:
            seen.add(key)
            reasoning.append(content)

    return reasoning


class SessionParser:
    """Converts RawSessionData from any adapter into a SessionDocument.

    The parser is completely agent-agnostic — it works with any
    RawSessionData regardless of which adapter produced it.
    """

    def parse_session(self, raw: RawSessionData) -> SessionDocument | None:
        """Parse RawSessionData into a normalized SessionDocument.

        Args:
            raw: RawSessionData from any adapter.

        Returns:
            A populated SessionDocument, or ``None`` if *raw* is ``None``.
        """
        if raw is None:
            return None

        # Combine file signals for extraction (deduplicate while preserving order)
        all_files = list(
            dict.fromkeys(
                raw.files_edited
                + raw.files_read
                + raw.files_mentioned
                + raw.files_user_edited
            )
        )

        project_name = derive_project_name(raw.workspace_dir, all_files)
        domains = extract_domains(all_files)
        languages = extract_languages(all_files)
        layers = extract_layers(all_files)
        session_pattern = classify_session_pattern(
            raw.turns,
            raw.files_edited,
            raw.user_edit_count,
            raw.edit_count,
            raw.task_raw,
        )
        reasoning_docs = extract_reasoning(raw.turns)

        return SessionDocument(
            session_id=raw.session_id,
            agent=raw.agent_id,
            project_name=project_name,
            project_root=raw.workspace_dir,
            session_start=raw.session_start,
            session_end=raw.session_end,
            duration_minutes=raw.duration_minutes,
            model_used=raw.model_used,
            files_edited=raw.files_edited,
            files_read=raw.files_read,
            files_mentioned=raw.files_mentioned,
            edit_count=raw.edit_count,
            user_edit_count=raw.user_edit_count,
            final_files=raw.final_files,
            domains=domains,
            languages=languages,
            layers=layers,
            session_pattern=session_pattern,
            task_raw=raw.task_raw,
            reasoning_docs=reasoning_docs,
            summary_doc="",
            propositions=[],
            quality_tag=QualityTag.UNKNOWN,
            tech_tags=[],
            parent_id=raw.parent_id,
            previous_session_id=raw.previous_session_id,
            indexed_at=0,
            schema_version=4,
        )
