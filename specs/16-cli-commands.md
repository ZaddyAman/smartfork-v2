# SmartFork v2 — CLI Commands (Layer 12)

> **Design:** All CLI commands defined via Typer. 
> **Entry point:** `smartfork` (installed via `pip install smartfork` or single binary)

---

## Command List

| Command | Short | Description |
|---------|-------|-------------|
| `setup` | — | Setup wizard (first-run or reconfigure) |
| `index` | — | Full index of all enabled agents' sessions |
| `search` | `s` | Search indexed sessions (deterministic) |
| `detect-fork` | `df` | Agentic search for relevant sessions |
| `fork` | `f` | Generate /fork.md from a session |
| `status` | `st` | Show index statistics |
| `vault` | — | Generate Obsidian vault |
| `config` | `c` | Get/set/list config values |
| `theme` | `t` | Switch or list themes |
| `watch` | — | Watch for new sessions (incremental index) |
| `mcp` | — | MCP server management |
| `shell` | — | Launch interactive TUI |

---

## Command Specifications

### `smartfork setup`

Interactive setup wizard (TUI or CLI fallback).

```
smartfork setup           # Full wizard
smartfork setup --quick   # Quick setup with defaults
smartfork setup --reset   # Reset and reconfigure
```

**Wizard steps:**
1. Detect installed coding agents
2. Configure session paths per agent
3. Check Ollama, offer cloud API keys
4. Select theme
5. Ready confirmation

---

### `smartfork index`

Index all sessions from enabled agents.

```
smartfork index                    # Full index, all agents
smartfork index --agent kilocode   # Index specific agent only
smartfork index --force            # Force full re-index
smartfork index --no-intelligence  # Skip LLM enrichment
```

**Output:** Progress bar (TUI) or Rich progress (CLI) showing:
- Sessions scanned
- Chunks embedded
- Errors encountered
- Completion summary

---

### `smartfork search`

Deterministic search (free, fast, default).

```
smartfork search "JWT race condition"
smartfork search "JWT race condition" --n 10
smartfork search "JWT race condition" --project BharatLawAI
smartfork search "JWT race condition" --quality solution_found
smartfork search "JWT race condition" --days 30
smartfork search "JWT race condition" --json
smartfork search "JWT race condition" --no-tui
```

**Flags:**
- `--n, --results INT` — Number of results (default 10)
- `--project TEXT` — Filter by project
- `--quality TEXT` — Filter by quality tag
- `--days INT` — Limit to last N days
- `--json` — Output as JSON
- `--no-tui` — Use CLI output instead of TUI

---

### `smartfork detect-fork`

Agentic search (LLM-orchestrated, opt-in).

```
smartfork detect-fork "debug JWT race condition"
smartfork detect-fork "debug JWT race condition" --cloud  # Use cloud LLM
smartfork detect-fork "debug JWT race condition" --n 5
smartfork detect-fork "debug JWT race condition" --json
```

**Same flags as `search`** plus:
- `--cloud` — Use cloud LLM (Anthropic/OpenAI) instead of local Ollama

---

### `smartfork fork`

Generate /fork.md from a session.

```
smartfork fork <session_id>
smartfork fork <session_id> --intent continue   (default)
smartfork fork <session_id> --intent reference
smartfork fork <session_id> --intent debug
smartfork fork <session_id> --intent synthesize
smartfork fork <session_id> --output ./my-fork.md
smartfork fork <session_id> --clipboard
smartfork fork <session_id> --no-llm
```

**Flags:**
- `--intent TEXT` — continue | reference | debug | synthesize (default: continue)
- `--output PATH` — Save to custom path
- `--clipboard` — Copy to system clipboard
- `--no-llm` — Use raw fallback (no LLM distillation)
- `--max-tokens INT` — Token budget (default: 2000)

---

### `smartfork status`

Show index statistics.

```
smartfork status
smartfork status --json
```

**Output:**
- Total sessions indexed
- Sessions per agent
- Sessions per project
- Quality breakdown (solution_found / dead_end / partial / reference / unknown)
- Last indexed timestamp
- Database size
- Embedding model info

---

### `smartfork vault`

Generate Obsidian knowledge vault.

```
smartfork vault
smartfork vault --output ./my-vault
smartfork vault --project-folders
smartfork vault --json  # Output metadata as JSON
```

**Flags:**
- `--output PATH` — Output directory (default: `./smartfork-vault`)
- `--project-folders` — Generate per-project MOC pages
- `--json` — Output vault metadata as JSON

---

### `smartfork config`

Manage configuration.

```
smartfork config get theme
smartfork config set theme ember
smartfork config list
smartfork config path         # Show config file location
smartfork config reset        # Reset to defaults
```

**Subcommands:**
- `get KEY` — Get config value
- `set KEY VALUE` — Set config value
- `list` — List all config values
- `path` — Show config.toml path
- `reset` — Reset to defaults (with confirmation)

---

### `smartfork theme`

Switch or list themes.

```
smartfork theme              # Show current theme
smartfork theme list
smartfork theme set ember
```

---

### `smartfork watch`

Watch for new sessions and incrementally index.

```
smartfork watch
smartfork watch --agent kilocode
```

Runs until Ctrl+C. Uses filesystem watcher (watchdog). New sessions auto-indexed.

---

### `smartfork mcp`

MCP server management.

```
smartfork mcp install       # Configure Claude Code MCP
smartfork mcp serve         # Start MCP server
smartfork mcp status        # Check MCP status
smartfork mcp uninstall     # Remove MCP config
```

---

### `smartfork shell`

Launch interactive Textual TUI.

```
smartfork shell
smartfork shell --no-tui   # CLI interactive mode (Rich)
```

---

## Global Flags

| Flag | Description |
|------|-------------|
| `--no-tui` | Disable Textual TUI, use Rich CLI output |
| `--verbose, -v` | Verbose output (DEBUG log level) |
| `--lite, -l` | Lite mode (reduced animations, CPU usage) |
| `--help` | Show help |

---

## Entry Point

**File:** `src/smartfork/__main__.py`

```python
from smartfork.cli.commands import app

if __name__ == "__main__":
    app()
```

**File:** `pyproject.toml`

```toml
[project.scripts]
smartfork = "smartfork.cli.commands:app"
```

---

## Testing

- Test each command with valid inputs
- Test each command with invalid inputs (error handling)
- Test --json flag produces valid JSON
- Test --no-tui fallback
- Test help text is complete
