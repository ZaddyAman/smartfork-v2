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
    enrich: bool = typer.Option(False, "--enrich", help="Enable LLM enrichment"),
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
        embedder = EmbeddingPipeline(embedder=emb, store=store)
    except Exception as e:
        error(f"Embedder not available: {e}")
        info("Search requires embeddings to function. Please fix the issue above and try again.")
        raise typer.Exit(1) from None

    # Try to set up LLM for intelligence (only when --enrich flag is passed)
    intelligence = None
    if enrich:
        try:
            from smartfork.indexer.intelligence import IndexIntelligence
            from smartfork.providers import get_llm

            llm = get_llm(cfg.llm_provider, cfg.llm_model)
            intelligence = IndexIntelligence(llm=llm)
        except Exception:
            from smartfork.indexer.intelligence import IndexIntelligence

            intelligence = IndexIntelligence(llm=None)
    else:
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
        raise typer.Exit(1) from None

    nl()
    t = get_theme()

    from rich import box as rbox
    from rich.table import Table

    summary_table = Table(
        title="Indexing Summary",
        box=rbox.ROUNDED,
        border_style=t.dim,
        title_style=f"bold {t.accent}",
        show_header=False,
        padding=(0, 1),
    )
    summary_table.add_column("Metric", style=t.accent, min_width=20)
    summary_table.add_column("Value", min_width=20)

    # Quality breakdown from store
    try:
        quality_stats = store.get_stats().get("by_quality", {})
    except Exception:
        quality_stats = {}
    high = quality_stats.get("solution_found", 0)
    medium = quality_stats.get("partial", 0) + quality_stats.get("reference", 0)
    low = quality_stats.get("dead_end", 0) + quality_stats.get("unknown", 0)

    parsed = stats.get("parsed", 0)
    stored = stats.get("stored", 0)
    enriched = stats.get("enriched", 0)
    errors = stats.get("errors", 0)
    elapsed = stats.get("elapsed_seconds", 0.0)

    throughput_ses = parsed / elapsed if elapsed > 0 else 0.0
    throughput_vec = stored / elapsed if elapsed > 0 else 0.0

    if elapsed < 60:
        elapsed_str = f"{elapsed:.1f}s"
    else:
        minutes = int(elapsed // 60)
        secs = elapsed % 60
        elapsed_str = f"{minutes}m {secs:.1f}s"

    summary_rows = [
        ("Sessions parsed", str(parsed)),
        ("Sessions embedded", str(stored)),
        ("Vectors stored", str(stored)),
        ("LLM enriched", str(enriched)),
        ("Errors", str(errors)),
        ("Throughput", f"{throughput_ses:.1f} ses/s · {throughput_vec:.1f} vec/s"),
        ("Quality breakdown", quality_minibar(high, medium, low)),
        ("Total time", elapsed_str),
    ]

    for label, value in summary_rows:
        summary_table.add_row(label, value)

    console.print(summary_table)

    parsed = stats.get("parsed", 0)
    stored = stats.get("stored", 0)

    if stored == 0 and parsed > 0:
        nl()
        error(f"{parsed} sessions parsed but 0 vectors stored!")
        info("Search will return empty results. To enable search:")
        info("[yellow]ollama pull qwen3-embedding:0.6b[/yellow]")
        info("[yellow]smartfork index --full[/yellow]")
    else:
        nl()
        success("Indexing complete! Run [bold]smartfork status[/bold] for stats.")


def _validate_mode(value: str) -> str:
    if value not in {"auto", "deterministic", "deep"}:
        raise typer.BadParameter(f"Invalid mode '{value}'. Choose from: auto, deterministic, deep")
    return value


@app.command(rich_help_panel="Core")
def search(
    query: str = typer.Argument(..., help="Search query"),
    results: int = typer.Option(5, "--results", "-n", help="Number of results"),
    fast: bool = typer.Option(
        False, "--fast", help="Use deterministic search directly (0 LLM calls)"
    ),
    deep: bool = typer.Option(
        False, "--deep", help="Enable deep mode (multi-session synthesis, +1 LLM call)"
    ),
    mode: str = typer.Option(
        "auto",
        "--mode",
        callback=_validate_mode,
        help="Search mode: auto, deterministic, deep",
    ),
) -> None:
    """Search indexed sessions."""
    from smartfork.config import get_config
    from smartfork.indexer.metadata_store import MetadataStore

    cfg = get_config()
    store = MetadataStore(cfg.sqlite_db_path)
    t = get_theme()

    # Try to set up embedder for vector search
    embedder = None
    try:
        from smartfork.indexer.embedder import EmbeddingPipeline
        from smartfork.providers import get_embedder

        emb = get_embedder(cfg.embedding_provider, cfg.embedding_model, cfg.embedding_dimensions)
        embedder = EmbeddingPipeline(embedder=emb, store=store)
    except Exception:
        pass

    import time
    search_start = time.time()
    search_results: list[Any] = []
    orchestrator: Any = None

    if fast or mode == "deterministic":
        # Deterministic path: skip QueryInterpreter, use DeterministicSearchEngine directly
        from smartfork.search.deterministic import DeterministicSearchEngine

        engine = DeterministicSearchEngine(embedder=embedder, metadata_store=store)
        search_results = engine.search(query, top_k=results)
    else:
        # Default / Deep path: SearchOrchestrator with QueryInterpreter
        from smartfork.providers import get_llm
        from smartfork.search.orchestrator import SearchOrchestrator

        try:
            llm_provider = cfg.llm_provider
            llm_model = cfg.llm_model
            llm = get_llm(llm_provider, llm_model)
        except RuntimeError as e:
            error(f"LLM setup failed: {e}")
            info(
                "Run with [bold]--fast[/bold] or [bold]--mode deterministic[/bold] "
                "to skip the orchestrator and use deterministic search."
            )
            raise typer.Exit(1) from None

        use_deep = deep or mode == "deep"
        orchestrator = SearchOrchestrator(
            embedder=embedder,
            metadata_store=store,
            llm=llm,
            use_fast=False,
            use_deep=use_deep,
        )

        try:
            search_results = orchestrator.search(query, top_k=results)
        except RuntimeError as e:
            error(f"Search failed: {e}")
            info(
                "Run with [bold]--fast[/bold] or [bold]--mode deterministic[/bold] "
                "to skip the orchestrator and use deterministic search."
            )
            raise typer.Exit(1) from None

    search_duration = time.time() - search_start

    header("Search")
    info(f"Query: {query}")

    if fast or mode == "deterministic":
        search_mode = (
            "deterministic (vector + BM25 + RRF + rerank + cards)"
            if embedder
            else "deterministic (BM25 + RRF + rerank + cards)"
        )

        if embedder is None and not search_results:
            error("Search disabled! No embedding model available.")
            info("Sessions are indexed but embeddings were not stored.")
            info("[yellow]ollama pull qwen3-embedding:0.6b[/yellow]")
            info("[yellow]smartfork index --full[/yellow]")
            return

        if embedder is None and search_results:
            warn("Vector search unavailable — results from keyword (BM25) only.")
    elif deep or mode == "deep":
        search_mode = "deep (interpret + search + graph + synthesize)"
    else:
        search_mode = "default (interpret + deterministic search)"

    if not search_results:
        info("No relevant sessions found.")
        if orchestrator is not None and orchestrator.last_empty_reasoning:
            info(f"Reason: {orchestrator.last_empty_reasoning}")
        if fast or mode == "deterministic":
            info("Try running without --fast for AI-assisted search.")
        elif embedder is None:
            info("Search requires embeddings. Run [yellow]smartfork index --full[/yellow]")
        else:
            info("Try a different query or run [bold]smartfork index --full[/bold] to refresh.")
        return

    info(f"{len(search_results)} results · {search_duration:.1f}s · {search_mode}")
    nl()

    from rich import box as rbox
    from rich.align import Align
    from rich.console import Group
    from rich.panel import Panel
    from rich.text import Text

    # Constrain card width so titles don't blow out the terminal
    panel_width = min(console.width - 4, 80) if console.width else 76

    for card in search_results:
        # Build title bar: [rank] title · badge · project_name · time_ago
        max_title_bar_len = 45
        display_title = card.title
        if len(display_title) > max_title_bar_len:
            display_title = display_title[: max_title_bar_len - 3] + "..."

        if card.quality_badge:
            badge = f"{card.quality_badge} {card.match_score:.0%}"
        else:
            if card.match_score >= 0.8:
                score_color = t.success
            elif card.match_score >= 0.6:
                score_color = t.warning
            else:
                score_color = t.error
            badge = f"[{score_color}]{card.match_score:.0%} match[/{score_color}]"

        title_parts = [
            f"[{t.accent}]{card.rank}[/{t.accent}]",
            f"[bold]{display_title}[/bold]",
        ]
        if card.supersession_note:
            title_parts.append(card.supersession_note)
        title_parts.append(badge)
        if card.project_name:
            title_parts.append(f"[{t.dim}]{card.project_name}[/{t.dim}]")
        if card.time_ago:
            title_parts.append(f"[{t.dim}]{card.time_ago}[/{t.dim}]")

        title_bar = "  ".join(title_parts)

        # Body content: excerpt, tags, files_summary, fork_command
        body_lines: list[str] = []
        if card.excerpt:
            body_lines.append(card.excerpt)

        if card.tags:
            body_lines.append(f"[{t.dim}]tags: {', '.join(card.tags)}[/{t.dim}]")

        if card.files_summary:
            body_lines.append(f"[{t.dim}]{card.files_summary}[/{t.dim}]")

        body = "\n".join(body_lines)

        # Right-aligned footer inside the panel
        footer_text = Text.from_markup(f"[{t.dim}]fork: {card.fork_command}[/{t.dim}]")
        card_content = Group(
            Text.from_markup(body),
            Align.right(footer_text),
        )

        panel = Panel(
            card_content,
            title=title_bar,
            title_align="left",
            border_style=t.accent,
            box=rbox.ROUNDED,
            padding=(0, 1),
            width=panel_width,
        )
        console.print(panel)
        console.print()  # blank line between cards

    nl()

    # Deep mode: show timeline + narrative
    if (deep or mode == "deep") and search_results:
        first_synthesis = getattr(search_results[0], "synthesis", None)
        if first_synthesis is not None:
            _display_timeline(first_synthesis)

    # Borderline confidence suggestion
    if (
        not fast
        and mode not in ("deterministic", "deep")
        and orchestrator is not None
        and search_results
    ):
        confidence = getattr(orchestrator, "last_multi_session_confidence", 0.0)
        if isinstance(confidence, (int, float)) and 0.40 <= confidence <= 0.75:
            info(
                f"{len(search_results)} results found. "
                "Add [bold]--deep[/bold] for timeline and narrative."
            )

    info("Run [bold]smartfork fork <session_id>[/bold] to create context.")


def _display_timeline(synthesis: Any) -> None:
    """Render timeline and narrative panels from a TimelineSummary."""
    from rich import box as rbox
    from rich.panel import Panel
    from rich.text import Text
    from rich.tree import Tree

    if synthesis.narrative:
        narrative_panel = Panel(
            Text(synthesis.narrative),
            title="[bold]Narrative[/bold]",
            border_style="blue",
            box=rbox.ROUNDED,
        )
        console.print(narrative_panel)

    if synthesis.timeline:
        tree = Tree("[bold]Timeline[/bold]")
        for entry in synthesis.timeline:
            task = entry.task or "Untitled"
            quality = getattr(entry.quality_tag, "value", str(entry.quality_tag))
            date_str = ""
            if entry.timestamp > 0:
                from datetime import datetime

                date_str = datetime.fromtimestamp(entry.timestamp / 1000).strftime(
                    "%Y-%m-%d"
                )
            label = f"{date_str} — {task} ({quality})"
            tree.add(label)

        timeline_panel = Panel(
            tree,
            title="[bold]Timeline[/bold]",
            border_style="green",
            box=rbox.ROUNDED,
        )
        console.print(timeline_panel)

    if synthesis.suggested_fork_session_id:
        info(
            "Suggested fork: "
            f"[bold]smartfork fork {synthesis.suggested_fork_session_id}[/bold]"
        )


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

    valid_intents = {"continue", "reference", "debug", "synthesize"}
    if intent not in valid_intents:
        header("Fork")
        error(f"Invalid intent '{intent}'. Valid: {', '.join(valid_intents)}")
        raise typer.Exit(1)

    cfg = get_config()
    store = MetadataStore(cfg.sqlite_db_path)
    doc = store.get_session_document(session_id)

    if doc is None:
        header("Fork")
        error(f"Session '{session_id}' not found in the index.")
        info("Run [bold]smartfork index --full[/bold] to index sessions first.")
        raise typer.Exit(1)

    # Check if session is superseded
    superseding = store.get_superseding_sessions(session_id)
    supersession_warning = ""
    if superseding:
        latest_id = superseding[0].get("superseding_id", "unknown")
        supersession_warning = (
            f"This session was superseded by {latest_id}. "
            "Consider forking from the latest version."
        )
        warn(supersession_warning)

    fork_intent = ForkIntent(intent)
    assembler = ForkAssembler()
    handoff = assembler.assemble(doc, intent=fork_intent, supersession_warning=supersession_warning)

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
    vector_count = 0
    emb_model = "N/A"
    try:
        vector_count = store.get_vector_count()
        emb_model = cfg.embedding_model
    except Exception:
        pass

    from rich import box as rbox
    from rich.console import Group
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text

    lines: list[Any] = []

    # Section 1: Overview
    overview_table = Table(box=None, show_header=False, padding=(0, 0))
    overview_table.add_column(style="bold", min_width=10)
    overview_table.add_column(style=t.accent, min_width=8)
    overview_table.add_column(style="bold", min_width=10)
    overview_table.add_column(style=t.accent, min_width=8)
    overview_table.add_column(style="bold", min_width=10)
    overview_table.add_column(style=t.accent, min_width=8)
    overview_table.add_row(
        "Sessions", str(total), "Vectors", str(vector_count), "Agents", str(len(by_agent))
    )
    lines.append(overview_table)

    # Section 1b: Agent bars
    if by_agent:
        agent_lines = []
        max_agent = max(by_agent.values()) if by_agent else 1
        for name, count in sorted(by_agent.items(), key=lambda x: -x[1]):
            bar = inline_bar(count, max_agent, width=12)
            pct = round(count / total * 100) if total else 0
            agent_lines.append(
                f"[{t.accent}]{bar}[/{t.accent}] {name} {count} ({pct}%)"
            )
        lines.append(Text.from_markup("\n".join(agent_lines)))

    # Separator
    if by_agent or by_project:
        lines.append(Rule(style=t.dim))

    # Section 2: Projects
    if by_project:
        lines.append(Text("Projects", style=f"bold {t.accent}"))
        projects_table = Table(box=None, show_header=False, padding=(0, 0))
        projects_table.add_column(min_width=14)
        projects_table.add_column(style=t.accent, min_width=16)
        projects_table.add_column(min_width=6)
        top = sorted(by_project.items(), key=lambda x: -x[1])[:5]
        max_proj = top[0][1] if top else 1
        for name, count in top:
            bar = inline_bar(count, max_proj, width=12)
            projects_table.add_row(name, bar, str(count))
        lines.append(projects_table)
        lines.append(Text(""))

    # Separator
    if by_project and by_quality:
        lines.append(Rule(style=t.dim))

    # Section 3: Quality
    if by_quality:
        lines.append(Text("Quality", style=f"bold {t.accent}"))
        high = by_quality.get("solution_found", 0) + by_quality.get("high", 0)
        med = by_quality.get("partial", 0) + by_quality.get("medium", 0)
        low = (
            by_quality.get("dead_end", 0)
            + by_quality.get("low", 0)
            + by_quality.get("unknown", 0)
        )
        total_qual = high + med + low

        quality_table = Table(box=None, show_header=False, padding=(0, 0))
        quality_table.add_column(min_width=8)
        quality_table.add_column(style=t.success, min_width=16)
        quality_table.add_column(min_width=6)

        if total_qual > 0:
            max_qual = max(high, med, low) if any((high, med, low)) else 1
            if high:
                quality_table.add_row("high", inline_bar(high, max_qual, width=12), str(high))
            if med:
                quality_table.add_row("medium", inline_bar(med, max_qual, width=12), str(med))
            if low:
                quality_table.add_row("low", inline_bar(low, max_qual, width=12), str(low))
        else:
            quality_table.add_row("—", "", "")
        lines.append(quality_table)
        lines.append(Text(""))

    # Separator (always show before embeddings)
    lines.append(Rule(style=t.dim))

    # Section 4: Embeddings
    lines.append(Text("Embeddings", style=f"bold {t.accent}"))
    if vector_count > 0:
        lines.append(Text(f"{vector_count} vectors stored · {emb_model}"))
    else:
        lines.append(Text("Vector count unknown (sqlite-vec not available)", style=t.warning))

    content = Group(*lines)
    panel = Panel(
        content,
        title=f"[bold]SmartFork[/bold] · [{t.accent}]Status[/{t.accent}]",
        title_align="left",
        border_style=t.dim,
        box=rbox.ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)

    if total == 0:
        nl()
        info("Run [bold]smartfork index --full[/bold] to populate.")
    elif vector_count == 0 and total > 0:
        nl()
        error("Search disabled! Sessions indexed but no vectors stored.")
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
            active = (
                f" [{palette.success}](active)[/{palette.success}]"
                if palette_name == cfg.theme
                else ""
            )
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
    output_dir: str = typer.Option(
        "./smartfork_vault", "--output", "-o", help="Output directory"
    ),
    project_folders: bool = typer.Option(
        False, "--project-folders", help="Group by project folders"
    ),
) -> None:
    """Generate an Obsidian vault from indexed sessions."""
    from pathlib import Path

    from smartfork.config import get_config
    from smartfork.indexer.metadata_store import MetadataStore
    from smartfork.vault.obsidian import ObsidianVaultGenerator

    cfg = get_config()
    store = MetadataStore(cfg.sqlite_db_path)
    sessions = store.get_all_session_documents(limit=10_000)

    header("Vault")
    info("Generating vault...")
    generator = ObsidianVaultGenerator()
    result_path = generator.generate(
        sessions=sessions,
        vault_dir=Path(output_dir),
        project_folders=project_folders,
    )
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
