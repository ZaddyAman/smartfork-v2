# SmartFork v2 — CLI UI Redesign (Layer 12.1)

> **Status:** `ready-for-agent`  
> **Supersedes:** Parts of `14-tui-app.md` (TUI is deprecated), updates `16-cli-commands.md`  
> **Spec version:** 1.0  
> **Date:** 2026-05-16

---

## Problem Statement

SmartFork's CLI has three competing UI paradigms: Typer commands with ad-hoc Rich formatting, a Rich Live stepper for indexing, and a Textual TUI that is broken and unmaintained. The result is:

1. **No brand identity** — the `--help` output is stock Typer with no grouping, no visual hierarchy, and a generic tagline.
2. **Inconsistent output** — each command formats output differently (some use tables, some raw prints, some badges). Colors are sprinkled ad-hoc with no design system.
3. **Dead code** — the Textual TUI (`tui/` directory) has broken imports, wrong API calls (`ForkAssembler.assemble()` called with wrong args), empty widget stubs, and 6 theme files that serve nothing. The `watch` command constructs a `FullIndexer()` with no arguments and crashes. The `detect-fork` command is a worse duplicate of `search`.
4. **Minimal progress feedback** — `smartfork index` (incremental, the most common path) shows zero visual feedback. The stepper for `--full` is functional but visually basic: flat-color bar, no elapsed time, no throughput metrics.
5. **Unnecessary dependencies** — `textual` and `watchdog` are heavy packages that serve dead code.

Users running SmartFork for the first time see a tool that looks unfinished and inconsistent.

---

## Solution

Remove all dead code (Textual TUI, broken commands), invest fully in the Typer + Rich CLI surface, and create a cohesive visual design system with:

- **Branded `--help`** with command grouping (Core / System / Integrations)
- **Theme-aware output helpers** — every command uses the same `header()`, `success()`, `error()`, `kv_table()` functions that read from a switchable palette
- **Enhanced index progress** — gradient bar, throughput sparkline, live stats ticker, per-agent sub-status
- **Richer search/status output** — card-style results with excerpts, visual dashboard with inline bar charts
- **6 CLI color palettes** switchable via `smartfork theme` (obsidian default)

---

## User Stories

1. As a developer, I want `smartfork --help` to show grouped commands (Core, System, Integrations) so that I can quickly find the command I need.
2. As a developer, I want a branded header line in `--help` output so that SmartFork feels like a premium tool, not a generic CLI.
3. As a developer, I want `smartfork index` (incremental) to show the same progress stepper as `--full` so I can see what's happening during indexing.
4. As a developer, I want the index progress bar to shift color as it fills (gradient) so the UI feels alive and polished.
5. As a developer, I want to see elapsed time in the index progress panel so I know how long the process has been running.
6. As a developer, I want to see throughput (items/second) and a sparkline in the index panel so I can gauge performance.
7. As a developer, I want live stats (sessions, chunks, errors) at the bottom of the index panel so I don't have to wait for completion to see counts.
8. As a developer, I want per-agent sub-status during scanning so I can see which agent is being processed and how many sessions it found.
9. As a developer, I want completed index phases to collapse into single summary lines so the display stays clean.
10. As a developer, I want `smartfork search` results to show excerpts and tags alongside title and match score so I can assess relevance without opening each session.
11. As a developer, I want a `-n` flag on `smartfork search` so I can control how many results I see (replacing the redundant `detect-fork` command).
12. As a developer, I want `smartfork status` to show inline bar charts for distribution (by project, by agent, by quality) so I can visually understand my index composition.
13. As a developer, I want every error message to include actionable fix commands so I'm never stuck.
14. As a developer, I want to switch between 6 color palettes (obsidian, phosphor, ember, arctic, iron, tungsten) so I can match my terminal aesthetic.
15. As a developer, I want `smartfork theme list` to show a one-line description of each palette's vibe so I can choose without trial-and-error.
16. As a developer, I want consistent Unicode symbols (✓ ✗ ▲ ›) across all commands instead of mixed brackets/emojis so the output feels cohesive.
17. As a developer, I want phase transitions in the index stepper to have a brief visual flash (●→◉→✓) so state changes feel intentional, not jarring.
18. As a developer, I want the progress panel width to be responsive (`min(console.width, 80)`) so it doesn't break in narrow terminals or waste space in wide ones.
19. As a developer, I want `smartfork setup` to use the same themed output helpers so setup looks consistent with every other command.
20. As a developer, I want `smartfork config list` to use the same table styling as `status` so the visual language is uniform.
21. As a developer, I want `smartfork fork` output to use branded headers and success/error helpers so it matches the rest of the CLI.
22. As a developer, I want the tool to not require `textual` or `watchdog` as dependencies since nothing uses them, reducing install size and potential conflicts.

---

## Implementation Decisions

### Modules to build/modify

#### 1. `cli/theme.py` — NEW (deep module)

The design system core. Encapsulates all visual concerns behind a simple interface.

**Responsibilities:**
- Define `CLITheme` dataclass with color tokens: `accent`, `success`, `warning`, `error`, `dim`, `heading`, `muted`
- Define 6 named palettes as `CLITheme` instances (obsidian, phosphor, ember, arctic, iron, tungsten)
- `get_theme() -> CLITheme` reads the active palette from config
- Output helper functions: `header(cmd_name)`, `success(msg)`, `warn(msg)`, `error(msg)`, `info(msg)`, `kv_table(title, rows)`, `results_table(title, columns, rows)`
- Custom `ProgressColumn` subclasses: `GradientBarColumn`, `SparklineColumn`, `PhaseIndicatorColumn`
- Color interpolation utility for gradient bar

**Key design decision:** The helpers call `get_theme()` internally. Commands never touch colors directly — they call `theme.success("Indexing complete")` and the right palette is applied.

**Palette definitions (token sets):**

| Palette | Accent | Success | Warning | Error | Dim |
|---------|--------|---------|---------|-------|-----|
| obsidian | `#7c3aed` | `#a3e635` | `#fbbf24` | `#f87171` | `#6b7280` |
| phosphor | `#39ff14` | `#39ff14` | `#facc15` | `#ff6b6b` | `#4ade80` |
| ember | `#f97316` | `#a3e635` | `#fbbf24` | `#f87171` | `#a8a29e` |
| arctic | `#38bdf8` | `#34d399` | `#fbbf24` | `#fb7185` | `#94a3b8` |
| iron | `#6d6494` | `#a3e635` | `#fbbf24` | `#f87171` | `#737373` |
| tungsten | `#a3a3a3` | `#a3e635` | `#fbbf24` | `#f87171` | `#737373` |

#### 2. `cli/display.py` — REWRITE (deep module)

The enhanced index stepper. Complete rewrite of the existing 219-line file.

**Key changes:**
- Create a **new `Progress` instance per phase** instead of mutating one task's description/total
- **`GradientBarColumn`**: subclass `ProgressColumn`, interpolates bar color from `theme.accent` to `theme.success` based on completion percentage
- **`SparklineColumn`**: stores last 10 throughput samples in a `deque(maxlen=10)`, renders as block characters
- **Live panel subtitle**: shows `{elapsed} · {chunks} chunks · {throughput}/s`
- **Responsive width**: `min(console.width, 80)`
- **Phase indicator**: braille spinner for indeterminate, filled dot for active, checkmark for complete, brief flash on transition (~200ms)
- **Per-agent sub-status during scan**: show each agent's count as it's discovered
- **Live stats row**: bottom of panel shows `sessions: N  chunks: N  errors: N  quality: bar N% high`
- **Dotted rule separator** between progress and stats using `Rule(style="dim")`

#### 3. `cli/commands.py` — MODIFY

**Remove:**
- `shell` command (entire function + imports)
- `detect_fork` command (entire function)
- `watch` command (entire function + watchdog imports)

**Rewire:**
- `theme` command: change from Textual CSS list to CLI palette list/switch (reads from `cli/theme.py` palette definitions)
- All `console.print(...)` calls replaced with `theme.header()`, `theme.success()`, `theme.error()`, etc.
- `search` command: add `-n` / `--results` flag (default 5), add `rich_help_panel="Core"` to decorator
- All commands: add `rich_help_panel` for grouping (Core / System / Integrations)
- `index` command: both `--full` and incremental paths use `IndexDisplay`
- Callback docstring changed to branded: `SmartFork v0.1.0 — session intelligence for AI coding agents`

**Modify `search` results:** Instead of a bare table, use card-style rows showing rank, title, match score, project, agent, time ago, excerpt, and tags.

**Modify `status` output:** Replace key-value table with visual dashboard using inline bar charts for distribution.

#### 4. `tui/` directory — DELETE entirely

All files removed:
- `tui/__init__.py`, `tui/app.py`
- `tui/screens/__init__.py`, `tui/screens/main.py`
- `tui/widgets/__init__.py`
- `tui/themes/` (all 6 `.tcss` files + `.gitkeep`)

#### 5. `pyproject.toml` — MODIFY

Remove from `dependencies`:
- `textual>=0.50`
- `watchdog>=4.0`

#### 6. `indexer/indexer.py` — MODIFY

Add `progress_callback` parameter to `index_incremental()` so both index paths can use `IndexDisplay`.

#### 7. `models/progress.py` — minor update

May need additional fields for sparkline throughput data and per-agent scan counts.

### Architectural Decisions

- **No new dependencies.** Everything uses Rich core (`ProgressColumn` subclass, `Live`, `Panel`, `Group`, `Rule`, `Text`, `Table`).
- **Theme is a config key**, not a runtime state. `get_config().theme` → `get_theme()` → `CLITheme` dataclass. Same singleton pattern as the rest of the codebase.
- **Helpers are module-level functions**, not methods on a class. Commands call `from smartfork.cli.theme import header, success, error` etc. This is simpler than injecting a theme object.
- **`GradientBarColumn` uses HSL interpolation** between two hex colors. No external color library — the interpolation is ~15 lines of math.
- **Sparkline throughput** is calculated as a rolling window: `items_completed / time_since_last_sample`. Stored in `deque(maxlen=10)`. Each value maps to one of 8 block characters.

---

## Testing Decisions

### What makes a good test here

CLI UI tests should verify **external behavior** — the content and structure of output — not implementation details like which Rich class was used internally. Tests should:
- Capture console output and assert on content (keywords, counts, structure)
- Verify commands exit with correct codes
- Verify error messages include actionable fix commands
- NOT assert on exact ANSI escape codes or pixel-level formatting

### Modules to test

#### `cli/theme.py`
- Each palette returns valid color hex codes
- `get_theme()` returns the correct palette based on config
- `header()`, `success()`, `error()` produce non-empty output
- `GradientBarColumn.render()` returns renderable for 0%, 50%, 100%
- `SparklineColumn.render()` returns correct block characters for known inputs
- Color interpolation edge cases (0.0, 0.5, 1.0)

#### `cli/display.py`
- `IndexDisplay` can be constructed and `__enter__`/`__exit__` without error
- `update()` with scan/parse/index phase events doesn't raise
- `finish()` sets all phases to done
- `_build_renderable()` returns a `Panel`

#### `cli/commands.py`
- `--help` output contains "Core", "System", "Integrations" group names
- `--help` does NOT contain "shell", "detect-fork", "watch"
- `search --results 3` limits output
- `theme list` shows all 6 palette names
- `theme switch obsidian` sets config

### Prior art

Existing tests in `tests/` use `pytest` with fixtures from `conftest.py`. The pattern is:
- Mock heavy dependencies (LLM, embedder, filesystem) via `monkeypatch` or constructor injection
- Test pure functions directly
- Test CLI commands via `typer.testing.CliRunner`

---

## Out of Scope

1. **Textual TUI rewrite** — the TUI is killed, not replaced. If a TUI is wanted in the future, it should be designed from scratch with a new spec.
2. **`watch` command** — killed entirely. Will be re-spec'd when filesystem watching is needed, with proper debounce and concurrent-safe SQLite access.
3. **`detect-fork` command** — absorbed into `search -n 1`. No separate agentic search command surface.
4. **JSON output mode** (`--json` flag) — mentioned in `16-cli-commands.md` spec but not implemented anywhere currently. Not part of this redesign.
5. **Interactive setup wizard** — the `setup` command gets themed output but its interactive flow is unchanged.
6. **MCP command internals** — `mcp serve` has a busy-wait loop (`while server.is_running: pass`). Fixing this is out of scope.
7. **Search/fork functional improvements** — this PRD only covers UI/UX of the CLI output, not the underlying search quality or fork assembly logic.

---

## Further Notes

- The existing `specs/14-tui-app.md` should be marked as **DEPRECATED** in its header. It describes a Textual architecture that will no longer exist.
- The existing `specs/16-cli-commands.md` should be updated post-implementation to reflect the new command surface (no `shell`, no `detect-fork`, no `watch`, `theme` rewired).
- The `ralph/prd.json` user story `US-024` (Implement Textual TUI screens and widgets) should be marked as deprecated — it describes dead architecture.
- The `--no-tui` global flag in `16-cli-commands.md` is no longer needed since there is no TUI. It should be removed.
- The `--lite` global flag should eventually suppress animations (sparklines, gradient bar) and use a simpler progress display. This can be done as a follow-up.
