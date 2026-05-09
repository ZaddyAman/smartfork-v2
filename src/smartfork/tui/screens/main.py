"""Main screen for SmartFork v2 TUI."""

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Static


class MainScreen(Screen):  # type: ignore[misc]
    """Main search/command screen."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("ctrl+p", "focus_command", "Focus Command"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Static("SmartFork v2 — Session Intelligence", id="title"),
            Input(placeholder="Enter a command or search query...", id="command-input"),
            VerticalScroll(
                Static("Ready. Type a command or search query.", id="output-area"),
                id="results",
            ),
        )
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command input."""
        query = event.value.strip()
        if not query:
            return

        output = self.query_one("#output-area", Static)
        if query.startswith("search "):
            search_term = query[7:]
            output.update(f"[bold]Searching:[/bold] {search_term}\n\nShowing results...")
        elif query.startswith("fork "):
            output.update(f"[bold]Forking session:[/bold] {query[5:]}\n\nGenerating context...")
        elif query == "status":
            output.update(
                "SmartFork v2 Status\n"
                "━━━━━━━━━━━━━━━━━\n"
                "Sessions indexed: 0\n"
                "Chunks stored: 0\n"
            )
        elif query == "help":
            output.update(
                "Commands:\n"
                "  search <query>  — Search sessions\n"
                "  fork <id>       — Fork session context\n"
                "  status          — Show stats\n"
                "  config          — Show config\n"
                "  help            — This help\n"
                "  quit            — Exit\n"
            )
        elif query == "quit":
            self.app.exit()
        else:
            output.update(f"Unknown command: {query}\nType 'help' for available commands.")

        event.input.clear()

    def action_focus_command(self) -> None:
        """Focus the command input."""
        self.query_one("#command-input", Input).focus()
