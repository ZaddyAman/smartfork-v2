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
├── indexer/     — Parsing, chunking, embedding, metadata store, supersession
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

## Supported LLM Providers

| Provider | Environment Variable | Example Model | Notes |
|---|---|---|---|
| ollama | (none) | qwen2.5-coder:7b | Local models via Ollama |
| anthropic | ANTHROPIC_API_KEY | claude-3-haiku-20240307 | |
| openai | OPENAI_API_KEY | gpt-4o-mini | |
| opencode | OPENCODE_API_KEY | qwen3.5-plus | |
| go | OPENCODE_API_KEY | qwen3.5-plus | |
| zen | OPENCODE_API_KEY | qwen3.5-plus | |
| openrouter | OPENROUTER_API_KEY | meta-llama/llama-3.3-70b-instruct:free | Free tier available |
| groq | GROQ_API_KEY | llama-3.3-70b-versatile | |
| gemini | GOOGLE_API_KEY | gemini-1.5-flash-latest | |
| together | TOGETHER_API_KEY | meta-llama/Llama-3.3-70B-Instruct-Turbo | |
| mistral | MISTRAL_API_KEY | mistral-large-latest | |
| deepseek | DEEPSEEK_API_KEY | deepseek-chat | |
| fireworks | FIREWORKS_API_KEY | accounts/fireworks/models/llama-v3p1-8b-instruct | |
| cohere | COHERE_API_KEY | command-r | |
| xai | XAI_API_KEY | grok-2-latest | |
| perplexity | PERPLEXITY_API_KEY | sonar | |
