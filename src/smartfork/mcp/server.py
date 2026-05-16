"""MCP server for SmartFork v2 — Claude Code integration."""

from loguru import logger


class SmartForkMCPServer:
    """Model Context Protocol server for SmartFork v2.

    Exposes session intelligence tools to Claude Code and other
    MCP-compatible AI coding agents.
    """

    def __init__(self) -> None:
        self._running = False

    def start(self) -> None:
        """Start the MCP server on stdio transport."""
        self._running = True
        logger.info("MCP server started on stdio")

    def stop(self) -> None:
        """Stop the MCP server."""
        self._running = False
        logger.info("MCP server stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def detect_fork(self, query: str, n: int = 5) -> list[dict[str, object]]:
        """Find relevant sessions to fork from."""
        try:
            from smartfork.search.deterministic import DeterministicSearchEngine

            engine = DeterministicSearchEngine()
            results = engine.search(query, n_results=n)
            return [
                {
                    "session_id": r.session_id,
                    "title": r.title,
                    "match_score": r.match_score,
                    "excerpt": r.excerpt,
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"detect_fork failed: {e}")
            return []

    def fork_session(self, session_id: str, intent: str = "continue") -> str:
        """Generate fork context from a session."""
        try:
            from smartfork.fork.assembler import ForkAssembler

            assembler = ForkAssembler()
            report = assembler.assemble(session_id, user_query="")
            if report and report.handoff_content:
                return report.handoff_content
            return f"# Handoff: {session_id}\n\nNo context available."
        except Exception as e:
            logger.error(f"fork_session failed: {e}")
            return f"# Handoff: {session_id}\n\nError: {e}"

    def index_status(self) -> dict[str, object]:
        """Get indexing statistics."""
        try:
            from smartfork.config import get_config
            from smartfork.indexer.metadata_store import MetadataStore

            cfg = get_config()
            store = MetadataStore(cfg.sqlite_db_path)
            stats = store.get_stats()
            return {
                "total_sessions": stats.get("total", 0),
                "indexed_chunks": stats.get("chunks", 0),
                "by_project": stats.get("by_project", {}),
                "by_agent": stats.get("by_agent", {}),
                "by_quality": stats.get("by_quality", {}),
            }
        except Exception as e:
            logger.error(f"index_status failed: {e}")
            return {"total_sessions": 0, "error": str(e)}

    def search_sessions(self, query: str, top_k: int = 5) -> list[dict[str, object]]:
        """Search indexed sessions."""
        try:
            from smartfork.search.deterministic import DeterministicSearchEngine

            engine = DeterministicSearchEngine()
            results = engine.search(query, n_results=top_k)
            return [
                {
                    "session_id": r.session_id,
                    "title": r.title,
                    "match_score": r.match_score,
                    "excerpt": r.excerpt,
                    "project": r.project_name,
                    "quality": str(r.quality_tag) if hasattr(r, "quality_tag") and r.quality_tag else "unknown",
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"search_sessions failed: {e}")
            return []

    def get_session(self, session_id: str) -> dict[str, object] | None:
        """Get full session details."""
        try:
            from smartfork.config import get_config
            from smartfork.indexer.metadata_store import MetadataStore

            cfg = get_config()
            store = MetadataStore(cfg.sqlite_db_path)
            doc = store.get_session(session_id)
            if doc is None:
                return None
            return {
                "session_id": doc.get("session_id", ""),
                "title": doc.get("title", ""),
                "project": doc.get("project_name", ""),
                "agent": doc.get("agent", ""),
                "quality": doc.get("quality_tag", "unknown"),
                "task_raw": doc.get("task_raw", ""),
                "domains": doc.get("domains", []),
                "languages": doc.get("languages", []),
                "files_edited": doc.get("files_edited", []),
                "session_start": doc.get("session_start", 0),
                "session_end": doc.get("session_end", 0),
            }
        except Exception as e:
            logger.error(f"get_session failed: {e}")
            return None

    def list_projects(self) -> list[str]:
        """List all indexed projects."""
        try:
            from smartfork.config import get_config
            from smartfork.indexer.metadata_store import MetadataStore

            cfg = get_config()
            store = MetadataStore(cfg.sqlite_db_path)
            stats = store.get_stats()
            by_project = stats.get("by_project", {})
            return sorted(by_project.keys())
        except Exception as e:
            logger.error(f"list_projects failed: {e}")
            return []

    def config_get(self, key: str) -> str | None:
        """Read a configuration value."""
        try:
            from smartfork.config import get_config

            cfg = get_config()
            value = getattr(cfg, key, None)
            return str(value) if value is not None else None
        except Exception as e:
            logger.error(f"config_get failed: {e}")
            return None

    def vault_export(self, output_dir: str = "./smartfork_vault") -> str:
        """Export session data as an Obsidian vault."""
        try:
            from pathlib import Path

            from smartfork.vault.obsidian import ObsidianVaultGenerator

            generator = ObsidianVaultGenerator()
            generator.generate(Path(output_dir))
            return str(Path(output_dir).absolute())
        except Exception as e:
            logger.error(f"vault_export failed: {e}")
            return str(output_dir)
