"""SmartFork v2 CLI commands."""

from typing import Any

import typer

from smartfork.cli.theme import (
    PALETTES,
    VALID_THEMES,
    error,
    get_console,
    get_theme,
    header,
    info,
    inline_bar,
    kv_table,
    nl,
    quality_minibar,
    success,
    warn,
)

app = typer.Typer(
    name="smartfork",
    help="SmartFork v0.1.0 — session intelligence for AI coding agents",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = get_console()

# Global flags
verbose_opt = typer.Option(False, "--verbose", "-v", help="Enable verbose output")
lite_opt = typer.Option(False, "--lite", help="Run in lite mode (reduced resource usage)")


@app.callback()
def callback(
    verbose: bool = verbose_opt,
    lite: bool = lite_opt,
) -> None:
    """SmartFork v0.1.0 — session intelligence for AI coding agents."""
    from pathlib import Path

    from loguru import logger

    log_file = Path.home() / ".smartfork" / "smartfork.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger.remove()
    if verbose:
        logger.add(str(log_file), level="DEBUG", rotation="10 MB")
    else:
        logger.add(str(log_file), level="WARNING", rotation="10 MB")


# ──────────────────────────────────────────────────────────────────────
# Core commands
# ──────────────────────────────────────────────────────────────────────


@app.command(rich_help_panel="Core")
def index(
    full: bool = typer.Option(False, "--full", help="Full re-index (ignore incremental)"),
    agent: str | None = typer.Option(None, "--agent", "-a", help="Index only specific agent"),
) -> None:
    """Index all discovered coding sessions."""
    from smartfork.config import get_config
    from smartfork.indexer.indexer import FullIndexer
    from smartfork.indexer.metadata_store import MetadataStore

    cfg = get_config()
    store = MetadataStore(cfg.sqlite_db_path)

    # Try to set up embedder
    embedder = None
    try:
        from smartfork.indexer.embedder import EmbeddingPipeline
        from smartfork.providers import get_embedder

        emb = get_embedder(cfg.embedding_provider, cfg.embedding_model, cfg.embedding_dimensions)
        embedder = EmbeddingPipeline(embedder=emb, persist_dir=cfg.qdrant_db_path, batch_size=cfg.batch_size)
    except Exception as e:
        error(f"Embedder not available: {e}")
        info("Search requires embeddings to function. Please fix the issue above and try again.")
        raise typer.Exit(1)

    # Try to set up LLM for intelligence
    intelligence = None
    try:
        from smartfork.indexer.intelligence import IndexIntelligence
        from smartfork.providers import get_llm

        llm = get_llm(cfg.llm_provider, cfg.llm_model)
        intelligence = IndexIntelligence(llm=llm)
    except Exception:
        from smartfork.indexer.intelligence import IndexIntelligence

        intelligence = IndexIntelligence(llm=None)

    indexer = FullIndexer(embedder=embedder, store=store, intelligence=intelligence)
    agent_ids = [agent] if agent else None

    from smartfork.cli.display import IndexDisplay

    try:
        with IndexDisplay(console) as display:
            if full:
                stats = indexer.index_all(agent_ids=agent_ids, progress_callback=display.update)
            else:
                stats = indexer.index_incremental(progress_callback=display.update)
            display.finish()
    except RuntimeError as e:
        nl()
        error(str(e))
        raise typer.Exit(1)

    nl()
    t = get_theme()
    rows = [(k, str(v)) for k, v in stats.items() if k != "elapsed_seconds"]
    console.print(kv_table("Indexing Summary", rows))

    chunked = stats.get("chunked", 0)
    stored = stats.get("stored", 0)

    if stored == 0 and chunked > 0:
        nl()
        error(f"{chunked} chunks created but 0 stored as embeddings!")
        info("Search will return empty results. To enable search:")
        info("[yellow]ollama pull qwen3-embedding:0.6b[/yellow]")
        info("[yellow]smartfork index --full[/yellow]")
    else:
        nl()
        success("Indexing complete! Run [bold]smartfork status[/bold] for stats.")


@app.command(rich_help_panel="Core")
def search(
    query: str = typer.Argument(..., help="Search query"),
    results: int = typer.Option(5, "--results", "-n", help="Number of results"),
) -> None:
    """Search indexed sessions."""
    from smartfork.config import get_config
    from smartfork.indexer.metadata_store import MetadataStore
    from smartfork.search.deterministic import DeterministicSearchEngine

    cfg = get_config()
    store = MetadataStore(cfg.sqlite_db_path)
    t = get_theme()

    # Try to set up embedder for vector search
    embedder = None
    try:
        from smartfork.indexer.embedder import EmbeddingPipeline
        from smartfork.providers import get_embedder

        emb = get_embedder(cfg.embedding_provider, cfg.embedding_model, cfg.embedding_dimensions)
        embedder = EmbeddingPipeline(embedder=emb, persist_dir=cfg.qdrant_db_path)
    except Exception:
        pass

    engine = DeterministicSearchEngine(embedder=embedder, metadata_store=store)
    search_results = engine.search(query, top_k=results)

    header("Search")
    info(f"Query: {query}")

    search_mode = "hybrid (vector + BM25)" if embedder else "keyword (BM25) only"

    if embedder is None and not search_results:
        error("Search disabled! No embedding model available.")
        info("Sessions are indexed but embeddings were not stored.")
        info("[yellow]ollama pull qwen3-embedding:0.6b[/yellow]")
        info("[yellow]smartfork index --full[/yellow]")
        return

    if embedder is None and search_results:
        warn("Vector search unavailable — results from keyword (BM25) only.")

    if not search_results:
        info("No results found. Try a different query or check your index.")
        return

    info(f"{len(search_results)} results · {search_mode}")
    nl()

    # Card-style results table
    from rich.table import Table
    from rich import box as rbox

    table = Table(box=rbox.ROUNDED, border_style=t.dim, show_header=False, padding=(0, 1))
    table.add_column("Content", min_width=60)

    for card in search_results:
        excerpt = card.excerpt[:100] + "..." if len(card.excerpt) > 100 else card.excerpt
        line1 = f"[bold white]{card.rank}[/bold white]  [bold]{card.title}[/bold]" + (
            f"  [{t.accent}]{card.match_score:.0%} match[/{t.accent}]"
        )
        line2 = f"[{t.dim}]{card.project_name} · {card.time_ago}[/{t.dim}]"
        line3 = f"[{t.dim}]{excerpt}[/{t.dim}]" if excerpt else ""
        cell = f"{line1}\n{line2}"
        if line3:
            cell += f"\n{line3}"
        table.add_row(cell)

    console.print(table)
    nl()
    info("Run [bold]smartfork fork <session_id>[/bold] to create context.")


@app.command(rich_help_panel="Core")
def fork(
    session_id: str = typer.Argument(..., help="Session ID to fork from"),
    intent: str = typer.Option(
        "continue", "--intent", "-i", help="Fork intent: continue, reference, debug, synthesize"
    ),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Generate fork context from a session."""
    from smartfork.config import get_config
    from smartfork.fork.assembler import ForkAssembler, ForkExporter
    from smartfork.indexer.metadata_store import MetadataStore
    from smartfork.models.fork import ForkIntent
    from smartfork.models.session import QualityTag, SessionDocument

    valid_intents = {"continue", "reference", "debug", "synthesize"}
    if intent not in valid_intents:
        header("Fork")
        error(f"Invalid intent '{intent}'. Valid: {', '.join(valid_intents)}")
        raise typer.Exit(1)

    cfg = get_config()
    store = MetadataStore(cfg.sqlite_db_path)
    session_data = store.get_session(session_id)

    if session_data is None:
        header("Fork")
        error(f"Session '{session_id}' not found in the index.")
        info("Run [bold]smartfork index --full[/bold] to index sessions first.")
        raise typer.Exit(1)

    # Reconstruct SessionDocument from stored data
    doc = SessionDocument(
        session_id=session_data["session_id"],
        agent=session_data["agent"],
        project_name=session_data["project_name"],
        project_root=session_data.get("project_root", ""),
        session_start=session_data.get("session_start", 0),
        session_end=session_data.get("session_end", 0),
        duration_minutes=session_data.get("duration_minutes", 0.0),
        model_used=session_data.get("model_used"),
        files_edited=store._deserialize_list(session_data.get("files_edited", "[]")),
        files_read=store._deserialize_list(session_data.get("files_read", "[]")),
        files_mentioned=store._deserialize_list(session_data.get("files_mentioned", "[]")),
        edit_count=session_data.get("edit_count", 0),
        user_edit_count=session_data.get("user_edit_count", 0),
        final_files=store._deserialize_list(session_data.get("final_files", "[]")),
        domains=store._deserialize_list(session_data.get("domains", "[]")),
        languages=store._deserialize_list(session_data.get("languages", "[]")),
        layers=store._deserialize_list(session_data.get("layers", "[]")),
        session_pattern=session_data.get("session_pattern", "standard_implementation"),
        task_raw=session_data.get("task_raw", ""),
        reasoning_docs=[],
        summary_doc=session_data.get("summary_doc", ""),
        propositions=store._deserialize_list(session_data.get("propositions", "[]")),
        quality_tag=QualityTag(session_data.get("quality_tag", "unknown")),
        tech_tags=store._deserialize_list(session_data.get("tech_tags", "[]")),
        indexed_at=session_data.get("indexed_at", 0),
        schema_version=session_data.get("schema_version", 2),
    )

    fork_intent = ForkIntent(intent)
    assembler = ForkAssembler()
    handoff = assembler.assemble(doc, intent=fork_intent)

    header("Fork")
    info(f"Generating [bold]{intent}[/bold] fork from {session_id}...")

    if output:
        from pathlib import Path

        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(handoff, encoding="utf-8")
        success(f"Handoff saved to: {path}")
    else:
        saved_path = ForkExporter.save_to_file(handoff, session_id, fork_intent)
        success(f"Handoff saved to: {saved_path}")


# ──────────────────────────────────────────────────────────────────────
# System commands
# ──────────────────────────────────────────────────────────────────────


@app.command(rich_help_panel="System")
def setup() -> None:
    """Run the interactive setup wizard."""
    from smartfork.adapters import list_adapters
    from smartfork.providers.helpers import check_ollama_available

    header("Setup")

    # 1. Detect agents
    console.print(" 1. Detecting installed coding agents...")
    adapters = list_adapters()
    found: list[str] = []
    for adapter in adapters:
        try:
            paths = adapter.get_default_sessions_paths()
        except OSError as e:
            warn(f"Cannot access {adapter.display_name} sessions: {e}")
            continue
        except Exception as e:
            warn(f"Failed to detect {adapter.display_name}: {e}")
            continue
        if paths:
            found.append(adapter.display_name)
    if found:
        success(f"Found: {', '.join(found)}")
    else:
        warn("No agents detected. Configure paths manually.")
    nl()

    # 2. Check Ollama
    console.print(" 2. Checking Ollama installation...")
    from smartfork.config import get_config as _get_cfg

    _cfg = _get_cfg()
    if check_ollama_available(_cfg.llm_model):
        success("Ollama is running")
    else:
        warn("Ollama not available. Install from https://ollama.com/download")
    nl()

    # 3. Config
    console.print(" 3. Configuration...")
    from smartfork.config import get_config

    cfg = get_config()
    cfg.save()
    success(f"Config saved to: {cfg.sqlite_db_path.parent / 'config.toml'}")
    nl()
    success("Setup complete! Run [bold]smartfork index[/bold] to begin.")


@app.command(rich_help_panel="System")
def status() -> None:
    """Show indexing statistics and health."""
    from smartfork.config import get_config
    from smartfork.indexer.metadata_store import MetadataStore

    cfg = get_config()
    store = MetadataStore(cfg.sqlite_db_path)
    t = get_theme()

    try:
        stats = store.get_stats()
    except Exception:
        stats = {"total_sessions": 0, "by_project": {}, "by_quality": {}, "by_agent": {}}

    header("Status")

    total = stats["total_sessions"]
    by_project: dict[str, int] = stats.get("by_project", {})
    by_agent: dict[str, int] = stats.get("by_agent", {})
    by_quality: dict[str, int] = stats.get("by_quality", {})

    # Check embeddings
    chunks_count = 0
    emb_model = "N/A"
    try:
        from smartfork.indexer.embedder import EmbeddingPipeline
        from smartfork.providers import get_embedder

        emb = get_embedder(cfg.embedding_provider, cfg.embedding_model, cfg.embedding_dimensions)
        pipeline = EmbeddingPipeline(embedder=emb, persist_dir=cfg.qdrant_db_path)
        emb_stats = pipeline.get_collection_stats()
        chunks_count = emb_stats.get("document_count", 0)
        emb_model = cfg.embedding_model
    except Exception:
        pass

    # Build visual dashboard
    from rich.table import Table
    from rich import box as rbox

    table = Table(box=rbox.ROUNDED, border_style=t.dim, show_header=False, padding=(0, 1), min_width=56)
    table.add_column("Content", min_width=54)

    # Row 1: Overview
    overview = (
        f"[bold]Sessions[/bold]  [{t.accent}]{total}[/{t.accent}]    "
        f"[bold]Chunks[/bold]  [{t.accent}]{chunks_count}[/{t.accent}]    "
        f"[bold]Agents[/bold]  [{t.accent}]{len(by_agent)}[/{t.accent}]"
    )
    table.add_row(overview)

    # Row 2: By agent with bars
    if by_agent:
        agent_lines = []
        max_agent = max(by_agent.values()) if by_agent else 1
        for name, count in sorted(by_agent.items(), key=lambda x: -x[1]):
            bar = inline_bar(count, max_agent, width=12)
            pct = round(count / total * 100) if total else 0
            agent_lines.append(f"[{t.accent}]{bar}[/{t.accent}] {name} {count} ({pct}%)")
        table.add_row("\n".join(agent_lines))

    # Row 3: By project with bars
    if by_project:
        proj_lines = []
        top = sorted(by_project.items(), key=lambda x: -x[1])[:5]
        max_proj = top[0][1] if top else 1
        for name, count in top:
            bar = inline_bar(count, max_proj, width=12)
            proj_lines.append(f"[{t.accent}]{bar}[/{t.accent}] {name} {count}")
        table.add_row("\n".join(proj_lines))

    # Row 4: Quality
    if by_quality:
        high = by_quality.get("solution_found", 0) + by_quality.get("high", 0)
        med = by_quality.get("partial", 0) + by_quality.get("medium", 0)
        low = by_quality.get("dead_end", 0) + by_quality.get("low", 0) + by_quality.get("unknown", 0)
        qbar = quality_minibar(high, med, low)
        table.add_row(f"[bold]Quality[/bold]  [{t.accent}]{qbar}[/{t.accent}]")

    # Row 5: Embeddings
    if chunks_count > 0:
        table.add_row(f"[bold]Embeddings[/bold]  {chunks_count} chunks · {emb_model}")
    else:
        table.add_row(f"[bold]Embeddings[/bold]  [{t.warning}]N/A (embedder not available)[/{t.warning}]")

    console.print(table)

    if total == 0:
        nl()
        info("Run [bold]smartfork index --full[/bold] to populate.")
    elif chunks_count == 0 and total > 0:
        nl()
        error("Search disabled! Sessions indexed but no embeddings stored.")
        info("[yellow]ollama pull qwen3-embedding:0.6b[/yellow]")


@app.command(rich_help_panel="System")
def config(
    action: str = typer.Argument("list", help="Action: get, set, list, reset"),
    key: str | None = typer.Argument(None, help="Config key"),
    value: str | None = typer.Argument(None, help="Config value (for set)"),
) -> None:
    """Manage SmartFork configuration."""
    from smartfork.config import get_config, reload_config

    cfg = get_config()

    if action == "list":
        header("Config")
        rows = [
            ("theme", cfg.theme),
            ("llm_provider", cfg.llm_provider),
            ("llm_model", cfg.llm_model),
            ("embedding_provider", cfg.embedding_provider),
            ("embedding_model", cfg.embedding_model),
            ("embedding_dimensions", str(cfg.embedding_dimensions)),
            ("chunk_size", str(cfg.chunk_size)),
            ("chunk_overlap", str(cfg.chunk_overlap)),
            ("lite_mode", str(cfg.lite_mode)),
            ("sqlite_db_path", str(cfg.sqlite_db_path)),
            ("log_level", cfg.log_level),
        ]
        for name, agent_cfg in cfg.agents.items():
            rows.append((f"agents.{name}.enabled", str(agent_cfg.enabled)))
            rows.append((f"agents.{name}.sessions_path", str(agent_cfg.sessions_path)))
        console.print(kv_table("Configuration", rows))

    elif action == "get" and key:
        if hasattr(cfg, key):
            console.print(f"{key} = {getattr(cfg, key)}")
        else:
            error(f"Unknown config key: {key}")

    elif action == "set" and key and value:
        if hasattr(cfg, key):
            field_type = type(getattr(cfg, key))
            try:
                coerced: Any
                if field_type is bool:
                    coerced = value.lower() in ("true", "1", "yes")
                elif field_type is int:
                    coerced = int(value)
                else:
                    coerced = value
                setattr(cfg, key, coerced)
                cfg.save()
                success(f"Set {key} = {coerced}")
            except Exception as e:
                error(f"Failed to set {key}: {e}")
        else:
            error(f"Unknown config key: {key}")

    elif action == "reset":
        from smartfork.config import CONFIG_FILE

        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()
        reload_config()
        warn("Config reset to defaults.")

    else:
        error("Usage: smartfork config [list|get <key>|set <key> <value>|reset]")


@app.command(rich_help_panel="System")
def theme(
    action: str = typer.Argument("list", help="Action: switch or list"),
    name: str | None = typer.Argument(None, help="Theme name (for switch)"),
) -> None:
    """Switch CLI color palette."""
    from smartfork.config import get_config

    cfg = get_config()

    if action == "list":
        header("Themes")
        for palette_name, palette in PALETTES.items():
            active = f" [{palette.success}](active)[/{palette.success}]" if palette_name == cfg.theme else ""
            console.print(
                f"   [{palette.accent}]{palette_name:<12}[/{palette.accent}] "
                f"[dim]{palette.description}[/dim]{active}"
            )
        nl()
    elif action == "switch" and name:
        if name in VALID_THEMES:
            cfg.theme = name
            cfg.save()
            success(f"Switched to theme: {name}")
        else:
            error(f"Unknown theme '{name}'. Valid: {', '.join(sorted(VALID_THEMES))}")


# ──────────────────────────────────────────────────────────────────────
# Integration commands
# ──────────────────────────────────────────────────────────────────────


@app.command(rich_help_panel="Integrations")
def vault(
    output_dir: str = typer.Option("./smartfork_vault", "--output", "-o", help="Output directory"),
    project_folders: bool = typer.Option(False, "--project-folders", help="Group by project folders"),
) -> None:
    """Generate an Obsidian vault from indexed sessions."""
    from pathlib import Path

    from smartfork.config import get_config
    from smartfork.indexer.metadata_store import MetadataStore
    from smartfork.models.session import QualityTag, SessionDocument
    from smartfork.vault.obsidian import ObsidianVaultGenerator

    cfg = get_config()
    store = MetadataStore(cfg.sqlite_db_path)

    all_ids = store.get_filtered_ids(limit=10_000)
    sessions: list[SessionDocument] = []
    for sid in all_ids:
        data = store.get_session(sid)
        if data:
            sessions.append(
                SessionDocument(
                    session_id=data["session_id"],
                    agent=data["agent"],
                    project_name=data["project_name"],
                    project_root=data.get("project_root", ""),
                    session_start=data.get("session_start", 0),
                    session_end=data.get("session_end", 0),
                    duration_minutes=data.get("duration_minutes", 0.0),
                    model_used=data.get("model_used"),
                    files_edited=store._deserialize_list(data.get("files_edited", "[]")),
                    files_read=store._deserialize_list(data.get("files_read", "[]")),
                    task_raw=data.get("task_raw", ""),
                    summary_doc=data.get("summary_doc", ""),
                    quality_tag=QualityTag(data.get("quality_tag", "unknown")),
                    domains=store._deserialize_list(data.get("domains", "[]")),
                    languages=store._deserialize_list(data.get("languages", "[]")),
                    tech_tags=store._deserialize_list(data.get("tech_tags", "[]")),
                )
            )

    header("Vault")
    info("Generating vault...")
    generator = ObsidianVaultGenerator()
    result_path = generator.generate(sessions=sessions, vault_dir=Path(output_dir), project_folders=project_folders)
    success(f"Vault created at: {result_path}")


@app.command(rich_help_panel="Integrations")
def mcp(
    action: str = typer.Argument("status", help="Action: install, serve, status, uninstall"),
) -> None:
    """Manage MCP server for Claude Code integration."""
    import json
    from pathlib import Path

    mcp_config_path = Path.home() / ".claude" / "mcp.json"
    server_entry = {"smartfork": {"command": "smartfork", "args": ["mcp", "serve"]}}

    if action == "install":
        mcp_config_path.parent.mkdir(parents=True, exist_ok=True)
        mcp_config: dict[str, Any] = {}
        if mcp_config_path.exists():
            try:
                mcp_config = json.loads(mcp_config_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                mcp_config = {}
        if "mcpServers" not in mcp_config:
            mcp_config["mcpServers"] = {}
        mcp_config["mcpServers"].update(server_entry)
        mcp_config_path.write_text(json.dumps(mcp_config, indent=2), encoding="utf-8")
        header("MCP")
        success(f"MCP server installed for Claude Code at {mcp_config_path}")

    elif action == "serve":
        from smartfork.mcp.server import SmartForkMCPServer

        server = SmartForkMCPServer()
        server.start()
        header("MCP")
        info("MCP server running on stdio...")
        info("Press Ctrl+C to stop.")
        try:
            while server.is_running:
                pass
        except KeyboardInterrupt:
            server.stop()

    elif action == "status":
        header("MCP")
        installed = mcp_config_path.exists()
        if installed:
            try:
                mcp_config = json.loads(mcp_config_path.read_text(encoding="utf-8"))
                servers = mcp_config.get("mcpServers", {})
                if "smartfork" in servers:
                    info("MCP server: [green]installed[/green]")
                else:
                    warn("Config exists but SmartFork entry missing")
            except (json.JSONDecodeError, OSError):
                warn("Config file corrupted")
        else:
            info("MCP server: not installed")
            info("Run [bold]smartfork mcp install[/bold] to set up.")

    elif action == "uninstall":
        header("MCP")
        if mcp_config_path.exists():
            try:
                mcp_config = json.loads(mcp_config_path.read_text(encoding="utf-8"))
                servers = mcp_config.get("mcpServers", {})
                servers.pop("smartfork", None)
                mcp_config_path.write_text(json.dumps(mcp_config, indent=2), encoding="utf-8")
                warn("MCP server uninstalled.")
            except (json.JSONDecodeError, OSError):
                error("Failed to read MCP config.")
        else:
            info("MCP server was not installed.")

    else:
        error("Usage: smartfork mcp [install|serve|status|uninstall]")


if __name__ == "__main__":
    app()
