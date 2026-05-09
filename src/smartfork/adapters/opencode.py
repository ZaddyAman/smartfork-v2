"""OpenCode session adapter for SmartFork v2."""

import json
import sqlite3
from pathlib import Path
from typing import Any

from loguru import logger

from smartfork.adapters.base import SessionAdapter
from smartfork.adapters.registry import register
from smartfork.models.session import RawSessionData, RawTurn


def get_default_opencode_db_path() -> Path:
    """Return the default OpenCode database path."""
    return Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def get_all_sessions_from_db(db_path: Path | None = None) -> list[dict[str, Any]]:
    """Query the OpenCode SQLite database for all sessions.

    Args:
        db_path: Path to the opencode.db file. Uses default if None.

    Returns:
        List of session dicts with session_id and other metadata.
    """
    if db_path is None:
        db_path = get_default_opencode_db_path()

    if not db_path.exists():
        logger.warning(f"OpenCode database not found at {db_path}")
        return []

    sessions: list[dict[str, Any]] = []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT id, title, created_at, model FROM session ORDER BY created_at DESC"
        )
        for row in cursor.fetchall():
            sessions.append({
                "session_id": str(row["id"]),
                "title": row["title"] or "",
                "created_at": row["created_at"] or 0,
                "model": row["model"] or "",
            })
        conn.close()
    except sqlite3.Error as e:
        logger.error(f"Failed to query OpenCode database: {e}")

    return sessions


@register
class OpenCodeAdapter(SessionAdapter):
    """Adapter for OpenCode session format (SQLite database)."""

    agent_id = "opencode"
    display_name = "OpenCode"
    session_type = "sqlite"

    def is_valid_session(self, session_path: Path) -> bool:
        """Check if path is a valid OpenCode SQLite database."""
        if not session_path.is_file():
            return False
        if session_path.suffix.lower() != ".db":
            return False
        # Quick check: does it have a session table?
        try:
            conn = sqlite3.connect(str(session_path))
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='session'"
            )
            result = cursor.fetchone()
            conn.close()
            return result is not None
        except sqlite3.Error:
            return False

    def get_session_files(self, session_path: Path) -> list[str]:
        """Return the database file path."""
        return [str(session_path)]

    def parse_raw(self, session_path: Path) -> RawSessionData | None:
        """Parse an OpenCode SQLite database into RawSessionData.

        Queries session, message, and part tables to extract conversation
        turns and metadata.

        Args:
            session_path: Path to the .db file.

        Returns:
            RawSessionData if parsing succeeds, None otherwise.
        """
        if not self.is_valid_session(session_path):
            return None

        try:
            conn = sqlite3.connect(str(session_path))
            conn.row_factory = sqlite3.Row

            # Get the most recent session
            cursor = conn.execute(
                "SELECT id, title, created_at, model, workspace_dir "
                "FROM session ORDER BY created_at DESC LIMIT 1"
            )
            session_row = cursor.fetchone()
            if not session_row:
                conn.close()
                return None

            session_id = str(session_row["id"])
            workspace_dir = session_row["workspace_dir"] or ""
            model_used = session_row["model"] or None
            session_start = int(session_row["created_at"]) if session_row["created_at"] else 0

            # Get messages for this session
            cursor = conn.execute(
                "SELECT id, role, created_at FROM message WHERE session_id = ? ORDER BY created_at",
                (session_row["id"],)
            )
            messages = cursor.fetchall()

            turns: list[RawTurn] = []
            files_read: list[str] = []
            files_edited: list[str] = []
            session_end = session_start

            for msg in messages:
                msg_id = msg["id"]
                role = msg["role"] or "unknown"
                msg_ts = int(msg["created_at"]) if msg["created_at"] else 0
                if msg_ts > session_end:
                    session_end = msg_ts

                # Get parts for this message
                cursor = conn.execute(
                    "SELECT type, content, metadata FROM part WHERE message_id = ? ORDER BY id",
                    (msg_id,)
                )
                parts = cursor.fetchall()

                text_parts: list[str] = []
                for part in parts:
                    part_type = part["type"] or ""
                    content = part["content"] or ""

                    if part_type in ("text", "user_text"):
                        text_parts.append(content)
                    elif part_type == "reasoning":
                        text_parts.append(f"[Reasoning] {content}")
                    elif part_type in ("tool_call", "tool_use"):
                        # Extract file paths from tool metadata
                        meta = part["metadata"] or ""
                        if meta:
                            try:
                                meta_dict = json.loads(meta)
                                file_path = meta_dict.get("file_path", meta_dict.get("path", ""))
                                if file_path and part_type == "tool_use":
                                    files_read.append(file_path)
                            except json.JSONDecodeError:
                                pass
                        text_parts.append(f"[Tool: {content[:100]}]")

                if text_parts:
                    turn = RawTurn(
                        role=role,
                        content="\n".join(text_parts),
                        timestamp=msg_ts,
                        is_tool_call=False,
                        tool_name=None,
                    )
                    turns.append(turn)

            conn.close()

            # Try to derive task from first user message
            task_raw = ""
            for turn in turns:
                if turn.role == "user":
                    task_raw = turn.content[:200]
                    break

            return RawSessionData(
                session_id=session_id,
                agent_id=self.agent_id,
                session_path=session_path,
                turns=turns,
                files_edited=files_edited,
                files_read=files_read,
                files_mentioned=[],
                files_user_edited=[],
                final_files=[],
                workspace_dir=workspace_dir,
                task_raw=task_raw,
                model_used=model_used,
                session_start=session_start,
                session_end=session_end,
            )

        except sqlite3.Error as e:
            logger.error(f"SQLite error parsing OpenCode session {session_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing OpenCode session {session_path}: {e}")
            return None

    def get_default_sessions_paths(self) -> list[Path]:
        """Return the default OpenCode database path."""
        db_path = get_default_opencode_db_path()
        if db_path.exists():
            return [db_path]
        return []
