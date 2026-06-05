# Phase 4 PRD: Search Pipeline Rewrite

**Phase:** 4 of 7  
**Estimated Duration:** 3-4 days  
**Priority:** Critical  
**Dependencies:** Phase 1 (Data Model + Schema), Phase 3 (Indexing Pipeline)  

---

## 1. Overview

This phase completely rewrites the search pipeline to replace the wasteful 5-stage orchestrator (9+ LLM calls) with a lean architecture: 1 LLM call for QueryInterpreter + deterministic hybrid search + optional 1 LLM call for multi-session synthesis.

**Current search flow (BROKEN):**
```
Decompose (1 call) → Parallel Retrieve (0 calls) → Rerank (2-6 calls) 
→ Judge (1-3 calls) → Synthesize (0 calls)
= ~9-13 LLM calls, ~9 minutes
```

**New search flow:**
```
QueryInterpreter (1 call) → DeterministicSearchEngine (0 calls) 
→ [optional] MultiSessionSynthesizer (1 call)
= 1-2 LLM calls, <3s (default), <500ms (fast), <4s (deep)
```

**Success Criteria:**
- [ ] Default search uses 1 LLM call (not 9+)
- [ ] Fast mode uses 0 LLM calls
- [ ] Deep mode uses 2 LLM calls
- [ ] FTS5 replaces in-memory BM25 rebuild
- [ ] sqlite-vec replaces ChromaDB vector search
- [ ] Reranker and Judge removed from default path
- [ ] Search latency: <3s default, <500ms fast, <4s deep

---

## 2. New Components

### 2.1 `QueryInterpreter` (NEW)

**File:** `src/smartfork/search/query_interpreter.py`  
**Purpose:** Single structured LLM call that replaces Decomposer + Reranker + Judge.

```python
"""Query interpreter for SmartFork v2.

Replaces the 5-stage decomposer with a single structured LLM call
that extracts keywords, expands synonyms, detects intent, and
computes multi_session_confidence for routing.
"""

from collections.abc import Callable
from typing import Any

from loguru import logger

from smartfork.models.query import QueryInterpretation


# Synonym dictionary for query expansion
SYNONYMS: dict[str, list[str]] = {
    "auth": ["authentication", "login", "oauth", "jwt", "token", "session"],
    "bug": ["error", "fix", "issue", "crash", "broken", "failure", "exception"],
    "db": ["database", "postgresql", "mysql", "sqlite", "sql", "migration"],
    "api": ["endpoint", "route", "rest", "graphql", "controller"],
    "deploy": ["deployment", "ci", "cd", "pipeline", "docker", "kubernetes"],
    "test": ["testing", "pytest", "jest", "spec", "unit test", "integration"],
    "ui": ["frontend", "component", "react", "css", "layout", "design"],
    "perf": ["performance", "speed", "optimization", "latency", "cache"],
}

# Intent keywords for deterministic fallback
INTENT_PATTERNS: dict[str, list[str]] = {
    "solution_hunting": ["how did i", "how to", "implement", "build", "create", "solve"],
    "error_recall": ["error", "bug", "fix", "crash", "broken", "fail", "exception"],
    "continuation": ["continue", "resume", "pick up", "where i left", "follow up"],
    "temporal_lookup": ["last week", "yesterday", "recently", "this week", "last month"],
    "decision_hunting": ["why did", "decision", "approach", "tradeoff", "choose"],
    "implementation_lookup": ["how did i", "how to", "build", "create", "implement"],
}


class QueryInterpreter:
    """Interprets natural language queries into structured search parameters.
    
    Uses 1 structured LLM call (or deterministic fallback) to produce
    QueryInterpretation with keywords, synonyms, intent, and routing.
    """
    
    def __init__(self, llm: object | None = None) -> None:
        self.llm = llm
    
    def interpret(self, query: str) -> QueryInterpretation:
        """Interpret a natural language query.
        
        Args:
            query: The user's raw search query.
        
        Returns:
            QueryInterpretation with structured search parameters.
        """
        if self.llm:
            try:
                return self._llm_interpret(query)
            except Exception as e:
                logger.warning(f"LLM interpretation failed, using fallback: {e}")
                return self._fallback_interpret(query)
        else:
            return self._fallback_interpret(query)
    
    def _llm_interpret(self, query: str) -> QueryInterpretation:
        """Structured LLM call for query interpretation."""
        prompt = f"""Analyze this developer search query and return structured JSON:

Query: "{query}"

Return this exact JSON structure:
{{
    "keywords": ["extracted", "technical", "keywords"],
    "synonyms": ["expanded", "terms"],
    "intent": "solution_hunting" or "error_recall" or "continuation" or "temporal_lookup" or "decision_hunting" or "implementation_lookup" or "vague_memory",
    "multi_session_confidence": 0.0 to 1.0,
    "project_hint": null or "project_name",
    "quality_boost": ["solution_found"] or [],
    "temporal_filter": null or {{"type": "relative", "value": "last_week"}}
}}

Rules:
- keywords: Extract 1-5 technical keywords (jwt, auth, bug, database, etc.)
- synonyms: Include related terms from domain knowledge
- intent: Classify the query's purpose
- multi_session_confidence: 
  - >0.75 if query contains temporal words ("what happened", "timeline", "across sessions")
  - >0.80 if query contains continuation words ("continue", "resume")
  - 0.40-0.75 if ambiguous ("how did I fix auth")
  - <0.40 if specific keywords only ("jwt auth bug")
- project_hint: Extract project name if mentioned
- quality_boost: ["solution_found"] if hunting for solutions
"""
        
        if hasattr(self.llm, 'complete_structured'):
            result = self.llm.complete_structured(
                prompt,
                output_schema=QueryInterpretation,
                max_tokens=400,
                temperature=0.1,
            )
            # Ensure original_query is set
            result.original_query = query
            return result
        else:
            result = self.llm.complete(prompt, max_tokens=400)
            return self._parse_interpretation(str(result), query)
    
    def _parse_interpretation(self, text: str, query: str) -> QueryInterpretation:
        """Parse text response into QueryInterpretation."""
        import json
        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                return QueryInterpretation(
                    original_query=query,
                    keywords=data.get("keywords", []),
                    synonyms=data.get("synonyms", []),
                    intent=data.get("intent", "vague_memory"),
                    multi_session_confidence=data.get("multi_session_confidence", 0.0),
                    project_hint=data.get("project_hint"),
                    quality_boost=data.get("quality_boost", []),
                    temporal_filter=data.get("temporal_filter"),
                )
        except (json.JSONDecodeError, ValueError):
            pass
        
        return self._fallback_interpret(query)
    
    def _fallback_interpret(self, query: str) -> QueryInterpretation:
        """Deterministic interpretation without LLM."""
        query_lower = query.lower()
        
        # Extract keywords (simple split + filter)
        words = [w for w in query_lower.split() if len(w) > 2]
        keywords = words[:5]  # Top 5 words
        
        # Expand synonyms
        synonyms: list[str] = []
        for word in keywords:
            if word in SYNONYMS:
                synonyms.extend(SYNONYMS[word])
        
        # Detect intent
        intent_scores: dict[str, int] = {}
        for intent, patterns in INTENT_PATTERNS.items():
            score = sum(1 for p in patterns if p in query_lower)
            if score > 0:
                intent_scores[intent] = score
        
        intent = max(intent_scores, key=intent_scores.get) if intent_scores else "vague_memory"
        
        # Compute multi_session confidence
        multi_session_confidence = 0.0
        temporal_words = ["what happened", "timeline", "journey", "across sessions", "history"]
        continuation_words = ["continue", "resume", "pick up", "where i left"]
        
        if any(w in query_lower for w in temporal_words):
            multi_session_confidence = 0.85
        elif any(w in query_lower for w in continuation_words):
            multi_session_confidence = 0.90
        elif intent in ("solution_hunting", "implementation_lookup"):
            multi_session_confidence = 0.30
        else:
            multi_session_confidence = 0.50
        
        # Build expanded query for FTS5
        all_terms = list(set(keywords + synonyms))
        expanded = " OR ".join(all_terms) if all_terms else query
        
        return QueryInterpretation(
            original_query=query,
            keywords=keywords,
            synonyms=synonyms,
            expanded_query=expanded,
            intent=intent,
            multi_session_confidence=multi_session_confidence,
            needs_deep_mode=multi_session_confidence > 0.75,
            quality_boost=["solution_found"] if intent == "solution_hunting" else [],
        )
```

**Export:** Add to `src/smartfork/search/__init__.py`

---

## 3. Modified Components

### 3.1 `DeterministicSearchEngine` (REWRITTEN)

**File:** `src/smartfork/search/deterministic.py`  
**Current:** In-memory BM25 rebuild per query + ChromaDB vector search  
**New:** Persistent FTS5 + sqlite-vec + RRF

```python
# REPLACE _bm25_search() method:

def _bm25_search(self, query: str, top_k: int = 30) -> list[tuple[str, float]]:
    """Search using persistent FTS5 index (REPLACES in-memory BM25)."""
    # Expand query with synonyms
    expanded = self._expand_query(query)
    
    # Query FTS5 virtual table via MetadataStore
    return self.store.fts5_search(expanded, limit=top_k)

def _expand_query(self, query: str) -> str:
    """Expand query with synonyms for FTS5 MATCH syntax."""
    from smartfork.search.query_interpreter import SYNONYMS
    
    words = query.lower().split()
    expanded_terms: list[str] = []
    
    for word in words:
        if word in SYNONYMS:
            synonyms = SYNONYMS[word]
            expanded_terms.append(f"({word} OR {' OR '.join(synonyms)})")
        else:
            expanded_terms.append(word)
    
    return " AND ".join(expanded_terms)

# REPLACE _vector_search() method:

def _vector_search(self, query: str, top_k: int = 30) -> list[tuple[str, float]]:
    """Search using sqlite-vec (REPLACES ChromaDB)."""
    # Embed query
    query_vector = self.embedder.embed_query(query)
    
    # Query sqlite-vec via MetadataStore
    return self.store.vector_search(query_vector, limit=top_k)

# FIX _rerank() method — add missing signals:

def _rerank(self, results: list[dict], interpretation: QueryInterpretation | None = None) -> list[dict]:
    """Multi-signal reranking with relationship awareness."""
    for result in results:
        base_score = result.get("match_score", 0.5)
        final_score = base_score * 0.50  # 50% semantic
        
        # Quality bonus (10%)
        if result.get("quality_tag") == "solution_found":
            final_score += 0.10
        elif result.get("quality_tag") == "partial":
            final_score += 0.05
        
        # Recency bonus (5%)
        if interpretation and interpretation.intent in ("continuation", "temporal_lookup"):
            # Boost recent sessions for continuation/temporal queries
            age_days = (time.time() * 1000 - result.get("session_start", 0)) / (24 * 3600 * 1000)
            if age_days < 7:
                final_score += 0.05
            elif age_days < 30:
                final_score += 0.03
        
        # Code preference bonus (5%)
        if interpretation and interpretation.intent == "implementation_lookup":
            if result.get("files_edited"):
                final_score += 0.05
        
        # File overlap (20%) — NEW
        if interpretation and interpretation.keywords:
            files = result.get("files_edited", []) + result.get("files_read", [])
            overlap = sum(1 for k in interpretation.keywords if any(k in f.lower() for f in files))
            final_score += 0.20 * (overlap / max(len(interpretation.keywords), 1))
        
        # Keyword density (15%) — NEW
        if interpretation and interpretation.keywords:
            text = " ".join([
                result.get("task_raw", ""),
                result.get("summary_doc", ""),
                " ".join(result.get("reasoning_docs", [])),
            ]).lower()
            matches = sum(1 for k in interpretation.keywords if k in text)
            final_score += 0.15 * (matches / max(len(interpretation.keywords), 1))
        
        # Relationship boost — NEW
        # Latest in chain +15%, superseded -30%
        session_id = result.get("session_id")
        if session_id and self.store:
            relationships = self.store.get_relationships(session_id, direction="to")
            for rel in relationships:
                if rel.relationship_type == "supersession":
                    # This session is superseded — demote
                    final_score *= 0.70
                    result["supersession_note"] = f"⬆ Superseded by '{rel.to_session}'"
                    break
            else:
                # Check if this is the latest in chain
                from_rels = self.store.get_relationships(session_id, direction="from")
                if from_rels:
                    final_score += 0.15
                    result["supersession_note"] = "✅ Latest in chain"
                else:
                    result["supersession_note"] = ""
        
        result["match_score"] = min(final_score, 1.0)
    
    # Sort by final score
    results.sort(key=lambda x: x["match_score"], reverse=True)
    return results
```

**Key changes:**
- `_bm25_search()` → `store.fts5_search()` (persistent index)
- `_vector_search()` → `store.vector_search()` (sqlite-vec)
- `_rerank()` adds file_overlap (20%), keyword_density (15%), relationship boost
- `_expand_query()` adds synonym expansion for FTS5

---

### 3.2 `SearchOrchestrator` (REWRITTEN)

**File:** `src/smartfork/search/orchestrator.py`  
**Current:** 5-stage pipeline (decompose → retrieve → rerank → judge → synthesize)  
**New:** QueryInterpreter → DeterministicSearchEngine → [optional] MultiSessionSynthesizer

```python
# REPLACE SearchOrchestrator class:

class SearchOrchestrator:
    """Orchestrates the new lean search pipeline.
    
    Flow:
    1. QueryInterpreter (1 LLM call) → structured search params
    2. DeterministicSearchEngine (0 LLM calls) → hybrid search
    3. [Optional] SessionGraphEngine + MultiSessionSynthesizer (1 LLM call for deep mode)
    4. Format ResultCards
    """
    
    def __init__(
        self,
        llm: object | None = None,
        embedder: EmbeddingProvider | None = None,
        store: MetadataStore | None = None,
    ) -> None:
        self.llm = llm
        self.embedder = embedder
        self.store = store or MetadataStore()
        self.interpreter = QueryInterpreter(llm)
        self.engine = DeterministicSearchEngine(embedder=embedder, store=store)
        self.graph_engine = SessionGraphEngine(store)
        self.synthesizer = MultiSessionSynthesizer(llm) if llm else None
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        project_filter: str | None = None,
        quality_filter: str | None = None,
        mode: str = "default",  # "fast" | "default" | "deep"
    ) -> list[ResultCard]:
        """Execute search with the lean pipeline.
        
        Args:
            query: User's natural language query.
            top_k: Number of results to return.
            project_filter: Optional project name filter.
            quality_filter: Optional quality tag filter.
            mode: "fast" (0 LLM calls), "default" (1 LLM call), "deep" (2 LLM calls).
        
        Returns:
            List of ResultCard objects.
        """
        # Step 1: Interpret query
        if mode == "fast":
            # Skip LLM interpretation entirely
            interpretation = QueryInterpretation(
                original_query=query,
                keywords=query.lower().split(),
                needs_deep_mode=False,
            )
        else:
            interpretation = self.interpreter.interpret(query)
        
        # Step 2: Search
        results = self.engine.search(
            query=interpretation.expanded_query or query,
            top_k=top_k * 3,  # Retrieve more for reranking
            project_filter=project_filter,
            quality_filter=quality_filter,
            interpretation=interpretation,
        )
        
        # Step 3: Multi-session synthesis (deep mode only)
        if mode == "deep" or (mode == "default" and interpretation.needs_deep_mode):
            if self.synthesizer:
                # Group results by chains
                chains = self.graph_engine.find_related_sessions(
                    query=query,
                    project=project_filter,
                    max_chains=3,
                )
                
                # Synthesize timeline/narrative
                synthesis = self.synthesizer.synthesize_timeline(query, chains)
                
                # Add synthesis to results (for CLI display)
                for card in results:
                    card.synthesis = synthesis.narrative if synthesis else ""
        
        # Step 4: Format ResultCards
        return self._format_cards(results[:top_k])
    
    def _format_cards(self, results: list[dict]) -> list[ResultCard]:
        """Format search results into ResultCards."""
        cards = []
        for i, result in enumerate(results, 1):
            card = ResultCard(
                session_id=result.get("session_id", ""),
                title=result.get("task_raw", "Untitled"),
                match_score=result.get("match_score", 0.0),
                project_name=result.get("project_name", ""),
                time_ago=self._format_time_ago(result.get("session_start", 0)),
                excerpt=result.get("summary_doc", "")[:200],
                tags=result.get("tech_tags", []),
                files_summary=self._summarize_files(result.get("files_edited", [])),
                fork_command=f"smartfork fork {result.get('session_id', '')}",
                quality_badge=self._quality_badge(result.get("quality_tag", "")),
                supersession_note=result.get("supersession_note", ""),
                rank=i,
            )
            cards.append(card)
        return cards
    
    def _format_time_ago(self, timestamp: int) -> str:
        """Format timestamp as human-readable time ago."""
        # Implementation from existing code
        pass
    
    def _summarize_files(self, files: list[str]) -> str:
        """Summarize file list for display."""
        if not files:
            return ""
        if len(files) <= 3:
            return ", ".join(files)
        return f"{files[0]}, {files[1]} +{len(files) - 2} more"
    
    def _quality_badge(self, quality_tag: str) -> str:
        """Map quality tag to display badge."""
        badges = {
            "solution_found": "[green]Strong match[/green]",
            "partial": "[yellow]Moderate match[/yellow]",
            "dead_end": "[red]Weak match[/red]",
            "reference": "[blue]Reference[/blue]",
        }
        return badges.get(quality_tag, "")
```

**Key changes:**
- Remove `decomposer`, `parallel_retriever`, `reranker`, `judge`, `synthesis` stages
- Add `interpreter`, `graph_engine`, `synthesizer`
- Mode parameter: "fast" | "default" | "deep"
- Deep mode triggers `MultiSessionSynthesizer` for timeline/narrative

---

## 4. Deliverables

| # | Deliverable | File | Acceptance Criteria |
|---|-------------|------|-------------------|
| 1 | `QueryInterpreter` | `search/query_interpreter.py` | 1 structured call, synonym expansion, intent detection |
| 2 | Rewritten `DeterministicSearchEngine` | `search/deterministic.py` | FTS5 + sqlite-vec + RRF + relationship boost |
| 3 | Rewritten `SearchOrchestrator` | `search/orchestrator.py` | 1-2 LLM calls, mode routing |
| 4 | Tests | `tests/search/` | All components tested |

---

## 5. Dependencies

### Depends on:
- Phase 1: `QueryInterpretation` model, FTS5 schema, sqlite-vec schema
- Phase 3: Vectors in sqlite-vec, relationships in DB

### Blocks:
- Phase 5: Multi-session intelligence uses `SearchOrchestrator` deep mode
- Phase 6: Cleanup removes old search components

---

## 6. Notes for Implementer

1. **Reranker/Judge removal:** Move `search/reranker.py` and `search/judge.py` to `search/legacy/` or delete. Don't leave them in the default path.
2. **Decomposer removal:** Move `search/decomposer.py` to `search/legacy/` (may still be used by --legacy flag).
3. **AgenticSearchEngine:** Move `search/agentic.py` to `search/legacy/` (dead code, never used by CLI).
4. **Backward compatibility:** Keep `--fast` flag working (skip interpreter, use deterministic directly).
5. **FTS5 query syntax:** The MATCH syntax is `(auth OR authentication) AND (bug OR error)`. Test on actual SQLite FTS5.
6. **Relationship boost:** Must query `session_relationships` table for each result. Cache per search to avoid N+1 queries.
