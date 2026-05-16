# SmartFork v2 — System Test Plan (Layer 20)

> **Purpose:** End-to-end validation of all SmartFork v2 features after Ralph builds the system.
> **Approach:** Black-box testing — run each command, verify output, check edge cases.
> **Prerequisites:** SmartFork v2 installed (`pip install -e .`), at least 1 session indexed.

---

## Test Categories

| Cat | Feature | Test Count |
|-----|---------|------------|
| CLI-01 | `smartfork setup` | 5 |
| CLI-02 | `smartfork index` | 6 |
| CLI-03 | `smartfork search` | 8 |
| CLI-04 | `smartfork detect-fork` | 7 |
| CLI-05 | `smartfork fork` | 8 |
| CLI-06 | `smartfork status` | 4 |
| CLI-07 | `smartfork vault` | 5 |
| CLI-08 | `smartfork config` | 6 |
| CLI-09 | `smartfork theme` | 4 |
| CLI-10 | `smartfork watch` | 3 |
| CLI-11 | `smartfork mcp` | 5 |
| CLI-12 | `smartfork shell` | 3 |
| TUI-01 | MainScreen | 5 |
| TUI-02 | SearchScreen | 6 |
| TUI-03 | ForkScreen | 5 |
| TUI-04 | StatusScreen | 3 |
| TUI-05 | SetupWizardScreen | 4 |
| TUI-06 | CommandPalette | 4 |
| TUI-07 | Themes (6 CSS) | 3 |
| MCP-01 | Tool: detect_fork | 3 |
| MCP-02 | Tool: fork_session | 3 |
| MCP-03 | Tool: index_status | 2 |
| MCP-04 | Tool: search_sessions | 3 |
| MCP-05 | Tool: list_projects | 2 |
| MCP-06 | Tool: vault_export | 2 |
| MCP-07 | Tool: config_get / config_set | 3 |
| MCP-08 | MCP CLI management | 4 |
| EDGE-01 | Graceful degradation | 6 |
| EDGE-02 | Error handling | 5 |
| EDGE-03 | Performance | 3 |
| **Total** | | **119** |

---

## CLI-01: `smartfork setup`

| ID | Test | Command | Expected |
|----|------|---------|----------|
| CLI-01.1 | Full wizard | `smartfork setup` | 5-step interactive wizard, detects agents |
| CLI-01.2 | Quick setup | `smartfork setup --quick` | Skip prompts, use defaults |
| CLI-01.3 | Reset config | `smartfork setup --reset` | Warns, then starts fresh wizard |
| CLI-01.4 | No agents installed | `smartfork setup` (no agents) | Warns "no coding agents detected", allows skip |
| CLI-01.5 | Cancel mid-wizard | Press Ctrl+C during setup | Clean exit, no corrupted config |

---

## CLI-02: `smartfork index`

| ID | Test | Command | Expected |
|----|------|---------|----------|
| CLI-02.1 | Full index | `smartfork index` | Progress bar, summary with session/chunk/error counts |
| CLI-02.2 | Agent filter | `smartfork index --agent kilocode` | Only kilocode sessions indexed |
| CLI-02.3 | Force re-index | `smartfork index --force` | Re-indexes all sessions (not just new) |
| CLI-02.4 | No intelligence | `smartfork index --no-intelligence` | Skips LLM enrichment, index still works |
| CLI-02.5 | Empty database | `smartfork index` after reset | Clean index, 0 sessions |
| CLI-02.6 | Corrupt session | Include corrupt .json in adapter dir | Skips bad session, logs warning, continues |

---

## CLI-03: `smartfork search`

| ID | Test | Command | Expected |
|----|------|---------|----------|
| CLI-03.1 | Basic search | `smartfork search "JWT race condition"` | Returns ranked ResultCards |
| CLI-03.2 | Limit results | `smartfork search "test" --n 3` | Max 3 results |
| CLI-03.3 | Project filter | `smartfork search "test" --project TestApp` | Only TestApp sessions |
| CLI-03.4 | Quality filter | `smartfork search "test" --quality solution_found` | Only SOLUTION_FOUND |
| CLI-03.5 | Recency filter | `smartfork search "test" --days 30` | Sessions from last 30 days |
| CLI-03.6 | JSON output | `smartfork search "test" --json` | Valid JSON array of ResultCards |
| CLI-03.7 | No-TUI mode | `smartfork search "test" --no-tui` | Results in Rich table, not TUI |
| CLI-03.8 | No results | `smartfork search "xyznonexistent123"` | "No sessions found" message, non-zero exit? |

---

## CLI-04: `smartfork detect-fork`

| ID | Test | Command | Expected |
|----|------|---------|----------|
| CLI-04.1 | Basic detect | `smartfork detect-fork "debug JWT"` | Agentic results with relevance explanations |
| CLI-04.2 | Cloud LLM | `smartfork detect-fork "test" --cloud` | Uses cloud provider (if API key set) |
| CLI-04.3 | Limit results | `smartfork detect-fork "test" --n 3` | Max 3 results |
| CLI-04.4 | JSON output | `smartfork detect-fork "test" --json` | Valid JSON with relevance_explanation |
| CLI-04.5 | No Ollama | Stop Ollama, run detect-fork | Falls back to deterministic or clear error |
| CLI-04.6 | No cloud key | `smartfork detect-fork "test" --cloud` (no key) | Clear error about missing API key |
| CLI-04.7 | Empty DB | Run on empty index | "No matching sessions found" gracefully |

---

## CLI-05: `smartfork fork`

| ID | Test | Command | Expected |
|----|------|---------|----------|
| CLI-05.1 | Continue intent | `smartfork fork <id> --intent continue` | Valid /fork.md with ✅/🚧 checklist |
| CLI-05.2 | Reference intent | `smartfork fork <id> --intent reference` | Artifacts section with paths/URLs |
| CLI-05.3 | Debug intent | `smartfork fork <id> --intent debug` | Error + root cause + fix + prevention |
| CLI-05.4 | Synthesize intent | `smartfork fork <id> --intent synthesize` | Overview + timeline + architectural shifts |
| CLI-05.5 | Custom output | `smartfork fork <id> --output ./my-fork.md` | File at custom path |
| CLI-05.6 | Clipboard | `smartfork fork <id> --clipboard` | Content in system clipboard |
| CLI-05.7 | No LLM | `smartfork fork <id> --no-llm` | Raw fallback, same sections, no distillation |
| CLI-05.8 | Invalid session | `smartfork fork invalid-123` | Clear error "session not found" |

---

## CLI-06: `smartfork status`

| ID | Test | Command | Expected |
|----|------|---------|----------|
| CLI-06.1 | Basic status | `smartfork status` | Counts: total, per-agent, per-project, quality, DB size |
| CLI-06.2 | JSON output | `smartfork status --json` | Valid JSON with all fields |
| CLI-06.3 | Empty DB | `smartfork status` (no sessions) | All counts show 0 |
| CLI-06.4 | After indexing | Index → check status | Counts reflect new sessions |

---

## CLI-07: `smartfork vault`

| ID | Test | Command | Expected |
|----|------|---------|----------|
| CLI-07.1 | Generate vault | `smartfork vault` | Creates `./smartfork-vault/` with MOC.md + session notes |
| CLI-07.2 | Custom output | `smartfork vault --output ./my-vault` | Vault at custom path |
| CLI-07.3 | Project folders | `smartfork vault --project-folders` | Per-project MOC pages |
| CLI-07.4 | JSON metadata | `smartfork vault --json` | Valid JSON with vault structure info |
| CLI-07.5 | Empty DB | `smartfork vault` (no sessions) | Empty vault with MOC showing "no sessions" |

---

## CLI-08: `smartfork config`

| ID | Test | Command | Expected |
|----|------|---------|----------|
| CLI-08.1 | Get value | `smartfork config get theme` | Current theme name |
| CLI-08.2 | Set value | `smartfork config set theme ember` | Updates config.toml |
| CLI-08.3 | List all | `smartfork config list` | All config key-value pairs |
| CLI-08.4 | Show path | `smartfork config path` | Path to config.toml |
| CLI-08.5 | Reset | `smartfork config reset` | Prompts confirm, resets to defaults |
| CLI-08.6 | Invalid key | `smartfork config get nonexistent` | Clear error "unknown config key" |

---

## CLI-09: `smartfork theme`

| ID | Test | Command | Expected |
|----|------|---------|----------|
| CLI-09.1 | Current theme | `smartfork theme` | Shows current theme name |
| CLI-09.2 | List themes | `smartfork theme list` | Shows 6 themes: phosphor, obsidian, ember, arctic, iron, tungsten |
| CLI-09.3 | Switch theme | `smartfork theme set ember` | Updates config, confirms |
| CLI-09.4 | Invalid theme | `smartfork theme set invalid` | Error "valid themes: phosphor, obsidian..." |

---

## CLI-10: `smartfork watch`

| ID | Test | Command | Expected |
|----|------|---------|----------|
| CLI-10.1 | Start watching | `smartfork watch` (then create session file) | Detects new session, auto-indexes |
| CLI-10.2 | Agent filter | `smartfork watch --agent kilocode` | Only watches kilocode adapter paths |
| CLI-10.3 | Ctrl+C exit | Press Ctrl+C during watch | Clean exit, "Watch stopped" message |

---

## CLI-11: `smartfork mcp`

| ID | Test | Command | Expected |
|----|------|---------|----------|
| CLI-11.1 | Install | `smartfork mcp install` | Adds SmartFork to Claude Code MCP config |
| CLI-11.2 | Serve | `smartfork mcp serve` | Starts MCP server on stdio |
| CLI-11.3 | Status | `smartfork mcp status` | Shows "running" or "stopped" + port info |
| CLI-11.4 | Uninstall | `smartfork mcp uninstall` | Removes from MCP config, confirms |
| CLI-11.5 | Serve without config | `smartfork mcp serve` (not installed) | Clear error "MCP not installed. Run smartfork mcp install first" |

---

## CLI-12: `smartfork shell`

| ID | Test | Command | Expected |
|----|------|---------|----------|
| CLI-12.1 | Launch TUI | `smartfork shell` | Full Textual TUI with MainScreen |
| CLI-12.2 | No-TUI fallback | `smartfork shell --no-tui` | Rich CLI interactive prompt |
| CLI-12.3 | TUI quit | Press Ctrl+Q in TUI | Clean exit to terminal |

---

## TUI-01: MainScreen

| ID | Test | Action | Expected |
|----|------|--------|----------|
| TUI-01.1 | Load | Launch `smartfork shell` | Command input visible, session count in header |
| TUI-01.2 | Input | Type query, press Enter | Routes to SearchScreen |
| TUI-01.3 | Empty state | First launch, no search yet | "No search yet" placeholder text |
| TUI-01.4 | Footer | Check footer bar | Shows Ctrl+O, F1, Ctrl+Q shortcuts |
| TUI-01.5 | Mode badge | Check header | "🔍 Deterministic" badge visible |

---

## TUI-02: SearchScreen

| ID | Test | Action | Expected |
|----|------|--------|----------|
| TUI-02.1 | Results display | Search "JWT" | Result cards with rank, score, title, date, files |
| TUI-02.2 | Expand card | Press → on a result | Shows full summary + reasoning |
| TUI-02.3 | Fork shortcut | Press Ctrl+F on result | Opens ForkScreen with that session |
| TUI-02.4 | Refine search | Press Ctrl+R | Clears results, new query input |
| TUI-02.5 | No results | Search "xyznonexistent" | "No sessions found" message |
| TUI-02.6 | Agentic badge | Trigger detect-fork | Header shows "🔍 Agentic" badge |

---

## TUI-03: ForkScreen

| ID | Test | Action | Expected |
|----|------|--------|----------|
| TUI-03.1 | Intent selector | Open ForkScreen | 4 intents visible (CONTINUE/REFERENCE/DEBUG/SYNTHESIZE) |
| TUI-03.2 | Preview | Select CONTINUE | Shows /fork.md preview |
| TUI-03.3 | Switch intent | Press Tab to cycle intents | Preview updates for each intent |
| TUI-03.4 | Export | Press Enter to export | Saves to file or clipboard |
| TUI-03.5 | Session info | Check header | Session ID + title shown |

---

## TUI-04: StatusScreen

| ID | Test | Action | Expected |
|----|------|--------|----------|
| TUI-04.1 | Load | Press Ctrl+S or menu | Shows all stats: total, per-agent, per-project, quality breakdown |
| TUI-04.2 | DB size | Check status screen | Database size in MB |
| TUI-04.3 | Zero state | Empty DB | All counts show 0, clear message |

---

## TUI-05: SetupWizardScreen

| ID | Test | Action | Expected |
|----|------|--------|----------|
| TUI-05.1 | First run | Delete config, launch smartfork | Setup wizard auto-launches |
| TUI-05.2 | Step progression | Press Enter through steps | 5 steps: agents → paths → providers → theme → confirm |
| TUI-05.3 | Back navigation | Press Esc at step 3 | Returns to step 2 |
| TUI-05.4 | Completion | Finish wizard | Config saved, launches MainScreen |

---

## TUI-06: CommandPalette

| ID | Test | Action | Expected |
|----|------|--------|----------|
| TUI-06.1 | Open | Press Ctrl+O | Overlay with command list + fuzzy search |
| TUI-06.2 | Fuzzy search | Type "sea" | Filters to Search, Search Agentic |
| TUI-06.3 | Execute | Select command, press Enter | Executes: navigates to screen or runs action |
| TUI-06.4 | Close | Press Esc | Returns to previous screen |

---

## TUI-07: Themes

| ID | Test | Action | Expected |
|----|------|--------|----------|
| TUI-07.1 | Switch via command | `smartfork theme set obsidian` | TUI uses obsidian.css on next launch |
| TUI-07.2 | All 6 render | Cycle through all 6 themes | Each theme renders without CSS errors |
| TUI-07.3 | Persistence | Switch theme, quit, relaunch | Theme persists across sessions |

---

## MCP-01: Tool — detect_fork

| ID | Test | Action | Expected |
|----|------|--------|----------|
| MCP-01.1 | Basic call | Call detect_fork("JWT race") | Returns List[ResultCard] with explanations |
| MCP-01.2 | Limit | Call detect_fork("test", n=3) | Max 3 results |
| MCP-01.3 | No match | Call detect_fork("xyznonexistent") | Empty list, no crash |

---

## MCP-02: Tool — fork_session

| ID | Test | Action | Expected |
|----|------|--------|----------|
| MCP-02.1 | Continue | Call fork_session(id, "continue") | /fork.md with ✅/🚧 checklist |
| MCP-02.2 | Debug | Call fork_session(id, "debug") | Includes error section + root cause |
| MCP-02.3 | Invalid ID | Call fork_session("invalid", "continue") | Clear error response |

---

## MCP-03: Tool — index_status

| ID | Test | Action | Expected |
|----|------|--------|----------|
| MCP-03.1 | Populated DB | Call index_status() | Dict with counts, breakdowns, DB size |
| MCP-03.2 | Empty DB | Call index_status() on empty | All zeros, no crash |

---

## MCP-04: Tool — search_sessions

| ID | Test | Action | Expected |
|----|------|--------|----------|
| MCP-04.1 | Basic search | Call search_sessions("JWT") | List[ResultCard] |
| MCP-04.2 | Filtered | Call search_sessions("JWT", filter_project="App") | Project-filtered results |
| MCP-04.3 | No match | Call search_sessions("xyznonexistent") | Empty list |

---

## MCP-05: Tool — list_projects

| ID | Test | Action | Expected |
|----|------|--------|----------|
| MCP-05.1 | Multiple projects | Call list_projects() | List of unique project names |
| MCP-05.2 | Empty DB | Call list_projects() on empty | Empty list |

---

## MCP-06: Tool — vault_export

| ID | Test | Action | Expected |
|----|------|--------|----------|
| MCP-06.1 | Export | Call vault_export("./test-vault") | Vault created, path returned |
| MCP-06.2 | Empty DB | Call vault_export on empty | Empty vault, path returned |

---

## MCP-07: Tools — config_get / config_set

| ID | Test | Action | Expected |
|----|------|--------|----------|
| MCP-07.1 | Get theme | Call config_get("theme") | Returns current theme |
| MCP-07.2 | Set theme | Call config_set("theme", "ember") | Updates, returns confirmation |
| MCP-07.3 | Invalid key | Call config_get("nonexistent") | Error response, no crash |

---

## MCP-08: MCP CLI Management

| ID | Test | Command | Expected |
|----|------|---------|----------|
| MCP-08.1 | Install | `smartfork mcp install` | Claude Code MCP config updated |
| MCP-08.2 | Serve starts | `smartfork mcp serve` | MCP server running on stdio |
| MCP-08.3 | Status running | `smartfork mcp status` (while serve) | Reports "running" |
| MCP-08.4 | Uninstall cleanup | `smartfork mcp uninstall` | Config removed, confirms |

---

## EDGE-01: Graceful Degradation

| ID | Test | Action | Expected |
|----|------|--------|----------|
| EDGE-01.1 | No Ollama | Stop Ollama, launch smartfork | Clear message + fix instructions, TUI still loads |
| EDGE-01.2 | No API key | Use --cloud without key set | Clear "set up secrets.env" message |
| EDGE-01.3 | Corrupt ChromaDB | Corrupt chroma.sqlite3 | "Database reset required" message + command |
| EDGE-01.4 | Corrupt config | Corrupt config.toml | "Config corrupted, run smartfork setup --reset" |
| EDGE-01.5 | Missing Textual | Uninstall Textual, run smartfork | Falls back to Rich CLI mode with clear message |
| EDGE-01.6 | Low resource | `smartfork --lite` | Reduced animations, lower CPU usage |

---

## EDGE-02: Error Handling

| ID | Test | Action | Expected |
|----|------|--------|----------|
| EDGE-02.1 | No args | `smartfork` | Shows help text (not crash) |
| EDGE-02.2 | Invalid command | `smartfork nonexistent` | "Unknown command" + suggest similar |
| EDGE-02.3 | Missing required arg | `smartfork fork` (no session_id) | "Missing argument: SESSION_ID" |
| EDGE-02.4 | Unicode query | `smartfork search "résumé café"` | Handles Unicode without crash |
| EDGE-02.5 | Very long query | `smartfork search "$(repeat 10000 'x')"` | Truncates gracefully, doesn't crash |

---

## EDGE-03: Performance

| ID | Test | Action | Expected |
|----|------|--------|----------|
| EDGE-03.1 | Search latency (10K sessions) | Search with 10K indexed sessions | <500ms response |
| EDGE-03.2 | Index latency (100 sessions) | Index 100 sessions | <2 minutes |
| EDGE-03.3 | TUI startup | Launch `smartfork shell` | <2 seconds to MainScreen |
