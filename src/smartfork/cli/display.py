"""Rich Live display for the SmartFork indexing pipeline.

A premium stepper layout with gradient bars, sparkline throughput,
live stats ticker, and per-agent sub-status.
"""

import time
from typing import Any

from rich import box
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
)
from rich.rule import Rule
from rich.text import Text

from smartfork.cli.theme import (
    GradientBarColumn,
    SparklineColumn,
    SparklineState,
    format_elapsed,
    get_theme,
    quality_minibar,
)
from smartfork.models.progress import ProgressEvent


class IndexDisplay:
    """Rich Live display for the index pipeline.

    A premium stepper with gradient bar, sparkline throughput,
    live stats, and phase transitions.
    """

    def __init__(self, console: Console) -> None:
        self.console = console
        self._start_time = time.time()

        # Phase state
        self._phase = "scanning"
        self._scan_done = False
        self._parse_done = False
        self._index_done = False

        # Scan data
        self._scan_agents_data: dict[str, dict[str, Any]] = {}
        self._scan_active_path = ""

        # Parse data
        self._parse_current = 0
        self._parse_total = 0
        self._parse_active_agent = ""
        self._start_parse_time = 0.0
        self._parse_time = 0.0

        # Index data
        self._index_current = 0
        self._index_total = 0
        self._index_active_agent = ""
        self._index_subtext = ""

        # Live stats
        self._total_chunks = 0
        self._total_errors = 0
        self._total_stored = 0

        # Sparkline state (shared across phases)
        self._sparkline = SparklineState()

        # Phase transition flash (timestamp of last phase completion)
        self._transition_time = 0.0

        # Build per-phase progress instances
        self._scan_progress = Progress(
            SpinnerColumn("dots", style=get_theme().accent),
            TextColumn("[bold white]{task.description:<18}"),
            console=None,
        )
        self._scan_task = self._scan_progress.add_task("Scanning agents", total=None)

        self._parse_progress = Progress(
            SpinnerColumn("dots", style=get_theme().accent),
            TextColumn("[bold white]{task.description:<18}"),
            GradientBarColumn(bar_width=25),
            MofNCompleteColumn(),
            SparklineColumn(self._sparkline),
            console=None,
        )
        self._parse_task = self._parse_progress.add_task("Parsing sessions", total=1)

        self._index_progress = Progress(
            SpinnerColumn("dots", style=get_theme().accent),
            TextColumn("[bold white]{task.description:<18}"),
            GradientBarColumn(bar_width=25),
            MofNCompleteColumn(),
            SparklineColumn(self._sparkline),
            console=None,
        )
        self._index_task = self._index_progress.add_task("Indexing sessions", total=1)

        self._live = Live(
            self._build_renderable(),
            console=console,
            refresh_per_second=12,
            screen=False,
        )

    def __enter__(self) -> "IndexDisplay":
        self._live.__enter__()
        return self

    def __exit__(self, *args: Any) -> None:
        self._live.__exit__(*args)

    def update(self, event: ProgressEvent) -> None:
        """Process a ProgressEvent and refresh the display."""
        # Detect phase transitions
        if event.phase in ("parsing", "indexing", "embedding", "enriching") and not self._scan_done:
            self._scan_done = True
            self._transition_time = time.time()
            self._start_parse_time = time.time()

        if event.phase in ("indexing", "embedding", "enriching") and not self._parse_done:
            self._parse_done = True
            self._transition_time = time.time()
            self._parse_time = time.time() - (self._start_parse_time or time.time())
            # Reset sparkline for index phase
            self._sparkline = SparklineState()

        self._phase = event.phase

        if event.scan_status == "done":
            self._scan_done = True
            if not self._start_parse_time:
                self._start_parse_time = time.time()

        # Update live stats from event
        stats = event.stats or {}
        self._total_chunks = stats.get("chunked", self._total_chunks)
        self._total_stored = stats.get("stored", self._total_stored)
        self._total_errors = stats.get("errors", self._total_errors)

        # Phase-specific updates
        if self._phase == "scanning":
            if event.agent_id:
                self._scan_agents_data[event.agent_id] = {
                    "count": event.scan_count,
                    "status": event.scan_status,
                }
            self._scan_active_path = event.scan_path

        elif self._phase == "parsing":
            self._parse_current = event.current
            self._parse_total = event.total
            if event.agent_id:
                self._parse_active_agent = event.agent_id

            self._parse_progress.update(
                self._parse_task,
                completed=self._parse_current,
                total=self._parse_total or 1,
            )

        elif self._phase in ("indexing", "embedding", "enriching"):
            self._index_current = event.session_current
            self._index_total = event.session_total
            if event.agent_id:
                self._index_active_agent = event.agent_id

            if event.phase == "embedding":
                if event.embed_total > 0:
                    self._index_subtext = (
                        f"embedding chunk {event.embed_current}/{event.embed_total}"
                    )
                else:
                    self._index_subtext = "embedding chunks..."
            elif event.phase == "enriching":
                if event.enrich_step and event.enrich_step != "done":
                    self._index_subtext = f"generating {event.enrich_step}..."
            else:
                self._index_subtext = "processing..."

            self._index_progress.update(
                self._index_task,
                completed=self._index_current,
                total=self._index_total or 1,
            )

        self._live.update(self._build_renderable())

    def finish(self) -> None:
        """Mark all phases as complete."""
        if not self._scan_done:
            self._scan_done = True
        if not self._parse_done:
            self._parse_done = True
            self._parse_time = time.time() - (self._start_parse_time or time.time())
        self._index_done = True
        self._live.update(self._build_renderable())

    def _build_renderable(self) -> RenderableType:
        """Build the full panel renderable."""
        t = get_theme()
        lines: list[RenderableType] = []

        # ── 1. Scan Step ──
        if self._scan_done:
            total_sessions = sum(d.get("count", 0) for d in self._scan_agents_data.values())
            agent_count = len(self._scan_agents_data)
            # Check for transition flash
            flash = self._is_flashing()
            marker = f"[{t.accent}]◉[/{t.accent}]" if flash else f"[{t.success}]✓[/{t.success}]"
            lines.append(
                Text.from_markup(
                    f"  {marker} Scanned [bold]{total_sessions}[/bold] "
                    f"sessions across [bold]{agent_count}[/bold] agents"
                )
            )
        elif self._phase == "scanning":
            lines.append(self._scan_progress)
            # Find running agent or fall back to active path
            active_agent = next(
                (k for k, v in self._scan_agents_data.items() if v.get("status") == "running"), 
                None
            )
            
            if active_agent:
                lines.append(
                    Text.from_markup(f"    [{t.dim}]╰── {active_agent} · scanning...[/{t.dim}]")
                )
            elif self._scan_active_path:
                path = self._scan_active_path
                if len(path) > 40:
                    path = "..." + path[-37:]
                lines.append(Text.from_markup(f"    [{t.dim}]╰── {path}[/{t.dim}]"))

        # ── 2. Parse Step ──
        if self._parse_done:
            flash = self._is_flashing()
            marker = f"[{t.accent}]◉[/{t.accent}]" if flash else f"[{t.success}]✓[/{t.success}]"
            lines.append(
                Text.from_markup(
                    f"  {marker} Parsed [bold]{self._parse_total}[/bold] "
                    f"sessions in [bold]{self._parse_time:.1f}s[/bold]"
                )
            )
        elif self._phase == "parsing":
            lines.append(self._parse_progress)
            if self._parse_active_agent:
                lines.append(
                    Text.from_markup(
                        f"    [{t.dim}]╰── {self._parse_active_agent} · "
                        f"processing session...[/{t.dim}]"
                    )
                )

        # ── 3. Index Step ──
        if self._index_done:
            total_time = time.time() - self._start_time
            lines.append(
                Text.from_markup(
                    f"  [{t.success}]✓[/{t.success}] Indexed [bold]{self._index_total}[/bold] "
                    f"sessions · [bold]{self._total_chunks}[/bold] chunks · "
                    f"[bold]{self._total_errors}[/bold] errors"
                )
            )
        elif self._phase in ("indexing", "embedding", "enriching"):
            lines.append(self._index_progress)
            agent = self._index_active_agent or "system"
            subtext = self._index_subtext or "processing..."
            lines.append(
                Text.from_markup(
                    f"    [{t.dim}]╰── {agent} · {subtext}[/{t.dim}]"
                )
            )

            # Live stats row (only during indexing)
            if self._total_chunks > 0 or self._total_errors > 0:
                lines.append(Text(""))
                lines.append(Rule(style=t.dim, characters="┄"))
                stats_parts = [
                    f"sessions: {self._index_current}",
                    f"chunks: {self._total_chunks}",
                    f"errors: {self._total_errors}",
                ]
                stats_line = "  ".join(stats_parts)
                lines.append(
                    Text.from_markup(f"  [{t.dim}]{stats_line}[/{t.dim}]")
                )

        # Build panel
        elapsed = time.time() - self._start_time
        elapsed_str = format_elapsed(elapsed)

        # Panel subtitle with live ticker
        subtitle_parts = [elapsed_str]
        if self._total_chunks > 0:
            subtitle_parts.append(f"{self._total_chunks} chunks")
        throughput = self._sparkline.throughput
        if throughput > 0:
            subtitle_parts.append(f"{throughput:.1f}/s")

        subtitle = " · ".join(subtitle_parts)

        panel_width = min(self.console.width, 80) if self.console.width else 70

        content = Group(*lines)
        return Panel(
            content,
            title=f"[bold]SmartFork[/bold] · [{t.accent}]Index[/{t.accent}]",
            title_align="left",
            subtitle=f"[{t.dim}]{subtitle}[/{t.dim}]",
            subtitle_align="right",
            border_style=t.dim,
            box=box.ROUNDED,
            width=panel_width,
            padding=(1, 2),
        )

    def _is_flashing(self) -> bool:
        """Check if we're in the brief transition flash window (~300ms)."""
        if self._transition_time <= 0:
            return False
        return (time.time() - self._transition_time) < 0.3
