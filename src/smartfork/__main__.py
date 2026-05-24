"""SmartFork v2 entry point."""
import sys
from typing import Any

if sys.platform == "win32":
    stdout: Any = sys.stdout
    stderr: Any = sys.stderr
    if hasattr(stdout, "reconfigure"):
        stdout.reconfigure(encoding="utf-8")
    if hasattr(stderr, "reconfigure"):
        stderr.reconfigure(encoding="utf-8")

from smartfork.cli.commands import app

if __name__ == "__main__":
    app()
