"""Session scanner — discovers sessions via adapters."""

from collections.abc import Callable
from pathlib import Path

from loguru import logger

from smartfork.adapters.registry import get_adapter, list_agent_ids
from smartfork.models.progress import ProgressEvent


class SessionScanner:
    """Scans the filesystem for coding sessions using registered adapters."""

    def scan(
        self,
        agent_ids: list[str] | None = None,
        progress_callback: Callable[[ProgressEvent], None] | None = None,
    ) -> list[tuple[str, Path]]:
        """Scan for sessions across all (or specified) adapters.

        Args:
            agent_ids: List of agent IDs to scan. None means all registered.
            progress_callback: Optional callback for live per-agent scan progress.

        Returns:
            List of (agent_id, session_path) tuples.
        """
        if agent_ids is None:
            agent_ids = list_agent_ids()

        sessions: list[tuple[str, Path]] = []

        # Signal all pending
        for agent_id in agent_ids:
            adapter = get_adapter(agent_id)
            if adapter is None:
                logger.warning(f"No adapter found for '{agent_id}', skipping.")
                continue
            if progress_callback:
                search_paths = adapter.get_default_sessions_paths()
                progress_callback(ProgressEvent(
                    phase="scanning",
                    agent_id=agent_id,
                    scan_status="pending",
                    scan_count=0,
                    scan_path=str(search_paths[0]) if search_paths else "",
                ))

        for agent_id in agent_ids:
            adapter = get_adapter(agent_id)
            if adapter is None:
                logger.warning(f"No adapter found for '{agent_id}', skipping.")
                continue

            search_paths = adapter.get_default_sessions_paths()
            if not search_paths:
                logger.debug(f"No default paths for adapter '{agent_id}'.")
                if progress_callback:
                    progress_callback(ProgressEvent(
                        phase="scanning",
                        agent_id=agent_id,
                        scan_status="complete",
                        scan_count=0,
                    ))
                continue

            # Signal scanning
            if progress_callback:
                progress_callback(ProgressEvent(
                    phase="scanning",
                    agent_id=agent_id,
                    scan_status="running",
                    scan_count=0,
                    scan_path=str(search_paths[0]) if search_paths else "",
                ))

            agent_sessions: list[tuple[str, Path]] = []

            for search_path in search_paths:
                if not search_path.exists():
                    continue

                try:
                    if adapter.session_type == "sqlite" and search_path.is_file():
                        if adapter.is_valid_session(search_path):
                            agent_sessions.append((agent_id, search_path))
                    elif adapter.session_type == "file":
                        if search_path.is_file() and adapter.is_valid_session(search_path):
                            agent_sessions.append((agent_id, search_path))
                    elif adapter.session_type in ("dir", "project"):
                        if not search_path.is_dir():
                            continue
                        if adapter.session_type == "project":
                            for candidate in search_path.rglob("*"):
                                if adapter.is_valid_session(candidate):
                                    agent_sessions.append((agent_id, candidate))
                        else:
                            for candidate in search_path.iterdir():
                                if candidate.is_dir() and adapter.is_valid_session(candidate):
                                    agent_sessions.append((agent_id, candidate))
                except PermissionError:
                    logger.warning(f"Permission denied scanning {search_path}")
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"Error scanning {search_path}: {exc}")

            sessions.extend(agent_sessions)

            if progress_callback:
                progress_callback(ProgressEvent(
                    phase="scanning",
                    agent_id=agent_id,
                    scan_status="complete",
                    scan_count=len(agent_sessions),
                ))

        logger.info(
            f"Scanner found {len(sessions)} sessions across "
            f"{len({a for a, _ in sessions})} agents."
        )
        return sessions


class TranscriptWatcher:
    """Watches for new session files and triggers indexing.

    Note: This is a stub. Full watchdog integration will be implemented
    when the watchdog package is available at runtime.
    """

    def __init__(self, callback: object | None = None) -> None:
        self.callback = callback
        self._running = False

    def start(self, watch_paths: list[Path]) -> None:
        """Start watching for new session files."""
        logger.info(f"Watcher started on {len(watch_paths)} paths")
        self._running = True

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        logger.info("Watcher stopped")

    @property
    def is_running(self) -> bool:
        return self._running
