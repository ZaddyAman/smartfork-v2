"""Claude Code session adapter for SmartFork v2."""

import json
import os
from pathlib import Path

from loguru import logger

from smartfork.adapters.base import SessionAdapter
from smartfork.adapters.registry import register
from smartfork.models.session import RawSessionData, RawTurn

# File-signal tool names
READ_TOOLS = {"read_file", "view_file", "read", "cat", "open_file"}
WRITE_TOOLS = {"write_file", "edit_file", "replace_in_file", "write", "create_file"}


def _extract_text_from_content(content: object) -> str:
    """Extract text from Claude's content (string or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text":
                    parts.append(str(block.get("text", "")))
                elif block_type == "tool_use":
                    # Tool use block — extract tool name and input summary
                    name = block.get("name", "")
                    parts.append(f"[tool_use: {name}]")
                elif block_type == "tool_result":
                    parts.append("[tool_result]")
        return "\n".join(parts)
    return str(content)


def _extract_file_signals_from_tools(messages: list[dict[str, object]]) -> dict[str, list[str]]:
    """Scan all messages for tool_use blocks and extract file signals."""
    files_read: list[str] = []
    files_edited: list[str] = []

    for msg in messages:
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            inp = block.get("input", {})
            if not isinstance(inp, dict):
                continue

            # Extract file paths from common input keys
            file_path = inp.get("file_path", inp.get("path", inp.get("file", "")))
            if not file_path:
                file_path = inp.get("old_file_path", "")
            if file_path and isinstance(file_path, str):
                if name in READ_TOOLS:
                    files_read.append(file_path)
                elif name in WRITE_TOOLS:
                    files_edited.append(file_path)

    return {
        "files_read": files_read,
        "files_edited": files_edited,
    }


def _get_claude_projects_dir() -> Path:
    """Get the Claude Code projects directory."""
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR", "")
    if config_dir:
        return Path(config_dir).expanduser() / "projects"
    return Path.home() / ".claude" / "projects"


@register
class ClaudeCodeAdapter(SessionAdapter):
    """Adapter for Claude Code session format (.jsonl files)."""

    agent_id = "claudecode"
    display_name = "Claude Code"
    session_type = "project"

    def is_valid_session(self, session_path: Path) -> bool:
        """Check if path is a valid Claude Code .jsonl session file."""
        return session_path.is_file() and session_path.suffix == ".jsonl"

    def get_session_files(self, session_path: Path) -> list[str]:
        """Return the session file path."""
        return [str(session_path)]

    def parse_raw(self, session_path: Path) -> RawSessionData | None:
        """Parse a Claude Code .jsonl session file into RawSessionData.

        Args:
            session_path: Path to the .jsonl session file.

        Returns:
            RawSessionData if parsing succeeds, None otherwise.
        """
        if not self.is_valid_session(session_path):
            return None

        try:
            turns: list[RawTurn] = []
            messages_raw: list[dict[str, object]] = []
            workspace_dir = ""
            model_used = "claude-3-5-sonnet"  # default
            session_start = 0
            session_end = 0

            with open(session_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning(f"Skipping invalid JSON line in {session_path}")
                        continue

                    messages_raw.append(record)

                    role = record.get("role", "unknown")
                    content = record.get("content", "")

                    # Extract text from content (handles string and list-of-blocks)
                    text = _extract_text_from_content(content)

                    ts = record.get("timestamp", 0)
                    ts = int(ts) if isinstance(ts, (int, float)) else 0

                    if ts > 0:
                        if session_start == 0 or ts < session_start:
                            session_start = ts
                        if ts > session_end:
                            session_end = ts

                    # Detect model
                    if not model_used or model_used == "claude-3-5-sonnet":
                        detected = record.get("model", "")
                        if detected:
                            model_used = detected

                    # Detect workspace
                    if not workspace_dir:
                        cwd = record.get("cwd", record.get("working_dir", ""))
                        if cwd:
                            workspace_dir = cwd

                    if text.strip():
                        turn = RawTurn(
                            role=role,
                            content=text,
                            timestamp=ts,
                            is_tool_call=False,
                            tool_name=None,
                        )
                        turns.append(turn)

            # Extract file signals from tool_use blocks
            file_signals = _extract_file_signals_from_tools(messages_raw)

            session_id = session_path.stem  # filename without .jsonl

            if not turns:
                return None

            # Extract task from first user message
            task_raw = ""
            for turn in turns:
                if turn.role in ("user", "human"):
                    task_raw = turn.content[:500].strip()
                    break

            return RawSessionData(
                session_id=session_id,
                agent_id=self.agent_id,
                session_path=session_path,
                turns=turns,
                files_edited=file_signals["files_edited"],
                files_read=file_signals["files_read"],
                files_mentioned=[],
                files_user_edited=[],
                final_files=[],
                workspace_dir=workspace_dir,
                task_raw=task_raw,
                model_used=model_used,
                session_start=session_start,
                session_end=session_end,
            )

        except Exception as e:
            logger.error(f"Failed to parse Claude Code session {session_path}: {e}")
            return None

    def get_default_sessions_paths(self) -> list[Path]:
        """Return default Claude Code projects directory."""
        projects_dir = _get_claude_projects_dir()
        if projects_dir.exists():
            return [projects_dir]
        return []

    def get_ide_choices(self) -> list[str]:
        """Claude Code is IDE-agnostic."""
        return []


def scan_claude_sessions(base_dir: Path | None = None) -> list[Path]:
    """Scan the Claude Code projects directory for .jsonl session files.

    Args:
        base_dir: Base directory to scan. Uses default if None.

    Returns:
        List of paths to .jsonl session files.
    """
    if base_dir is None:
        base_dir = _get_claude_projects_dir()

    if not base_dir.exists():
        return []

    return list(base_dir.rglob("*.jsonl"))
