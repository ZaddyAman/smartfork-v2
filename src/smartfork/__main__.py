"""SmartFork v2 entry point."""
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from smartfork.cli.commands import app

if __name__ == "__main__":
    app()
