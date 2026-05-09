# SmartFork v2 — Architecture Overview

> **Build target:** Autonomous AI agent (Ralph) will implement this system.
> **Language:** Python 3.11+ with Textual TUI framework
> **Agent SDK:** PydanticAI (orchestration) + Smolagents (workers) + Strands Agents (MCP)
> **License:** AGPL-3.0

---

## What SmartFork v2 Solves

Every developer using AI coding tools (Claude Code, Kilo Code, Cursor, OpenCode) generates hundreds of session transcripts. These contain weeks of debugging insights, architectural decisions, and proven solutions. Without SmartFork, ALL of this context evaporates when the session ends.

SmartFork v2 is an **AI-native session intelligence CLI tool** that:

1. **Indexes** session transcripts from 7+ coding agents into a semantic vector database
2. **Searches** with both deterministic (fast, free) and agentic (LLM-orchestrated) paths
3. **Forks** context from past sessions into new sessions — eliminating cold-start
4. **Exports** knowledge as an Obsidian vault — turning coding history into a navigable second brain
5. **Presents** everything through a premium Textual TUI with command palette

---

## System Layers (build in this order)

```
Layer 0: PROVIDERS          — LLM + Embedding backends
Layer 1: ADAPTERS           — Multi-agent session format parsers
Layer 2: INGESTION          — Watcher → Parser → Chunker → Embedder → Store
Layer 3: INDEX INTELLIGENCE — Quality tags, tech tags, summaries, propositions
Layer 4: SUPERSESSION       — Detecting which sessions obsolete others
Layer 5: METADATA STORE     — SQLite for structured queries
Layer 6: SEARCH (DETERMINISTIC) — Vector + BM25 + RRF fusion (free path)
Layer 7: SEARCH (AGENTIC)   — PydanticAI orchestrated multi-step search
Layer 8: FORK PRIMING       — Context cloning for new sessions
Layer 9: OBSIDIAN VAULT     — Knowledge base export
Layer 10: TUI (TEXTUAL)     — Fullscreen terminal interface
Layer 11: MCP SERVER        — IDE integration via Model Context Protocol
Layer 12: CLI COMMANDS      — Typer-based command surface
Layer 13: TESTS             — Unit, integration, agentic E2E
```

---

## Data Flow (end-to-end)

```
SESSION DIRECTORY
  │ (Kilo Code .json OR Claude .jsonl OR OpenCode .db OR ...)
  ▼
ADAPTER (SessionAdapter.parse_raw)
  │ Normalizes agent-specific format → RawSessionData
  ▼
SESSION PARSER (SessionParser.parse_session)
  │ Derives project, domains, languages, pattern → SessionDocument
  ▼
CHUNKER (MessageBoundaryChunker)
  │ Respects conversation turns, never splits code blocks
  │ Adds context headers: [Project: X | Session: Y | Task: Z]
  ▼
EMBEDDER (EmbeddingProvider.embed)
  │ Instruction-prefixed per doc_type: task/summary/reasoning/proposition
  │ Batching: 32 chunks per call
  ▼
CHROMADB (vector_store.upsert)
  │ Vectors + metadata + full text for BM25
  ▼
METADATA STORE (SQLite)
  │ Structured fields: session_id, project, duration, domains, languages, quality_tag
  ▼
INDEX INTELLIGENCE (background LLM)
  │ Per-session: title, summary, quality tag, tech tags, propositions
  │ Cross-session: supersession detection
  ▼
READY FOR SEARCH
```

---

## Search Flow (two paths)

### Path A — Deterministic (default, free, <500ms)
```
User query
  → Embed query (same instruction as indexing)
  → Vector search (ChromaDB cosine)
  → BM25 keyword search (rank-bm25)
  → RRF fusion (reciprocal rank fusion)
  → Metadata filter (quality tag, recency, project)
  → Chunk re-rank (multi-signal: semantic 50%, file 20%, keyword 15%, recency 5%)
  → Result cards
```

### Path B — Agentic (opt-in, local Ollama or cloud API key)
```
User query
  → PydanticAI orchestrator agent:
    Step 1: Query Understanding (1 LLM call)
      → Expand natural language → structured intent + search variants
    Step 2: Multi-Variant Parallel Search (Smolagents workers, 3-5 parallel)
      → Each worker = code agent, writes Python to query ChromaDB with different strategy
    Step 3: Result Evaluation (1-2 LLM calls)
      → Agent reads top candidates (title + summary + first exchange)
      → Re-ranks based on semantic match, not just vector score
    Step 4: Refinement Loop (conditional, max 3 rounds)
      → If no candidate scores above threshold: generate new strategies → loop to Step 2
    Step 5: Recommendation Synthesis (1 LLM call)
      → Natural language explanation of WHY each result matches
  → Result cards with explanations
```

---

## Directory Structure (target)

```
smartfork/
├── pyproject.toml              # Package config, dependencies, scripts
├── README.md
├── LICENSE                     # AGPL-3.0
│
├── src/smartfork/
│   ├── __init__.py
│   ├── __main__.py             # Entry point
│   ├── config.py               # SmartForkConfig (TOML, Pydantic)
│   │
│   ├── providers/              # Layer 0
│   │   ├── __init__.py
│   │   ├── llm.py              # LLMProvider protocol + Ollama/Anthropic/OpenAI
│   │   └── embedding.py        # EmbeddingProvider protocol + Ollama/ST/OpenAI
│   │
│   ├── adapters/               # Layer 1
│   │   ├── __init__.py
│   │   ├── base.py             # SessionAdapter, RawSessionData, RawTurn
│   │   ├── registry.py         # @register decorator
│   │   ├── kilocode.py         # Kilo Code adapter
│   │   ├── claudecode.py       # Claude Code adapter  
│   │   ├── opencode.py         # OpenCode adapter (SQLite)
│   │   ├── cursor_agent.py     # Cursor adapter
│   │   ├── antigravity.py      # AntiGravity adapter
│   │   ├── cline.py            # Cline adapter
│   │   └── gemini.py           # Gemini adapter
│   │
│   ├── indexer/                # Layers 2-5
│   │   ├── __init__.py
│   │   ├── parser.py           # SessionParser (generic, takes any adapter)
│   │   ├── project_extractor.py # derive_project_name, extract_domains/languages/layers
│   │   ├── chunker.py          # MessageBoundaryChunker + ContextualChunker
│   │   ├── embedder.py         # Embedding orchestrator (uses providers)
│   │   ├── indexer.py          # FullIndexer (orchestrates parse→chunk→embed→store)
│   │   ├── watcher.py          # TranscriptWatcher (watchdog-based)
│   │   ├── scanner.py          # SessionScanner (discovers sessions)
│   │   ├── intelligence.py     # Quality tags, tech tags, titling, summarization, propositions
│   │   ├── supersession.py     # SupersessionDetector
│   │   └── metadata_store.py   # SQLite metadata store
│   │
│   ├── search/                 # Layers 6-7
│   │   ├── __init__.py
│   │   ├── deterministic.py    # Path A: Vector + BM25 + RRF + rerank
│   │   ├── agentic.py          # Path B: PydanticAI orchestrator + Smolagents workers
│   │   ├── bm25.py             # BM25 index (rank-bm25)
│   │   ├── rrf.py              # RRF fusion (standard, weighted, alpha)
│   │   ├── reranker.py         # Multi-signal chunk reranker
│   │   └── query_parser.py     # Query intent detection (reused by both paths)
│   │
│   ├── fork/                   # Layer 8
│   │   ├── __init__.py
│   │   ├── assembler.py        # ForkAssembler (intent-classified: continue/reference/debug/synthesize)
│   │   ├── generator.py        # ForkMDGenerator (query-aware context extraction)
│   │   └── gap_analyzer.py     # Compaction gap analysis
│   │
│   ├── vault/                  # Layer 9
│   │   ├── __init__.py
│   │   ├── obsidian.py         # Obsidian vault generator (MOC, Mermaid, Dataview)
│   │   └── exporter.py         # Export formats: .md, .html, .json
│   │
│   ├── tui/                    # Layer 10
│   │   ├── __init__.py
│   │   ├── app.py              # Textual App entry point
│   │   ├── screens/            # Textual screens
│   │   │   ├── main.py         # Main search/command screen
│   │   │   ├── search.py       # Search results screen
│   │   │   ├── fork.py         # Fork preview screen
│   │   │   ├── status.py       # Index status screen
│   │   │   └── setup.py        # Setup wizard screen
│   │   ├── widgets/            # Reusable Textual widgets
│   │   │   ├── command_palette.py
│   │   │   ├── result_card.py
│   │   │   ├── progress_bar.py
│   │   │   ├── theme_switcher.py
│   │   │   └── shortcut_bar.py
│   │   └── themes/             # Textual CSS themes
│   │       ├── phosphor.tcss
│   │       ├── obsidian.tcss
│   │       ├── ember.tcss
│   │       ├── arctic.tcss
│   │       ├── iron.tcss
│   │       └── tungsten.tcss
│   │
│   ├── mcp/                    # Layer 11
│   │   ├── __init__.py
│   │   └── server.py           # MCP server (using Strands Agents)
│   │
│   ├── cli/                    # Layer 12
│   │   ├── __init__.py
│   │   └── commands.py         # All Typer commands
│   │
│   └── models/                 # Data models (shared)
│       ├── __init__.py
│       ├── session.py          # SessionDocument, TaskSession
│       ├── search.py           # SearchResult, ResultCard, QueryIntent
│       └── fork.py             # ForkIntent, ContextReport
│
├── tests/
│   ├── conftest.py
│   ├── test_providers.py
│   ├── test_adapters.py
│   ├── test_indexer.py
│   ├── test_search_deterministic.py
│   ├── test_search_agentic.py
│   ├── test_fork.py
│   ├── test_vault.py
│   ├── test_tui.py
│   └── test_mcp.py
│
└── ralph/
    ├── prompt.md               # Ralph agent instructions
    ├── prd.json                # User stories (generated from specs)
    └── progress.txt            # Learnings from each loop iteration
```

---

## Key Design Principles

1. **Local-first, cloud-optional** — Everything works offline with Ollama. Cloud API keys are opt-in.
2. **Adapter pattern** — The core pipeline never knows which agent produced the data. New agents = new adapter, zero pipeline changes.
3. **Two search paths** — Deterministic is always free and available. Agentic is opt-in for power users.
4. **Index-time intelligence** — LLM work happens once per session at index time, benefits all future searches.
5. **Memory via filesystem** — Git history + SQLite + ChromaDB, not in-memory state.
6. **Pluggable providers** — LLM and embedding backends are swappable via Protocol interfaces.
7. **Opinionated TUI** — Command palette, keyboard-first, no mouse required but supported.

---

## Dependencies

```
# Core
pydantic>=2.0
pydantic-settings>=2.0
tomli>=2.0
tomli-w>=1.0
typer>=0.9
rich>=13.0
textual>=0.50

# AI / ML
chromadb>=0.5
ollama>=0.4
sentence-transformers>=3.0
rank-bm25>=0.2
pydantic-ai>=0.0.1
smolagents>=1.0
strands-agents>=1.0
instructor>=1.0

# Storage
aiosqlite>=0.20

# File watching
watchdog>=4.0

# Utilities
loguru>=0.7
python-dotenv>=1.0

# Testing
pytest>=8.0
pytest-asyncio>=0.24

# Dev
ruff>=0.5
mypy>=1.0
```

---

## Build Order (for Ralph)

Ralph should implement the system in this order. Each layer depends on the previous:

1. `00-architecture.md` — Read first (this file)
2. `19-data-models.md` — All models, schemas, protocols BEFORE any implementation
3. `01-providers.md` — LLM + Embedding providers
4. `02-config.md` — Config system
5. `03-adapters.md` — Adapter system (base + all 7 adapters)
6. `04-parser.md` — SessionParser + project extraction
7. `05-chunking.md` — Chunking system
8. `06-embedding.md` — Embedding pipeline
9. `09-metadata-store.md` — SQLite metadata store
10. `07-index-intelligence.md` — Quality tags, tech tags, summaries
11. `08-supersession.md` — Supersession detection
12. `10-deterministic-search.md` — Path A search
13. `11-agentic-search.md` — Path B agentic search
14. `12-fork-priming.md` — Fork context generation
15. `13-obsidian-vault.md` — Obsidian vault export
16. `16-cli-commands.md` — CLI command surface
17. `14-tui-app.md` — Textual TUI
18. `15-mcp-server.md` — MCP server
19. `17-testing-strategy.md` — Tests
20. `18-edge-cases.md` — Edge case reference (read alongside each layer)
