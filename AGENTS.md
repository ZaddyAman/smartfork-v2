# AGENTS.md — SmartFork v2

## Build System
- `pyproject.toml` at project root
- Install dev: `pip install -e ".[dev]"`
- Install prod: `pip install -e .`

## Quality Checks
```bash
ruff check src/      # Linting
mypy src/            # Type checking
pytest tests/ -x     # Tests (stop on first failure)
```

## Project Structure
```
src/smartfork/
├── models/      — All Pydantic models, dataclasses, enums, protocols
├── providers/   — LLM + Embedding backends
├── adapters/    — Session format parsers (7 agents)
├── indexer/     — Parsing, chunking, embedding, intelligence, supersession
├── database/    — ChromaDB client, SQLite metadata store
├── search/      — Deterministic + Agentic search engines
├── fork/        — Fork context assembler and generator
├── vault/       — Obsidian vault generator
├── tui/         — Textual TUI screens and widgets
├── mcp/         — MCP server
└── cli/         — Typer CLI commands
```

## Key Conventions
- All Pydantic models in `models/`. Never define models in other modules.
- Protocols define interfaces. Put in the module that CONSUMES the interface.
- Factory functions (`get_llm()`, `get_embedder()`) for provider instantiation.
- Singleton `get_config()` for config access.
- Timestamps are ALWAYS milliseconds (int). Duration is ALWAYS minutes (float).
- List fields default to empty lists, never None.
- Log errors with loguru. Show user-friendly messages for known failures.
- NEVER crash with an unhandled exception.
