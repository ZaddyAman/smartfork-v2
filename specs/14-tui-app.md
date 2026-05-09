# SmartFork v2 — Textual TUI (Layer 10)

> **Design:** Premium terminal interface using Textual framework.
> **Inspiration:** Claude Code (Ink/React), Amp (custom TUI), opencode (markdown output).
> **Framework:** Textual (Python) — CSS layouts, widgets, keyboard handling, mouse support.

---

## Architecture

```
Textual App
├── MainScreen (default — command input + results)
├── SearchScreen (search results with expandable cards)
├── ForkScreen (fork preview + intent selection)
├── StatusScreen (index stats, database info)
├── SetupWizardScreen (first-run configuration)
├── CommandPalette (Ctrl+O overlay)
└── Footer (keyboard shortcuts, mode badge)
```

---

## MainScreen

**File:** `src/smartfork/tui/screens/main.py`

```
┌─ SmartFork v2 ─────────────────── Sessions: 1,247 │ Obsidian ─┐
│                                                                  │
│  ▸ _                                                             │  ← Command input
│                                                                  │
│  ┌─ Recent Results ──────────────────────────────────────────┐  │
│  │  No search yet. Type a query above or press Ctrl+O for     │  │
│  │  commands.                                                  │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
├─ Ctrl+O: Commands │ F1: Help │ Ctrl+Q: Quit │ 🔍 Deterministic ─┤
└──────────────────────────────────────────────────────────────────┘
```

---

## SearchScreen

**File:** `src/smartfork/tui/screens/search.py`

```
┌─ SmartFork v2 ─────────────────── 🔍 Agentic │ Obsidian ────────┐
│  ▸ fix JWT race condition refresh tokens                         │
│                                                                  │
│  ┌─ ★ 1. Session #1a84 [0.96] ─ Fixing race condition ─────┐  │
│  │  🔄 Fixes earlier attempt │ ✓ Solution Found              │  │
│  │  ▸ 3 weeks ago (47 min) │ 📁 auth.py, middleware.py +3   │  │
│  │  This specifically debugs concurrent token refresh...    │  │
│  │  [Enter: Fork] [→: Expand] [Ctrl+F: Fork with intent]   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─ 2. Session #7c2d [0.82] ─ JWT refresh implementation ──┐  │
│  │  1 month ago (32 min) │ 📁 auth.py, models.py             │  │
│  │  Contains the base implementation that #1a84 was fixing. │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
├─ Ctrl+O: Commands │ 1-5: Fork │ Ctrl+R: Refine │ Ctrl+Q: Quit ─┤
└──────────────────────────────────────────────────────────────────┘
```

---

## ForkScreen

**File:** `src/smartfork/tui/screens/fork.py`

Shows fork preview with intent selector:

```
┌─ Fork Preview ──────────────────────────────────────────────────┐
│  Session: Fixing race condition in auth flow (#1a84)             │
│                                                                  │
│  Intent: [CONTINUE] [REFERENCE] [DEBUG]                          │
│                                                                  │
│  ┌─ Context Report Preview ─────────────────────────────────┐  │
│  │  ## Summary                                                │  │
│  │  Debugged JWT race condition causing 401 errors on...     │  │
│  │                                                            │  │
│  │  ## Key Files                                              │  │
│  │  - auth.py (23 edits)                                      │  │
│  │  - middleware.py (12 edits)                                │  │
│  │                                                            │  │
│  │  ## Gotchas                                                │  │
│  │  - Don't call refresh_token() inside middleware            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  [Enter: Generate /fork.md] [Ctrl+C: Copy to clipboard]          │
│  [Ctrl+S: Save to file] [Esc: Back]                              │
└──────────────────────────────────────────────────────────────────┘
```

---

## CommandPalette

**File:** `src/smartfork/tui/widgets/command_palette.py`

```
┌─ Command Palette ───────────────────────────────────────────────┐
│  ▸ fork                                                          │
│                                                                  │
│  fork          Generate /fork.md from a session                  │
│  detect-fork   Find relevant sessions to fork from               │
│  index         Index all sessions                                │
│  search        Search indexed sessions                           │
│  status        Show index status                                 │
│  vault         Generate Obsidian vault                           │
│  config        Manage configuration                              │
│  theme         Switch color theme                                │
│  setup         Run setup wizard                                  │
│  help          Show help                                         │
│  quit          Exit SmartFork                                    │
└──────────────────────────────────────────────────────────────────┘
```

Keyboard: `Ctrl+O` opens, type to fuzzy-filter, `Enter` to select, `Esc` to close.

---

## SetupWizardScreen

**File:** `src/smartfork/tui/screens/setup.py`

```
┌─ SmartFork Setup Wizard ────────────────────────────────────────┐
│                                                                  │
│  Step 1 of 5: Detect Coding Agents                               │
│                                                                  │
│  ✓ Kilo Code found (127 sessions)                                │
│  ✓ Claude Code found (43 sessions)                               │
│  ○ OpenCode not found                                            │
│  ○ Cursor Agent not found                                        │
│                                                                  │
│  [Enter: Continue] [Space: Toggle] [Esc: Skip]                  │
└──────────────────────────────────────────────────────────────────┘
```

**5 wizard steps:**
1. **Detect agents** — auto-detect installed coding tools
2. **Configure paths** — confirm or customize session paths
3. **LLM setup** — check Ollama, offer cloud API key option
4. **Theme** — pick color theme
5. **Ready** — confirmation + "Run smartfork index to begin"

---

## Themes

**File:** `src/smartfork/tui/themes/`

6 themes as Textual CSS files:

| Theme | Mood | Primary color |
|-------|------|--------------|
| phosphor | Classic CRT green hacker aesthetic | #4ADE80 |
| obsidian | Cold steel blue-grey (default) | #64748B |
| ember | Warm amber, distinctive | #D97706 |
| arctic | Ice-cold blue, clinical | #38BDF8 |
| iron | Muted violet, depth | #6D6494 |
| tungsten | Pure greyscale, zero distraction | #737373 |

```css
/* obsidian.tcss */
Screen {
    background: #0F172A;
    color: #CBD5E1;
}

Header {
    background: #1E293B;
    color: #CBD5E1;
    dock: top;
    height: 1;
}

Footer {
    background: #1E293B;
    color: #64748B;
    dock: bottom;
    height: 1;
}

Input {
    border: solid #334155;
}
```

---

## Widgets

| Widget | File | Purpose |
|--------|------|---------|
| `ResultCard` | `widgets/result_card.py` | Expandable search result card |
| `CommandPalette` | `widgets/command_palette.py` | Fuzzy command search overlay |
| `ProgressBar` | `widgets/progress_bar.py` | Animated indexing progress |
| `ThemeSwitcher` | `widgets/theme_switcher.py` | Quick theme toggle |
| `ShortcutBar` | `widgets/shortcut_bar.py` | Context-aware keyboard hints |
| `StatusBadge` | `widgets/status_badge.py` | Quality tag, mode, supersession badges |

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+O` | Command palette |
| `Ctrl+F` / `/` | Start search / fork |
| `F1` | Help |
| `Ctrl+Q` | Quit |
| `Esc` | Back / close overlay |
| `Tab` / `Shift+Tab` | Navigate focus |
| `↑` / `↓` | Navigate list |
| `Enter` | Select / confirm |
| `Space` | Toggle checkboxes |
| `1-9` | Quick fork (select result N) |
| `Ctrl+S` | Save fork to file |
| `Ctrl+C` | Copy fork to clipboard |
| `Ctrl+T` | Switch theme |

---

## Fallback: CLI Mode

When Textual is not installed or `--no-tui` flag is used:
- Fall back to Rich-based CLI output (panels, tables, text)
- Same functionality, no fullscreen GUI
- `smartfork --no-tui search "query"`

---

## Testing

- Test all screens render without error
- Test command palette filtering
- Test keyboard navigation through results
- Test theme switching at runtime
- Test setup wizard flow end-to-end
- Test Textual not installed → CLI fallback
