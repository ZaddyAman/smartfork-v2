# SmartFork v2

> **AI-Native Session Intelligence CLI Tool**
> 
> Index your coding session transcripts from 7+ AI coding agents.
> Search with deterministic or LLM-orchestrated search.
> Fork context into new sessions. Export knowledge as Obsidian vaults.

## Status

🚧 **PRD Complete — Ready for Ralph implementation**

This repository contains the complete Product Requirements Document (PRD) and Ralph agent loop setup for building SmartFork v2 from scratch using autonomous AI coding.

## Quick Links

- [Architecture Overview](specs/00-architecture.md)
- [All Specifications](specs/)
- [PRD User Stories](ralph/prd.json)
- [Ralph Agent Instructions](ralph/prompt.md)

## Running Ralph

```bash
cd ralph
chmod +x ralph.sh
./ralph.sh           # Default: 50 iterations
./ralph.sh 100       # Custom max iterations
```

## Requirements

- Python 3.11+
- Claude Code (or Amp) for Ralph loop
- Ollama for local LLM/embeddings
- Git

## License

AGPL-3.0 — See [LICENSE](LICENSE)
