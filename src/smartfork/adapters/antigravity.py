"""AntiGravity session adapter for SmartFork v2.

AntiGravity uses the same Kilo Code session format but stores sessions
in AntiGravity-specific directories.
"""

import os
import platform
from pathlib import Path

from smartfork.adapters.kilocode import KiloCodeAdapter
from smartfork.adapters.registry import register


@register
class AntiGravityAdapter(KiloCodeAdapter):
    """Adapter for AntiGravity's Kilo Code-based sessions.

    Inherits all parsing logic from KiloCodeAdapter but overrides
    IDE detection to use AntiGravity-specific paths.
    """

    agent_id = "antigravity"
    display_name = "AntiGravity"
    session_type = "dir"

    def get_ide_choices(self) -> list[str]:
        return ["AntiGravity"]

    def get_default_path_for_ide(self, ide: str) -> Path | None:
        if ide == "AntiGravity":
            sys_platform = platform.system().lower()
            base = Path.home()
            if sys_platform == "windows":
                appdata = os.environ.get("APPDATA", "")
                base = Path(appdata)
            elif sys_platform == "darwin":
                base = base / "Library" / "Application Support"
            else:
                base = base / ".config"
            return (
                base
                / "AntiGravity"
                / "User"
                / "globalStorage"
                / "kilocode.kilo-code"
                / "tasks"
            )
        return None
