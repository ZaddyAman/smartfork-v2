"""Textual TUI application for SmartFork v2."""

from pathlib import Path

from smartfork.tui.screens.main import MainScreen


def run_tui() -> None:
    """Launch the Textual TUI, or fall back to CLI if Textual is unavailable."""
    try:
        from textual.app import App

        class SmartForkApp(App):  # type: ignore[misc]
            """SmartFork v2 Textual TUI."""

            CSS_PATH = _get_theme_path("obsidian")
            BINDINGS = [
                ("ctrl+o", "show_command_palette", "Command Palette"),
                ("ctrl+q", "quit", "Quit"),
                ("ctrl+s", "toggle_search", "Search"),
                ("ctrl+f", "toggle_fork", "Fork"),
            ]

            def on_mount(self) -> None:
                self.push_screen(MainScreen())

        app = SmartForkApp()
        app.run()

    except ImportError:
        print(
            "Textual TUI is not installed. Install it with: pip install textual\n"
            "Falling back to CLI mode. Use 'smartfork --help' for commands."
        )


def _get_theme_path(theme: str) -> str:
    """Get the path to a theme CSS file."""
    theme_dir = Path(__file__).parent / "themes"
    theme_file = theme_dir / f"{theme}.tcss"
    return str(theme_file)
