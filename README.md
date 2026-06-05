# SmartFork v2

AI-native session intelligence CLI tool. Indexes coding sessions from AI agents (OpenCode, KiloCode, Claude Code, Cursor, Gemini, Cline) and provides semantic search, relationship detection, and fork context generation.

## Features

- **Multi-Agent Support**: Parse sessions from 7 AI coding agents via adapters
- **Semantic Search**: Hybrid FTS5 + vector search with sqlite-vec (fallback to FTS5-only when extension unavailable)
- **Three Search Modes**:
  - `--fast`: Deterministic search only (0 LLM calls, <500ms)
  - Default: QueryInterpreter + deterministic search (1 LLM call, <3s)
  - `--deep`: Multi-session timeline synthesis (2 LLM calls, <4s)
- **Session Relationships**: Automatic detection of continuation, supersession, branch, and related sessions
- **Fork Context Generation**: Generate handoff documents to resume work across sessions
- **Obsidian Vault Export**: Export indexed sessions as a markdown vault
- **MCP Server**: Claude Code integration via Model Context Protocol
- **15+ LLM Providers**: Ollama, OpenAI, Anthropic, OpenCode, OpenRouter, Groq, Gemini, Together, Mistral, DeepSeek, Fireworks, Cohere, xAI, Perplexity

## Installation

```bash
pip install -e ".[dev]"
```

## Quick Start

```bash
# Index all discovered sessions
smartfork index

# Search with AI-assisted query expansion (default)
smartfork search "jwt auth bug"

# Fast deterministic search only
smartfork search "jwt auth" --fast

# Deep multi-session timeline mode
smartfork search "what happened with auth across sessions" --deep

# Generate fork context from a session
smartfork fork <session_id>

# Show indexing status
smartfork status

# Generate Obsidian vault
smartfork vault
```

## Architecture

```
src/smartfork/
├── models/      — Pydantic models, dataclasses, enums, protocols
├── providers/   — LLM + Embedding backends (15+ providers)
├── adapters/    — Session format parsers (7 agents)
├── indexer/     — Session-level embedding, relationship detection, metadata store
├── search/      — QueryInterpreter, DeterministicSearchEngine, SearchOrchestrator
├── fork/        — Fork context assembler and generator
├── vault/       — Obsidian vault generator
├── tui/         — Textual TUI screens and widgets
├── mcp/         — MCP server for Claude Code
└── cli/         — Typer CLI commands
```

## Search Modes

| Mode | Flag | LLM Calls | Latency | Use Case |
|------|------|-----------|---------|----------|
| Fast | `--fast` | 0 | <500ms | Known keywords, quick lookup |
| Default | (none) | 1 | <3s | Natural language queries |
| Deep | `--deep` | 2 | <4s | Multi-session timeline, continuation |

## Quality Checks

```bash
ruff check src/      # Linting
mypy src/            # Type checking
pytest tests/ -x     # Tests (stop on first failure)
```

See [AGENTS.md](AGENTS.md) for full conventions, provider table, and development guidelines.
