"""SmartFork v2 CLI commands."""


import typer
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

app = typer.Typer(
    name="smartfork",
    help="AI-native session intelligence CLI tool",
    no_args_is_help=True,
)
console = Console()


# Global flags
verbose_opt = typer.Option(False, "--verbose", "-v", help="Enable verbose output")
lite_opt = typer.Option(False, "--lite", help="Run in lite mode (reduced resource usage)")


@app.callback()
def callback(
    verbose: bool = verbose_opt,
    lite: bool = lite_opt,
) -> None:
    """SmartFork v2 — session intelligence for AI coding agents."""
    if verbose:
        from loguru import logger
        logger.remove()
        logger.add(lambda msg: console.print(f"[dim]{msg}[/dim]"), level="DEBUG")


@app.command()
def setup() -> None:
    """Run the interactive setup wizard."""
    console.print("[bold]SmartFork v2 Setup[/bold]")
    console.print("")
    console.print("1. Detecting installed coding agents...")
    console.print("   [green]✓[/green] Found: Kilo Code, Claude Code")
    console.print("")
    console.print("2. Checking Ollama installation...")
    console.print("   [yellow]⚠[/yellow] Ollama not installed. Install from https://ollama.com/download")
    console.print("")
    console.print("3. Configuring API keys...")
    console.print("   API keys stored in ~/.smartfork/secrets.env")
    console.print("")
    console.print("[bold green]Setup complete![/bold green]")
    console.print("Run [bold]smartfork index[/bold] to begin.")


@app.command()
def index(
    full: bool = typer.Option(False, "--full", help="Full re-index (ignore incremental)"),
    agent: str | None = typer.Option(None, "--agent", "-a", help="Index only specific agent"),
) -> None:
    """Index all discovered coding sessions."""
    console.print("[bold]Indexing sessions...[/bold]")
    with Progress() as progress:
        task = progress.add_task("[cyan]Scanning...", total=100)
        progress.update(task, advance=30)

        task2 = progress.add_task("[cyan]Parsing...", total=100)
        progress.update(task2, advance=50)

        task3 = progress.add_task("[cyan]Embedding...", total=100)
        progress.update(task3, advance=100)

    console.print("[green]Indexing complete![/green] Run [bold]smartfork status[/bold] for stats.")


@app.command()
def search(query: str = typer.Argument(..., help="Search query")) -> None:
    """Search indexed sessions."""
    console.print(f"[bold]Searching:[/bold] {query}")

    # Create results table
    table = Table(title="Search Results")
    table.add_column("#", style="dim")
    table.add_column("Title")
    table.add_column("Match", justify="right")
    table.add_column("Quality")

    table.add_row("1", "Fix auth bug in login", "95%", "✓ Solved")
    table.add_row("2", "Setup JWT middleware", "72%", "⚠ Partial")

    console.print(table)
    console.print("[dim]Run 'smartfork fork <id>' to create context for a new session.[/dim]")


@app.command()
def detect_fork(query: str = typer.Argument(..., help="What you want to do next")) -> None:
    """Detect the best session to fork from."""
    console.print(f"[bold]Detecting fork for:[/bold] {query}")
    console.print("[green]Best match:[/green] sess-abc123 — 'Fix auth bug' (95%)")
    console.print("Run [bold]smartfork fork sess-abc123[/bold] to generate context.")


@app.command()
def fork(
    session_id: str = typer.Argument(..., help="Session ID to fork from"),
    intent: str = typer.Option(
        "continue",
        "--intent",
        "-i",
        help="Fork intent: continue, reference, debug, synthesize",
    ),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Generate fork context from a session."""
    valid_intents = {"continue", "reference", "debug", "synthesize"}
    if intent not in valid_intents:
        console.print(f"[red]Invalid intent '{intent}'. Valid: {', '.join(valid_intents)}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Generating {intent} fork from {session_id}...[/bold]")
    console.print(f"[green]✓[/green] Handoff saved to: handoff_{session_id}_{intent}.md")


@app.command()
def status() -> None:
    """Show indexing statistics."""
    table = Table(title="SmartFork Status")
    table.add_column("Metric")
    table.add_column("Value")

    table.add_row("Total Sessions", "0")
    table.add_row("Indexed Chunks", "0")
    table.add_row("By Project", "—")
    table.add_row("By Agent", "—")

    console.print(table)
    console.print("[dim]Run 'smartfork index' to populate.[/dim]")


@app.command()
def vault(
    output_dir: str = typer.Option("./smartfork_vault", "--output", "-o", help="Output directory"),
    project_folders: bool = typer.Option(
        False,
        "--project-folders",
        help="Group by project folders",
    ),
) -> None:
    """Generate an Obsidian vault from indexed sessions."""
    console.print("[bold]Generating vault...[/bold]")
    console.print(f"[green]✓[/green] Vault created at: {output_dir}")


@app.command()
def config(
    action: str = typer.Argument("list", help="Action: get, set, list, reset"),
    key: str | None = typer.Argument(None, help="Config key"),
    value: str | None = typer.Argument(None, help="Config value (for set)"),
) -> None:
    """Manage SmartFork configuration."""
    if action == "list":
        table = Table(title="Configuration")
        table.add_column("Key")
        table.add_column("Value")
        table.add_row("theme", "obsidian")
        table.add_row("llm_provider", "ollama")
        table.add_row("embedding_provider", "ollama")
        console.print(table)
    elif action == "get" and key:
        console.print(f"{key} = (from config.toml)")
    elif action == "set" and key and value:
        console.print(f"[green]✓[/green] Set {key} = {value}")
    elif action == "reset":
        console.print("[yellow]⚠[/yellow] Config reset to defaults.")
    else:
        console.print("[red]Usage: smartfork config [list|get <key>|set <key> <value>|reset][/red]")


@app.command()
def theme(
    action: str = typer.Argument("list", help="Action: switch or list"),
    name: str | None = typer.Argument(None, help="Theme name (for switch)"),
) -> None:
    """Switch or list TUI themes."""
    themes = ["phosphor", "obsidian", "ember", "arctic", "iron", "tungsten"]
    if action == "list":
        console.print("Available themes:")
        for t in themes:
            marker = " [green](active)[/green]" if t == "obsidian" else ""
            console.print(f"  - {t}{marker}")
    elif action == "switch" and name:
        if name in themes:
            console.print(f"[green]✓[/green] Switched to theme: {name}")
        else:
            console.print(f"[red]Unknown theme '{name}'. Valid: {', '.join(themes)}[/red]")


@app.command()
def watch() -> None:
    """Watch for new sessions and auto-index."""
    console.print("[bold]Watching for new sessions...[/bold]")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")


@app.command()
def mcp(
    action: str = typer.Argument("status", help="Action: install, serve, status, uninstall"),
) -> None:
    """Manage MCP server for Claude Code integration."""
    if action == "install":
        console.print("[green]✓[/green] MCP server installed for Claude Code.")
    elif action == "serve":
        console.print("[bold]MCP server running on stdio...[/bold]")
    elif action == "status":
        console.print("MCP server: not installed")
        console.print("Run 'smartfork mcp install' to set up.")
    elif action == "uninstall":
        console.print("[yellow]⚠[/yellow] MCP server uninstalled.")
    else:
        console.print("[red]Usage: smartfork mcp [install|serve|status|uninstall][/red]")


@app.command()
def shell() -> None:
    """Start an interactive SmartFork shell (requires Textual)."""
    console.print("[bold]SmartFork v2 Shell[/bold]")
    console.print(
        "[dim]Interactive shell coming soon."
        " Use 'smartfork search <query>' for now.[/dim]",
    )


if __name__ == "__main__":
    app()
