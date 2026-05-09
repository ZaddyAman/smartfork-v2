"""Kilo Code session adapter for SmartFork v2."""

import json
import os
import platform
import re
from pathlib import Path
from typing import Any

from loguru import logger

from smartfork.adapters.base import SessionAdapter
from smartfork.adapters.registry import register
from smartfork.models.session import RawSessionData, RawTurn

# Tool call tags to detect
TOOL_CALL_TAGS = [
    "<read_file>",
    "<write_to_file>",
    "<search_files>",
    "<list_files>",
    "<execute_command>",
    "<ask_followup_question>",
    "<attempt_completion>",
    "<replace_in_file>",
    "<insert_code_block>",
    "<browser_action>",
    "<use_mcp_tool>",
    "<access_mcp_resource>",
    "<switch_mode>",
    "<update_todo_list>",
    "<new_task>",
]

# Content cleaning patterns
CLEANUP_PATTERNS = [
    re.compile(r"<file_content>.*?</file_content>", re.DOTALL),
    re.compile(r"<environment_details>.*?</environment_details>", re.DOTALL),
    re.compile(r"<terminal_output>.*?</terminal_output>", re.DOTALL),
    re.compile(r"<attached_files>.*?</attached_files>", re.DOTALL),
    re.compile(r"```.*?```", re.DOTALL),
    re.compile(r"<thinking>.*?</thinking>", re.DOTALL),
]

# IDE name -> platform-specific paths
IDE_PATHS: dict[str, dict[str, str]] = {
    "Cursor": {
        "win32": "%APPDATA%/Cursor/User/globalStorage/kilocode.kilo-code/tasks",
        "darwin": (
            "~/Library/Application Support/Cursor/User/globalStorage/"
            "kilocode.kilo-code/tasks"
        ),
        "linux": "~/.config/Cursor/User/globalStorage/kilocode.kilo-code/tasks",
    },
    "VS Code": {
        "win32": "%APPDATA%/Code/User/globalStorage/kilocode.kilo-code/tasks",
        "darwin": (
            "~/Library/Application Support/Code/User/globalStorage/"
            "kilocode.kilo-code/tasks"
        ),
        "linux": "~/.config/Code/User/globalStorage/kilocode.kilo-code/tasks",
    },
    "AntiGravity": {
        "win32": "%APPDATA%/AntiGravity/User/globalStorage/kilocode.kilo-code/tasks",
        "darwin": (
            "~/Library/Application Support/AntiGravity/User/globalStorage/"
            "kilocode.kilo-code/tasks"
        ),
        "linux": "~/.config/AntiGravity/User/globalStorage/kilocode.kilo-code/tasks",
    },
}


def _extract_text(content: Any) -> str:
    """Extract text from multi-format content field.

    Handles: plain string, OpenAI array-of-parts, and nested dict format.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text", "")
                if isinstance(text, dict):
                    text = text.get("value", "")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    if isinstance(content, dict):
        text = content.get("text", "")
        if isinstance(text, dict):
            text = text.get("value", "")
        if isinstance(text, str):
            return text
    return str(content)


def _clean_content(text: str) -> str:
    """Remove tool outputs, code blocks, and environment data from text."""
    for pattern in CLEANUP_PATTERNS:
        text = pattern.sub("", text)
    return text.strip()


def _is_tool_call(text: str) -> bool:
    """Check if text contains tool call tags."""
    return any(tag in text for tag in TOOL_CALL_TAGS)


def _extract_tool_name(text: str) -> str | None:
    """Extract the tool name from a tool call text."""
    for tag in TOOL_CALL_TAGS:
        if tag in text:
            return tag.strip("<>")
    return None


def _resolve_ide_path(ide: str) -> Path | None:
    """Resolve IDE-specific session path for the current platform."""
    ide_data = IDE_PATHS.get(ide)
    if not ide_data:
        return None

    sys_platform = platform.system().lower()
    if sys_platform == "windows":
        sys_platform = "win32"

    path_template = ide_data.get(sys_platform)
    if not path_template:
        return None

    # Expand %APPDATA% on Windows
    if "%APPDATA%" in path_template:
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            path_template = path_template.replace("%APPDATA%", appdata)

    return Path(path_template).expanduser()


@register
class KiloCodeAdapter(SessionAdapter):
    """Adapter for Kilo Code session format (3-file JSON directory)."""

    agent_id = "kilocode"
    display_name = "Kilo Code"
    session_type = "dir"

    def is_valid_session(self, session_path: Path) -> bool:
        """Check if path contains a valid Kilo Code session.

        A valid session has api_conversation_history.json in the directory.
        """
        if not session_path.is_dir():
            return False
        return (session_path / "api_conversation_history.json").is_file()

    def get_session_files(self, session_path: Path) -> list[str]:
        """Return the expected session file names."""
        return [
            "task_metadata.json",
            "api_conversation_history.json",
            "ui_messages.json",
        ]

    def parse_raw(self, session_path: Path) -> RawSessionData | None:
        """Parse a Kilo Code session directory into RawSessionData.

        Args:
            session_path: Path to the session directory.

        Returns:
            RawSessionData if parsing succeeds, None otherwise.
        """
        if not self.is_valid_session(session_path):
            return None

        try:
            # File paths
            metadata_path = session_path / "task_metadata.json"
            history_path = session_path / "api_conversation_history.json"
            ui_path = session_path / "ui_messages.json"

            # --- Parse task_metadata.json ---
            file_signals: dict[str, list[str]] = {
                "files_edited": [],
                "files_read": [],
                "files_mentioned": [],
                "files_user_edited": [],
                "final_files": [],
            }
            if metadata_path.is_file():
                with open(metadata_path, encoding="utf-8") as f:
                    metadata = json.load(f)
                for key in file_signals:
                    val = metadata.get(key, [])
                    if isinstance(val, list):
                        file_signals[key] = [str(v) for v in val]
                    elif isinstance(val, str):
                        file_signals[key] = [val]

            # --- Parse api_conversation_history.json ---
            turns: list[RawTurn] = []
            workspace_dir = ""
            task_raw = ""
            model_used: str | None = None
            session_start = 0
            session_end = 0

            if history_path.is_file():
                with open(history_path, encoding="utf-8") as f:
                    history = json.load(f)

                # history may be a dict with messages or a list
                messages: list[Any] = []
                if isinstance(history, dict):
                    raw_messages = history.get("messages", history.get("history", []))
                    if isinstance(raw_messages, list):
                        messages = raw_messages
                    workspace_dir = history.get("workspace_dir", history.get("cwd")) or ""
                    task_raw = history.get("task", history.get("task_raw")) or ""
                    model_used = history.get("model", history.get("model_used"))
                elif isinstance(history, list):
                    messages = history

                for msg in messages:
                    if not isinstance(msg, dict):
                        continue
                    role = msg.get("role", "unknown")
                    content_raw = msg.get("content", "")
                    content = _extract_text(content_raw)

                    ts = msg.get("timestamp", 0)
                    ts = int(ts) if isinstance(ts, (int, float)) else 0

                    # Track session boundaries
                    if ts > 0:
                        if session_start == 0 or ts < session_start:
                            session_start = ts
                        if ts > session_end:
                            session_end = ts

                    # Filter tool calls from assistant turns
                    is_tool = False
                    tool_name = None
                    if _is_tool_call(content):
                        is_tool = True
                        tool_name = _extract_tool_name(content)
                    content = _clean_content(content)

                    if content.strip():
                        turn = RawTurn(
                            role=role,
                            content=content,
                            timestamp=ts,
                            is_tool_call=is_tool,
                            tool_name=tool_name,
                        )
                        turns.append(turn)

            # --- Parse ui_messages.json for reasoning ---
            if ui_path.is_file():
                with open(ui_path, encoding="utf-8") as f:
                    ui_messages = json.load(f)

                if isinstance(ui_messages, list):
                    for msg in ui_messages:
                        if not isinstance(msg, dict):
                            continue
                        # Look for say:"reasoning" blocks
                        say = msg.get("say", "")
                        if isinstance(say, str) and "reasoning" in say.lower():
                            ts = msg.get("ts", 0)
                            if isinstance(ts, (int, float)):
                                ts = int(ts)
                            text = msg.get("text", "")
                            content = _clean_content(text)
                            if content.strip():
                                turn = RawTurn(
                                    role="assistant",
                                    content=content,
                                    timestamp=ts,
                                    is_tool_call=False,
                                    tool_name=None,
                                )
                                turns.append(turn)

            # --- Construct session_id ---
            session_id = session_path.name

            return RawSessionData(
                session_id=session_id,
                agent_id=self.agent_id,
                session_path=session_path,
                turns=turns,
                files_edited=file_signals["files_edited"],
                files_read=file_signals["files_read"],
                files_mentioned=file_signals["files_mentioned"],
                files_user_edited=file_signals["files_user_edited"],
                final_files=file_signals["final_files"],
                workspace_dir=workspace_dir,
                task_raw=task_raw,
                model_used=model_used,
                session_start=session_start,
                session_end=session_end,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Kilo Code session at {session_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing Kilo Code session at {session_path}: {e}")
            return None

    def get_ide_choices(self) -> list[str]:
        """Return supported IDE names for auto-detection."""
        return ["Cursor", "VS Code", "AntiGravity"]

    def get_default_sessions_paths(self) -> list[Path]:
        """Return default search paths for Kilo Code sessions."""
        paths: list[Path] = []
        for ide in self.get_ide_choices():
            ide_path = self.get_default_path_for_ide(ide)
            if ide_path and ide_path.exists():
                paths.append(ide_path)
        # Also check legacy path from config
        try:
            from smartfork.config import get_config
            cfg = get_config()
            legacy = cfg.kilo_code_tasks_path
            if legacy != Path(".") and legacy.exists():
                paths.append(legacy)
        except Exception:
            pass
        return paths

    def get_default_path_for_ide(self, ide: str) -> Path | None:
        """Get the default Kilo Code sessions path for a specific IDE."""
        return _resolve_ide_path(ide)
