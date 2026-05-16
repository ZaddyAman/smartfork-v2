"""SmartFork CLI design system — palettes, output helpers, and custom progress columns."""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from rich import box
from rich.console import Console, RenderableType
from rich.progress import ProgressColumn, Task
from rich.style import Style
from rich.table import Table
from rich.text import Text


# ──────────────────────────────────────────────────────────────────────
# Palette definitions
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CLITheme:
    """A named CLI color palette with semantic tokens."""

    name: str
    description: str
    accent: str
    success: str
    warning: str
    error: str
    dim: str
    heading: str = "bold white"
    muted: str = "dim"


PALETTES: dict[str, CLITheme] = {
    "obsidian": CLITheme(
        name="obsidian",
        description="dark, violet-cyan — premium dev tooling",
        accent="#7c3aed",
        success="#a3e635",
        warning="#fbbf24",
        error="#f87171",
        dim="#6b7280",
    ),
    "phosphor": CLITheme(
        name="phosphor",
        description="retro terminal, neon green — hacker aesthetic",
        accent="#39ff14",
        success="#39ff14",
        warning="#facc15",
        error="#ff6b6b",
        dim="#4ade80",
    ),
    "ember": CLITheme(
        name="ember",
        description="warm, orange-amber — distinctive warmth",
        accent="#f97316",
        success="#a3e635",
        warning="#fbbf24",
        error="#f87171",
        dim="#a8a29e",
    ),
    "arctic": CLITheme(
        name="arctic",
        description="cool, sky blue — minimal Scandinavian",
        accent="#38bdf8",
        success="#34d399",
        warning="#fbbf24",
        error="#fb7185",
        dim="#94a3b8",
    ),
    "iron": CLITheme(
        name="iron",
        description="muted violet — understated depth",
        accent="#6d6494",
        success="#a3e635",
        warning="#fbbf24",
        error="#f87171",
        dim="#737373",
    ),
    "tungsten": CLITheme(
        name="tungsten",
        description="greyscale — zero distraction, pure focus",
        accent="#a3a3a3",
        success="#a3e635",
        warning="#fbbf24",
        error="#f87171",
        dim="#737373",
    ),
}

VALID_THEMES = set(PALETTES.keys())


def get_theme() -> CLITheme:
    """Return the active CLI palette from config. Falls back to obsidian."""
    try:
        from smartfork.config import get_config
        name = get_config().theme
    except Exception:
        name = "obsidian"
    return PALETTES.get(name, PALETTES["obsidian"])


# ──────────────────────────────────────────────────────────────────────
# Shared console
# ──────────────────────────────────────────────────────────────────────

_console: Console | None = None


def get_console() -> Console:
    """Return a shared Console instance."""
    global _console
    if _console is None:
        _console = Console()
    return _console


# ──────────────────────────────────────────────────────────────────────
# Output helpers
# ──────────────────────────────────────────────────────────────────────

def header(cmd_name: str) -> None:
    """Print a branded command header: SmartFork · CommandName."""
    t = get_theme()
    c = get_console()
    c.print()
    c.print(f" [{t.accent}]SmartFork[/{t.accent}] · [bold white]{cmd_name}[/bold white]")
    c.print()


def success(msg: str) -> None:
    """Print a success message with ✓."""
    t = get_theme()
    get_console().print(f" [{t.success}]✓[/{t.success}] {msg}")


def warn(msg: str) -> None:
    """Print a warning message with ▲."""
    t = get_theme()
    get_console().print(f" [{t.warning}]▲[/{t.warning}] {msg}")


def error(msg: str) -> None:
    """Print an error message with ✗."""
    t = get_theme()
    get_console().print(f" [{t.error}]✗[/{t.error}] {msg}")


def info(msg: str) -> None:
    """Print an info/hint message with ›."""
    t = get_theme()
    get_console().print(f"   [{t.dim}]›[/{t.dim}] {msg}")


def nl() -> None:
    """Print a blank line."""
    get_console().print()


# ──────────────────────────────────────────────────────────────────────
# Table helpers
# ──────────────────────────────────────────────────────────────────────

def kv_table(title: str, rows: list[tuple[str, str]]) -> Table:
    """Create a themed key-value table."""
    t = get_theme()
    table = Table(
        title=title,
        box=box.ROUNDED,
        border_style=t.dim,
        title_style=f"bold {t.accent}",
        show_header=True,
        header_style=f"bold {t.accent}",
    )
    table.add_column("Metric", style=t.accent, min_width=20)
    table.add_column("Value", min_width=20)
    for key, value in rows:
        table.add_row(key, value)
    return table


def results_table(
    title: str,
    columns: list[tuple[str, dict[str, Any]]],
    rows: list[list[str]],
) -> Table:
    """Create a themed multi-column results table."""
    t = get_theme()
    table = Table(
        title=title,
        box=box.ROUNDED,
        border_style=t.dim,
        title_style=f"bold {t.accent}",
        show_header=True,
        header_style=f"bold {t.accent}",
    )
    for col_name, col_kwargs in columns:
        table.add_column(col_name, **col_kwargs)
    for row in rows:
        table.add_row(*row)
    return table


# ──────────────────────────────────────────────────────────────────────
# Inline bar chart helper (for status dashboard)
# ──────────────────────────────────────────────────────────────────────

def inline_bar(value: int, max_value: int, width: int = 16) -> str:
    """Generate a proportional inline bar using █ characters."""
    if max_value <= 0:
        return ""
    filled = max(1, round(value / max_value * width))
    return "█" * filled


def quality_minibar(high: int, medium: int, low: int) -> str:
    """Generate a quality distribution mini-bar like ██▓▓░."""
    total = high + medium + low
    if total == 0:
        return "—"
    h = max(1, round(high / total * 10)) if high else 0
    m = max(1, round(medium / total * 10)) if medium else 0
    lo = max(1, round(low / total * 10)) if low else 0
    # Normalize to 10 chars
    chars = h + m + lo
    if chars > 10:
        # Trim proportionally
        ratio = 10 / chars
        h = max(1, round(h * ratio)) if high else 0
        m = max(1, round(m * ratio)) if medium else 0
        lo = 10 - h - m
    pct = round(high / total * 100) if total else 0
    return "█" * h + "▓" * m + "░" * lo + f" {pct}% high"


# ──────────────────────────────────────────────────────────────────────
# Color interpolation (for gradient bar)
# ──────────────────────────────────────────────────────────────────────

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert #RRGGBB to (r, g, b)."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert (r, g, b) to #RRGGBB."""
    return f"#{r:02x}{g:02x}{b:02x}"


def _rgb_to_hsl(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Convert RGB (0-255) to HSL (h: 0-360, s: 0-1, l: 0-1)."""
    r1, g1, b1 = r / 255, g / 255, b / 255
    mx, mn = max(r1, g1, b1), min(r1, g1, b1)
    l = (mx + mn) / 2

    if mx == mn:
        h = s = 0.0
    else:
        d = mx - mn
        s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
        if mx == r1:
            h = ((g1 - b1) / d + (6 if g1 < b1 else 0)) * 60
        elif mx == g1:
            h = ((b1 - r1) / d + 2) * 60
        else:
            h = ((r1 - g1) / d + 4) * 60

    return h, s, l


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    """Convert HSL to RGB (0-255)."""
    if s == 0:
        v = int(round(l * 255))
        return v, v, v

    def hue_to_rgb(p: float, q: float, t: float) -> float:
        if t < 0:
            t += 1
        if t > 1:
            t -= 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    h_norm = h / 360

    return (
        int(round(hue_to_rgb(p, q, h_norm + 1 / 3) * 255)),
        int(round(hue_to_rgb(p, q, h_norm) * 255)),
        int(round(hue_to_rgb(p, q, h_norm - 1 / 3) * 255)),
    )


def interpolate_color(color_a: str, color_b: str, t: float) -> str:
    """Interpolate between two hex colors via HSL. t in [0, 1]."""
    t = max(0.0, min(1.0, t))
    h1, s1, l1 = _rgb_to_hsl(*_hex_to_rgb(color_a))
    h2, s2, l2 = _rgb_to_hsl(*_hex_to_rgb(color_b))

    # Shortest path on hue circle
    dh = h2 - h1
    if abs(dh) > 180:
        if dh > 0:
            h1 += 360
        else:
            h2 += 360

    h = (h1 + (h2 - h1) * t) % 360
    s = s1 + (s2 - s1) * t
    l = l1 + (l2 - l1) * t

    return _rgb_to_hex(*_hsl_to_rgb(h, s, l))


# ──────────────────────────────────────────────────────────────────────
# Custom ProgressColumn: Gradient Bar
# ──────────────────────────────────────────────────────────────────────

class GradientBarColumn(ProgressColumn):
    """A progress bar that shifts color from theme.accent → theme.success."""

    def __init__(self, bar_width: int = 25) -> None:
        super().__init__()
        self.bar_width = bar_width

    def render(self, task: Task) -> RenderableType:
        """Render a gradient-colored bar."""
        t = get_theme()
        if task.total is None or task.total == 0:
            # Indeterminate — pulse animation
            frame = int(time.time() * 4) % (self.bar_width * 2)
            chars = list("░" * self.bar_width)
            pulse_pos = frame if frame < self.bar_width else self.bar_width * 2 - frame - 1
            for offset in range(-2, 3):
                idx = pulse_pos + offset
                if 0 <= idx < self.bar_width:
                    chars[idx] = "█" if offset == 0 else "▓" if abs(offset) == 1 else "▒"
            return Text("".join(chars), style=Style(color=t.accent))

        pct = min(task.percentage / 100, 1.0) if task.percentage is not None else 0.0
        filled = int(pct * self.bar_width)
        empty = self.bar_width - filled

        bar_color = interpolate_color(t.accent, t.success, pct)
        filled_text = Text("█" * filled, style=Style(color=bar_color))
        empty_text = Text("░" * empty, style=Style(color=t.dim))
        return Text.assemble(filled_text, empty_text)


# ──────────────────────────────────────────────────────────────────────
# Custom ProgressColumn: Sparkline
# ──────────────────────────────────────────────────────────────────────

SPARK_CHARS = "▁▂▃▄▅▆▇█"


@dataclass
class SparklineState:
    """Tracks throughput samples for sparkline rendering."""

    samples: deque[float] = field(default_factory=lambda: deque(maxlen=10))
    last_completed: float = 0.0
    last_time: float = 0.0

    def record(self, completed: float) -> None:
        """Record a throughput sample."""
        now = time.time()
        if self.last_time > 0:
            dt = now - self.last_time
            if dt > 0.1:  # Avoid division by near-zero
                rate = (completed - self.last_completed) / dt
                self.samples.append(max(0.0, rate))
                self.last_completed = completed
                self.last_time = now
        else:
            self.last_completed = completed
            self.last_time = now

    def render(self) -> str:
        """Render sparkline from samples."""
        if len(self.samples) < 2:
            return ""
        mx = max(self.samples) if self.samples else 1.0
        if mx <= 0:
            return "▁" * len(self.samples)
        result = []
        for s in self.samples:
            idx = min(int(s / mx * (len(SPARK_CHARS) - 1)), len(SPARK_CHARS) - 1)
            result.append(SPARK_CHARS[idx])
        return "".join(result)

    @property
    def throughput(self) -> float:
        """Current throughput (avg of last 3 samples)."""
        if not self.samples:
            return 0.0
        recent = list(self.samples)[-3:]
        return sum(recent) / len(recent)


class SparklineColumn(ProgressColumn):
    """Renders a throughput sparkline next to the progress bar."""

    def __init__(self, sparkline_state: SparklineState | None = None) -> None:
        super().__init__()
        self.state = sparkline_state or SparklineState()

    def render(self, task: Task) -> RenderableType:
        """Render sparkline."""
        t = get_theme()
        self.state.record(task.completed or 0)
        spark = self.state.render()
        if not spark:
            return Text("")
        return Text(f" {spark}", style=Style(color=t.dim))


# ──────────────────────────────────────────────────────────────────────
# Elapsed time formatter
# ──────────────────────────────────────────────────────────────────────

def format_elapsed(seconds: float) -> str:
    """Format elapsed time: '3s', '1m 12s', '2h 5m'."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"
