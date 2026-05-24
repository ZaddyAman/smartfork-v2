# SmartFork v2 — Search Architecture Refactor

## Master Implementation Plan

**Version:** 1.0  
**Date:** 2026-05-24  
**Status:** Approved for Implementation  
**Estimated Duration:** 2-3 weeks  
**Total Phases:** 7  

---

## Executive Summary

This document defines the complete architecture refactor for SmartFork v2's search and indexing system. The goal is to replace the over-engineered 5-stage agentic pipeline (9+ LLM calls, ~9 minutes) with a lean, deterministic hybrid search architecture (0-2 LLM calls, <500ms-3s) while activating the currently dead supersession/relationship system.

**Key Improvements:**
- Search latency: ~9 min → <3s (default), <500ms (fast mode)
- LLM calls per search: 9+ → 0-2
- Vector storage: ChromaDB (external) → sqlite-vec (embedded in SQLite)
- Keyword search: In-memory BM25 rebuild per query → Persistent SQLite FTS5
- Session relationships: 0% utilized → 100% wired into search, fork, and display
- Chunking: 5 chunks/session destroying context → Session-level essence preserving full reasoning arc

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           USER QUERY ENTRY                               │
│  smartfork search "what happened with auth"                              │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 4: QueryInterpreter (1 LLM call)                                  │
│  - Extract keywords, synonyms, intent                                    │
│  - Detect multi_session_confidence (0.0-1.0)                             │
│  - Route: fast (0 calls) | default (1 call) | deep (2 calls)           │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           │                   │                   │
           ▼                   ▼                   ▼
    ┌────────────┐      ┌────────────┐      ┌────────────┐
    │   --fast   │      │  default   │      │   --deep   │
    │  0 LLM     │      │  1 LLM     │      │  2 LLM     │
    │  <500ms    │      │  ~2-3s     │      │  ~3-4s     │
    └─────┬──────┘      └─────┬──────┘      └─────┬──────┘
          │                   │                   │
          └───────────────────┼───────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 4: DeterministicSearchEngine (0 LLM calls)                       │
│  - Synonym expansion from dictionary                                     │
│  - FTS5 keyword search (persistent BM25 + stemming)                      │
│  - sqlite-vec vector search (session-level embeddings)                   │
│  - RRF fusion of keyword + vector ranks                                 │
│  - Multi-signal reranking (quality, recency, file overlap,               │
│    keyword density, relationship boost)                                 │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 5: SessionGraphEngine (deterministic, 0 LLM calls)               │
│  - Query session_relationships table                                     │
│  - Follow continuation chains                                           │
│  - Group results by chains                                              │
│  - Annotate ResultCards (⬆ superseded, ✅ latest, +15% boost)          │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 5: MultiSessionSynthesizer (1 LLM call, deep mode only)          │
│  - Input: Query + grouped session chains                                 │
│  - Output: Timeline + narrative + resolution status + fork suggestion   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  DISPLAY                                                                 │
│  - ResultCards with supersession annotations                             │
│  - Timeline panel (deep mode)                                            │
│  - Suggested fork command                                                │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Indexing Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         INDEXING PIPELINE                                │
│                         smartfork index                                  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 3: Scan → Parse → Normalize                                      │
│  - Scanner discovers sessions across adapters                            │
│  - Adapters parse raw files (OpenCode: SQLite, Kilo: JSON, etc.)        │
│  - SessionParser normalizes to SessionDocument                         │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 3: Enrich (IndexIntelligence, 1 structured LLM call)             │
│  - Generate summary_doc                                                │
│  - Detect quality_tag                                                  │
│  - Extract tech_tags                                                    │
│  - Refine task_raw title                                               │
│  - REMOVED: propositions (unused)                                        │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 3: Build Session Essence                                          │
│  - Compose: task_raw + summary_doc + top 3 reasoning_docs              │
│  - ~500-5000 tokens, fits in embedding context window                   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 3: Embed (1 call per session)                                    │
│  - Ollama qwen3-embedding:0.6b (1024d)                                  │
│  - Fallback: sentence-transformers mxbai-embed-large (1024d)          │
│  - Store in sqlite-vec (1 vector per session)                           │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 3: Store Metadata                                                 │
│  - SQLite sessions table (structured fields)                             │
│  - FTS5 virtual table (full-text search index)                           │
│  - sqlite-vec virtual table (vector embeddings)                           │
│  - All in ONE SQLite file (~/.smartfork/metadata.db)                    │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 3: Detect Relationships                                         │
│  - Tier 1: Explicit (OpenCode parent_id)                                 │
│  - Tier 2: Heuristic (temporal + file overlap + embedding sim)          │
│  - Tier 3: LLM verify (optional, ambiguous cases)                       │
│  - Store in session_relationships table                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Decision Log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Ollama default, sentence-transformers fallback** | 1024d consistency, instruction-aware prefixes, zero re-index for existing users |
| 2 | **Session-level essence, not chunking** | Preserves reasoning arc, reduces vectors 5x, no context fragmentation |
| 3 | **sqlite-vec over ChromaDB** | Single SQLite file, no external process, scales to 100K+ vectors |
| 4 | **FTS5 over rank_bm25** | Persistent index, Porter stemming, sub-millisecond search, no rebuild |
| 5 | **1-call structured enrichment** | 5 calls → 1 call, 80% cost reduction, same quality |
| 6 | **Remove propositions** | Unused in search, cards, or fork. Dead code. |
| 7 | **Option C: Auto multi-session + overrides** | Natural language is the product; users shouldn't memorize flags |
| 8 | **Relationship graph over flat supersession** | Supports continuation, branch, related — full developer workflow |
| 9 | **Postpone Cursor/Gemini/Cline adapters** | Only 4 active adapters; Cursor can be added later; doesn't block core refactor |
| 10 | **Postpone to --deep, not delete 5-stage** | Safer migration; can remove in Phase 6 if truly unused |

---

## Phase Dependencies

```
Phase 1: Data Model + Schema
    │
    ├───► Phase 2: Adapter Layer
    │         │
    │         └───► Phase 3: Indexing Pipeline
    │                   │
    │                   └───► Phase 4: Search Pipeline
    │                             │
    │                             └───► Phase 5: Multi-Session Intelligence
    │                                       │
    │                                       └───► Phase 6: Cleanup
    │                                                 │
    │                                                 └───► Phase 7: Testing
    │
    └───► Phase 4: Search Pipeline (also depends on Phase 1 schema)
```

**Parallel work possible:**
- Phase 1 and Phase 2 can be done in parallel (different concerns)
- Phase 6 (Cleanup) can start as soon as Phase 4 is stable

---

## Risk Register

| # | Risk | Mitigation |
|---|------|------------|
| 1 | sqlite-vec extension not available on all platforms | Fallback to BLOB storage + brute-force cosine sim |
| 2 | Ollama server not running during index/search | Auto-fallback to sentence-transformers |
| 3 | sentence-transformers 1.2GB model download too large | Make it optional dependency; warn user |
| 4 | Re-indexing required, user loses old data | Backup existing DB before migration |
| 5 | FTS5 not compiled into user's SQLite | Check at startup; fallback to LIKE queries (slower but functional) |
| 6 | Relationship detection produces false chains | Confidence thresholds + user override in TUI later |

---

## Success Criteria

### Performance
- [ ] Search default mode: <3s end-to-end (including LLM call)
- [ ] Search fast mode: <500ms end-to-end
- [ ] Indexing 300 sessions: <5 minutes (including 1 LLM call per session)
- [ ] Zero LLM calls for fast mode search

### Quality
- [ ] "jwt auth bug" returns relevant sessions in top 3
- [ ] "what happened with auth" triggers deep mode, shows timeline
- [ ] "continue my API work" follows chain to latest session
- [ ] Superseded sessions show ⬆ annotation and are demoted in ranking
- [ ] Latest session in chain shows ✅ and is boosted +15%

### Robustness
- [ ] Search works without Ollama running (FTS5 only, vector fallback)
- [ ] Indexing works without Ollama (heuristics only)
- [ ] Corrupted DB is auto-detected and reset with backup
- [ ] All existing tests pass

---

## File Inventory

### New Files (to create)
- `src/smartfork/models/relationship.py`
- `src/smartfork/models/query.py`
- `src/smartfork/models/enrichment.py`
- `src/smartfork/search/query_interpreter.py`
- `src/smartfork/search/session_graph_engine.py`
- `src/smartfork/search/multi_session_synthesizer.py`
- `src/smartfork/indexer/session_essence_builder.py`
- `src/smartfork/indexer/relationship_detector.py`

### Modified Files (to edit)
- `src/smartfork/models/session.py` — Add parent_id
- `src/smartfork/models/__init__.py` — Export new models
- `src/smartfork/indexer/metadata_store.py` — Add FTS5, sqlite-vec, relationships
- `src/smartfork/indexer/intelligence.py` — Refactor to 1-call
- `src/smartfork/indexer/embedder.py` — Replace ChromaDB with sqlite-vec
- `src/smartfork/indexer/indexer.py` — Remove chunking, add relationship detection
- `src/smartfork/indexer/chunker.py` — Remove from indexing path
- `src/smartfork/adapters/opencode.py` — Pass parent_id
- `src/smartfork/search/deterministic.py` — Add FTS5, fix reranker
- `src/smartfork/search/orchestrator.py` — Replace 5-stage with new flow
- `src/smartfork/search/synthesis.py` — Keep for ResultCard formatting
- `src/smartfork/search/cache.py` — Wire into search
- `src/smartfork/cli/commands.py` — Add --fast, --deep, --mode flags
- `src/smartfork/config.py` — Fix env var precedence
- `pyproject.toml` — Update dependencies

### Files to Delete or Deprecate
- `src/smartfork/search/reranker.py` — Move to legacy/ or delete
- `src/smartfork/search/judge.py` — Move to legacy/ or delete
- `src/smartfork/search/agentic.py` — Move to legacy/ or delete
- `src/smartfork/search/decomposer.py` — Move to legacy/ or delete

---

## Appendices

### A. Complete PRD Documents
See individual PRD files:
- `prd/phase-01-data-model.md`
- `prd/phase-02-adapter-layer.md`
- `prd/phase-03-indexing-pipeline.md`
- `prd/phase-04-search-pipeline.md`
- `prd/phase-05-multi-session-intelligence.md`
- `prd/phase-06-cleanup.md`
- `prd/phase-07-testing.md`

### B. Database Schema Reference
See `phase-01-data-model.md` for complete SQL schema.

### C. API Specifications
See individual phase PRDs for method signatures and protocols.
