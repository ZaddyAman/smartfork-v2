# SmartFork v2 — Edge Cases & Error Handling (Layer 14)

> **Design:** Every component must handle failure gracefully. SmartFork should never crash with a traceback — always show a user-friendly message.

---

## Global Error Handling Policy

1. **Never crash with a traceback** — catch all exceptions, log, show user-friendly message
2. **Degrade gracefully** — if one feature fails, others keep working
3. **Clear error messages** — tell the user what went wrong and how to fix it
4. **Always fall forward** — empty results > error > crash

---

## Provider Failures

### Ollama not installed
```
✗ Ollama is not installed.
  Install from: https://ollama.ai
  Or use cloud LLM: smartfork config set llm_provider anthropic
```

### Ollama not running
```
✗ Ollama is running but not responding.
  Start with: ollama serve
  Check status: ollama list
```

### Model not pulled
```
✗ Model 'qwen2.5-coder:7b' not found.
  Pull with: ollama pull qwen2.5-coder:7b
  Or use a different model: smartfork config set llm_model <model>
```

### Cloud API key missing
```
✗ Anthropic API key not found.
  Set with: smartfork config set-secret ANTHROPIC_API_KEY sk-ant-...
  Or use local Ollama: smartfork config set llm_provider ollama
```

### Cloud API error
```
✗ Anthropic API error: Rate limit exceeded.
  SmartFork will retry automatically.
  Switched to deterministic search for now.
```

---

## ChromaDB Failures

### Database corrupted
```
✗ ChromaDB database appears corrupted.
  Reset with: smartfork index --force
  This will re-index all sessions (1,247 sessions, est. 5 min)
```

### Database path not writable
```
✗ Cannot write to ChromaDB at ~/.smartfork/qdrant_db.
  Check disk space and permissions.
```

### Embedding dimension mismatch
```
⚠ Embedding model changed from qwen3-embedding:0.6b (1024 dims) 
  to nomic-embed-text (768 dims). These are INCOMPATIBLE.
  
  To change: smartfork config set embedding_model nomic-embed-text --reindex
  This will delete all vectors and re-index 1,247 sessions (est. 5 min).
```

---

## Database Failures

### SQLite locked
```
✗ Database is locked by another process.
  Is smartfork already running? Stop it first.
```

### SQLite corrupt
```
✗ Metadata database appears corrupted.
  Reset with: smartfork config reset-db
  This preserves your ChromaDB vectors but clears metadata.
```

---

## Adapter Failures

### Session directory not found
```
⚠ Agent 'kilocode' session path not found: C:\Users\...\tasks
  Configure with: smartfork config set agents.kilocode.sessions_path <path>
  Or disable: smartfork config set agents.kilocode.enabled false
```

### Corrupt session file
```
⚠ Skipping corrupt session: 019caac9
  Reason: JSON decode error in api_conversation_history.json
  File: C:\Users\...\tasks\019caac9\api_conversation_history.json
  Delete or fix this file to include it in the index.
```

### Unknown format
```
⚠ Skipping directory that doesn't match any known agent format.
  Path: C:\Users\...\unknown_format\
  SmartFork supports: Kilo Code, Claude Code, OpenCode, Cursor, AntiGravity, Cline, Gemini
```

---

## Search Failures

### No sessions indexed
```
✗ No sessions indexed. Run 'smartfork index' first.
```

### Query too short
```
⚠ Query too short. Try a more descriptive search phrase.
```

### No results found
```
○ No matching sessions found for "xyz".
  Try: broader terms, different angle, or check your index with 'smartfork status'
```

### Deterministic search timeout
```
⚠ Search took longer than expected.
  Try reducing sessions: filter by project or date range.
  Or switch to agentic search: smartfork detect-fork "query"
```

---

## TUI Failures

### Terminal too small
```
⚠ Terminal window too small. Minimum: 80×24.
  Current: {cols}×{rows}. Please resize.
```

### Textual not installed
```
⚠ Textual TUI not available (textual package not installed).
  Install: pip install textual
  Falling back to CLI mode.
```

### Unicode not supported (Windows legacy cmd.exe)
```
⚠ Unicode characters may not display correctly in this terminal.
  Use Windows Terminal or PowerShell 7+ for best experience.
  SmartFork will use ASCII fallback characters.
```

Fallback characters: `▪` → `#`, `·` → `.`, braille spinner → `|/-\|`

---

## Fork Failures

### Session not found
```
✗ Session 'abc123' not found in index.
  Check with: smartfork status
```

### LLM unavailable for fork
```
⚠ LLM unavailable — using raw context assembly.
  The /fork.md will be less detailed but still functional.
  To fix: start Ollama or configure cloud LLM.
```

### Compaction gap analysis fails
```
⚠ Could not perform gap analysis for compacted session 'abc123'.
  The /fork.md may miss some context from the original session.
```

---

## Vault Generation Failures

### Output path not writable
```
✗ Cannot write to ./my-vault.
  Check permissions or use a different path: --output /tmp/vault
```

### Large vault (1000+ sessions)
```
⚠ Generating vault with 1,247 sessions may take a few minutes.
  Continue? [Y/n]
```

---

## Config Failures

### Invalid TOML
```
✗ Config file is corrupted: ~/.smartfork/config.toml
  Error: Unexpected character at line 15
  Fix manually or reset: smartfork config reset
```

### Invalid theme
```
✗ Unknown theme 'bluesky'.
  Valid: phosphor, obsidian, ember, arctic, iron, tungsten
```

---

## Windows-Specific

### UTF-8 encoding
```
# Auto-detected and configured:
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
```

### Path handling
- Always use `Path` objects, never string concatenation
- Handle both `\` and `/` separators
- Handle Windows drive letters
- Handle long paths (UNC prefix if needed)

### File permissions
- Windows doesn't support `0o600` — skip chmod
- Use `%APPDATA%` for default paths

---

## macOS/Linux Specific

### File permissions
```python
if sys.platform != "win32":
    os.chmod(SECRETS_FILE, 0o600)
```

### Default paths
- macOS: `~/Library/Application Support/`
- Linux: `~/.config/`, `~/.local/share/`

---

## Concurrency

### Multiple processes
- SQLite WAL mode for concurrent reads
- Detect if another `smartfork index` is running
```
✗ Another indexing process is already running (PID: 12345).
  Wait for it to finish or stop it.
```

---

## Memory

### Large index (100K+ sessions)
- Streaming processing, not loading all at once
- Batch writes to SQLite (100 per batch)
- ChromaDB handles vectors efficiently

### Lite mode
```
--lite flag: reduced animations, smaller batches, no background LLM
```

---

## Implementation Note for Ralph

For EVERY component:
1. Identify what can fail (missing files, network errors, corrupt data)
2. Catch the exception at the right level
3. Log the full error for debugging
4. Show a user-friendly message
5. Continue processing (skip bad sessions, not crash the pipeline)
