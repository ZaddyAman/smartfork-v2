"""OpenCode session adapter for SmartFork v2 — SQLite-based."""

import json
import sqlite3
from pathlib import Path

from loguru import logger

from smartfork.adapters.base import SessionAdapter
from smartfork.adapters.registry import register
from smartfork.models.session import RawSessionData, RawTurn


def get_default_opencode_db_path() -> Path:
    """Return the default OpenCode database path."""
    return Path.home() / ".local" / "share" / "opencode" / "opencode.db"


@register
class OpenCodeAdapter(SessionAdapter):
    """Adapter for OpenCode session format (SQLite database).

    OpenCode stores all sessions in a single SQLite database with three
    key tables: session, message, part. Messages and parts store their
    content as JSON blobs in a ``data`` column.
    """

    agent_id = "opencode"
    display_name = "OpenCode"
    session_type = "sqlite"

    def is_valid_session(self, session_path: Path) -> bool:
        """Check if path is a valid OpenCode SQLite database."""
        if not session_path.is_file():
            return False
        if session_path.suffix.lower() != ".db":
            return False
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

    def get_default_sessions_paths(self) -> list[Path]:
        """Return the default OpenCode database path."""
        db_path = get_default_opencode_db_path()
        if db_path.exists():
            return [db_path]
        return []

    def get_all_sessions_from_db(
        self, db_path: Path | None = None
    ) -> list[RawSessionData]:
        """Return all sessions from the OpenCode SQLite database.

        Queries the session, message, and part tables. Messages and parts
        store their data as JSON blobs.

        Args:
            db_path: Path to the opencode.db file. Uses default if None.

        Returns:
            List of RawSessionData, one per session row.
        """
        if db_path is None:
            db_path = get_default_opencode_db_path()

        if not db_path.exists():
            logger.warning(f"OpenCode database not found at {db_path}")
            return []

        sessions: list[RawSessionData] = []
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            cur.execute(
                """SELECT id, project_id, parent_id, slug, directory, title,
                          version, time_created, time_updated,
                          agent, model
                   FROM session
                   WHERE directory IS NOT NULL AND directory != ''
                   ORDER BY time_updated DESC"""
            )

            for row in cur.fetchall():
                session_id = row["id"]
                session_dir = row["directory"] or ""
                title = row["title"] or ""
                time_created = row["time_created"] or 0
                time_updated = row["time_updated"] or 0
                model_used = row["model"] or "opencode"
                parent_id = row["parent_id"] or None

                turns: list[RawTurn] = []
                files_edited: list[str] = []
                files_read: list[str] = []
                task_raw = title[:500] if title else ""

                cur.execute(
                    """SELECT id, time_created, data FROM message
                       WHERE session_id = ? ORDER BY time_created""",
                    (session_id,),
                )
                messages = cur.fetchall()

                for msg_row in messages:
                    msg_id = msg_row["id"]
                    ts = msg_row["time_created"] or 0

                    try:
                        msg_data = json.loads(msg_row["data"])
                    except (json.JSONDecodeError, TypeError):
                        continue

                    role = msg_data.get("role", "")

                    msg_model = msg_data.get("model", {})
                    if isinstance(msg_model, dict):
                        model_id = msg_model.get("modelID", "")
                        if model_id:
                            model_used = model_id

                    if role == "user":
                        content = _get_user_content(cur, msg_id, msg_data)
                        if not task_raw and content:
                            task_raw = content[:500]
                        if content:
                            turns.append(
                                RawTurn(
                                    role="user",
                                    content=content,
                                    timestamp=ts,
                                )
                            )

                    elif role == "assistant":
                        assistant_turns, assistant_files = _get_assistant_content(
                            cur, msg_id, ts
                        )
                        turns.extend(assistant_turns)
                        files_read.extend(assistant_files)

                if turns:
                    sessions.append(
                        RawSessionData(
                            session_id=session_id,
                            agent_id=self.agent_id,
                            session_path=Path(session_dir),
                            turns=turns,
                            files_edited=list(set(files_edited))[:20],
                            files_read=list(set(files_read))[:20],
                            files_mentioned=[],
                            files_user_edited=[],
                            final_files=[],
                            workspace_dir=session_dir,
                            task_raw=task_raw,
                            model_used=model_used,
                            session_start=time_created,
                            session_end=time_updated,
                            edit_count=len(set(files_edited)),
                            user_edit_count=0,
                            parent_id=parent_id,
                        )
                    )

            conn.close()
            logger.info(
                f"[{self.agent_id}] Found {len(sessions)} sessions from database"
            )

        except sqlite3.Error as e:
            logger.error(f"Failed to query OpenCode database: {e}")
        except Exception as e:
            logger.error(f"Unexpected error reading OpenCode sessions: {e}")

        return sessions

    def parse_raw(self, session_path: Path) -> RawSessionData | None:
        """Parse a single session from the OpenCode database.

        For SQLite-based adapters, this returns the first session from the
        database. Use ``get_all_sessions_from_db()`` for batch processing.

        Args:
            session_path: Path to the .db file.

        Returns:
            RawSessionData if parsing succeeds, None otherwise.
        """
        sessions = self.get_all_sessions_from_db(session_path)
        if sessions:
            return sessions[0]
        return None


def _get_user_content(cur, msg_id: str, msg_data: dict) -> str:
    """Get user message content from part rows with type='text'."""
    cur.execute(
        """SELECT data FROM part
           WHERE message_id = ?
           ORDER BY time_created""",
        (msg_id,),
    )

    for row in cur.fetchall():
        try:
            part_data = json.loads(row["data"])
            if part_data.get("type") == "text":
                content = part_data.get("text", "")
                if content:
                    return content
        except (json.JSONDecodeError, TypeError):
            pass

    summary = msg_data.get("summary", {})
    if isinstance(summary, dict):
        diffs = summary.get("diffs", [])
        if diffs:
            return f"User task with {len(diffs)} file changes"

    return ""


def _get_assistant_content(
    cur, msg_id: str, ts: int
) -> tuple[list[RawTurn], list[str]]:
    """Get assistant message content (reasoning + tools) from part rows."""
    turns: list[RawTurn] = []
    files_read: list[str] = []

    cur.execute(
        """SELECT data FROM part
           WHERE message_id = ?
           ORDER BY time_created""",
        (msg_id,),
    )

    for row in cur.fetchall():
        try:
            part_data = json.loads(row["data"])
            part_type = part_data.get("type", "")

            if part_type == "reasoning":
                reasoning_text = part_data.get("text", "")
                if reasoning_text and len(reasoning_text) > 20:
                    turns.append(
                        RawTurn(
                            role="assistant",
                            content=reasoning_text,
                            timestamp=ts,
                        )
                    )

            elif part_type == "tool":
                tool_name = part_data.get("tool", "")
                tool_input = part_data.get("state", {}).get("input", {})

                if tool_name:
                    turns.append(
                        RawTurn(
                            role="assistant",
                            content="",
                            timestamp=ts,
                            is_tool_call=True,
                            tool_name=tool_name,
                        )
                    )

                    if isinstance(tool_input, dict):
                        for key in ("file_path", "path", "filePath", "filepath"):
                            fpath = tool_input.get(key)
                            if (
                                fpath
                                and isinstance(fpath, str)
                                and "." in fpath
                            ):
                                files_read.append(fpath)

        except (json.JSONDecodeError, TypeError, KeyError):
            continue

    return turns, files_read
