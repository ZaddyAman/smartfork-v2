"""SmartFork v2 CLI commands."""

import typer

app = typer.Typer(
    name="smartfork",
    help="AI-native session intelligence CLI tool",
    no_args_is_help=True,
)


@app.callback()
def callback() -> None:
    """SmartFork v2 — session intelligence for AI coding agents."""


@app.command()
def hello() -> None:
    """Placeholder command to verify CLI works."""
    typer.echo("SmartFork v2 CLI is installed and working!")


if __name__ == "__main__":
    app()
