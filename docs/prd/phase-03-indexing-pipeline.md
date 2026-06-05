# Phase 3 PRD: Indexing Pipeline Rewrite

**Phase:** 3 of 7  
**Estimated Duration:** 2-3 days  
**Priority:** Critical  
**Dependencies:** Phase 1 (Data Model + Schema), Phase 2 (Adapter Layer)  

---

## 1. Overview

This phase completely rewrites the indexing pipeline to:
1. Replace chunk-level embeddings with session-level essence embeddings
2. Replace ChromaDB with sqlite-vec (in SQLite)
3. Refactor IndexIntelligence from 5 LLM calls to 1 structured call
4. Add relationship detection at index time
5. Build session essence for embedding

**Current indexing flow (BROKEN):**
```
Scan → Parse → Chunk (5 chunks/session) → Embed (5 vectors/session) 
→ Store in ChromaDB → Enrich (5 LLM calls) → Store metadata
= 1,500 vectors, 1,500+ LLM calls, 50+ minutes
```

**New indexing flow:**
```
Scan → Parse → Build Essence → Embed (1 vector/session) 
→ Store in sqlite-vec → Enrich (1 LLM call) → Store metadata 
→ Detect Relationships
= 300 vectors, 300 LLM calls, ~5 minutes
```

**Success Criteria:**
- [ ] Indexing produces 1 vector per session (not 5 chunks)
- [ ] Vectors stored in sqlite-vec, not ChromaDB
- [ ] IndexIntelligence uses 1 structured LLM call per session
- [ ] Relationship detection runs after all sessions in a project are stored
- [ ] Full re-index of 300 sessions completes in <5 minutes
- [ ] Session essence contains task + summary + top 3 reasoning docs
- [ ] Fallback to sentence-transformers works if Ollama unavailable

---

## 2. New Components

### 2.1 `SessionEssenceBuilder` (NEW)

**File:** `src/smartfork/indexer/session_essence_builder.py`  
**Purpose:** Create a ~500-5000 token text representation of a session for embedding.

```python
"""Session essence builder for SmartFork v2.

Creates a condensed text representation of a session that captures
the task → approach → outcome arc without including the full
(potentially 50K+ token) transcript.
"""

from smartfork.models.session import SessionDocument


class SessionEssenceBuilder:
    """Builds a session essence string for embedding.
    
    The essence captures:
    - What the user was trying to do (task)
    - What they concluded (summary)
    - Key reasoning blocks (top 3, most informative)
    
    Total length: ~500-5000 tokens, well within embedding model limits.
    """
    
    def __init__(self, max_reasoning_docs: int = 3, max_reasoning_length: int = 1500) -> None:
        self.max_reasoning_docs = max_reasoning_docs
        self.max_reasoning_length = max_reasoning_length
    
    def build_essence(self, session: SessionDocument) -> str:
        """Build an essence string from a SessionDocument.
        
        Args:
            session: The session to build essence for.
        
        Returns:
            A text string suitable for embedding.
        """
        parts: list[str] = []
        
        # Part 1: Task (always included)
        if session.task_raw:
            parts.append(f"Task: {session.task_raw}")
        
        # Part 2: Summary (always included if available)
        if session.summary_doc:
            parts.append(f"Summary: {session.summary_doc}")
        
        # Part 3: Key reasoning blocks (top N, truncated)
        for i, reasoning in enumerate(session.reasoning_docs[:self.max_reasoning_docs]):
            if reasoning.strip():
                truncated = reasoning[:self.max_reasoning_length]
                if len(reasoning) > self.max_reasoning_length:
                    truncated += "..."
                parts.append(f"Reasoning {i+1}: {truncated}")
        
        # Part 4: Tech context (brief)
        if session.tech_tags:
            parts.append(f"Technologies: {', '.join(session.tech_tags)}")
        
        return "\n\n".join(parts)
    
    def build_essence_with_instruction(self, session: SessionDocument) -> str:
        """Build essence with an instruction prefix for Ollama embedder.
        
        Ollama's qwen3-embedding model supports instruction-aware embedding.
        This prepends a domain-specific instruction to improve retrieval quality.
        """
        essence = self.build_essence(session)
        instruction = (
            "Represent this coding session for semantic retrieval. "
            "Capture the task, approach, and outcome."
        )
        return f"{instruction}\n\n{essence}"
```

**Export:** Add to `src/smartfork/indexer/__init__.py`

---

### 2.2 `RelationshipDetector` (NEW)

**File:** `src/smartfork/indexer/relationship_detector.py`  
**Purpose:** Detect relationships between sessions at index time.

```python
"""Relationship detection for SmartFork v2.

Detects explicit, heuristic, and LLM-verified relationships between
sessions at index time. Runs after all sessions for a project have
been stored in the metadata store.
"""

import math
from collections import defaultdict
from typing import Any

from loguru import logger

from smartfork.indexer.metadata_store import MetadataStore
from smartfork.models.relationship import SessionRelationship
from smartfork.models.session import SessionDocument


class RelationshipDetector:
    """Detects relationships between sessions.
    
    Uses three tiers of detection:
    1. Explicit: parent_id from OpenCode adapter (confidence=1.0)
    2. Heuristic: temporal + file overlap + embedding similarity
    3. LLM verify: For ambiguous cases (optional, disabled by default)
    """
    
    # Thresholds
    HEURISTIC_THRESHOLD = 0.65
    LLM_VERIFY_THRESHOLD = 0.40  # 0.40-0.65 is ambiguous zone
    
    # Scoring weights
    TEMPORAL_WEIGHT = 0.30
    FILE_OVERLAP_WEIGHT = 0.25
    EMBEDDING_WEIGHT = 0.20
    WORKSPACE_WEIGHT = 0.15
    NAMING_WEIGHT = 0.10
    
    def __init__(self, store: MetadataStore | None = None) -> None:
        self.store = store or MetadataStore()
    
    def detect_all(
        self,
        sessions: list[SessionDocument],
        vectors: dict[str, list[float]] | None = None,
    ) -> list[SessionRelationship]:
        """Detect all relationships in a set of sessions.
        
        Args:
            sessions: List of sessions to analyze (should be from same project).
            vectors: Optional dict of session_id → embedding vector.
        
        Returns:
            List of detected SessionRelationship objects.
        """
        relationships: list[SessionRelationship] = []
        
        # Tier 1: Explicit relationships
        explicit = self._detect_explicit(sessions)
        relationships.extend(explicit)
        
        # Tier 2: Heuristic relationships
        heuristic = self._detect_heuristic(sessions, vectors)
        relationships.extend(heuristic)
        
        # Tier 3: LLM verification (optional, disabled by default)
        # This would run on ambiguous pairs in heuristic
        
        return relationships
    
    def _detect_explicit(
        self,
        sessions: list[SessionDocument],
    ) -> list[SessionRelationship]:
        """Detect explicit relationships from adapter metadata.
        
        Currently only OpenCode provides parent_id.
        """
        relationships = []
        
        for session in sessions:
            if session.parent_id:
                relationships.append(SessionRelationship(
                    from_session=session.parent_id,
                    to_session=session.session_id,
                    relationship_type="continuation",
                    confidence=1.0,
                    detected_by="explicit",
                    reasons=["parent_id_from_adapter"],
                    created_at=session.session_start,
                ))
        
        return relationships
    
    def _detect_heuristic(
        self,
        sessions: list[SessionDocument],
        vectors: dict[str, list[float]] | None = None,
    ) -> list[SessionRelationship]:
        """Detect heuristic relationships using signals.
        
        Optimized algorithm:
        1. Group sessions by project
        2. Sort each project's sessions by start time
        3. Compare each session only with later sessions (forward-only)
        4. Skip pairs that fail hard filters
        5. Score remaining pairs with weighted signals
        6. Classify relationship type based on scores and metadata
        """
        relationships = []
        
        # Group by project
        by_project = defaultdict(list)
        for session in sessions:
            by_project[session.project_name].append(session)
        
        for project, proj_sessions in by_project.items():
            # Sort by start time
            sorted_sessions = sorted(proj_sessions, key=lambda s: s.session_start)
            
            # Compare each session with later sessions
            for i, older in enumerate(sorted_sessions):
                for j in range(i + 1, len(sorted_sessions)):
                    newer = sorted_sessions[j]
                    
                    # Hard filters
                    if not self._passes_hard_filters(older, newer):
                        continue
                    
                    # Score
                    score, reasons = self._score_pair(older, newer, vectors)
                    
                    if score >= self.HEURISTIC_THRESHOLD:
                        rel_type = self._classify_relationship(older, newer, score)
                        relationships.append(SessionRelationship(
                            from_session=older.session_id,
                            to_session=newer.session_id,
                            relationship_type=rel_type,
                            confidence=score,
                            detected_by="heuristic",
                            reasons=reasons,
                            created_at=newer.session_start,
                        ))
        
        return relationships
    
    def _passes_hard_filters(
        self,
        older: SessionDocument,
        newer: SessionDocument,
    ) -> bool:
        """Check if a pair passes hard exclusion filters."""
        # Same session
        if older.session_id == newer.session_id:
            return False
        
        # Time gap > 30 days
        time_diff = newer.session_start - older.session_start
        if time_diff > 30 * 24 * 3600 * 1000:  # 30 days in ms
            return False
        
        # No domain overlap
        older_domains = set(older.domains)
        newer_domains = set(newer.domains)
        if not (older_domains & newer_domains):
            return False
        
        return True
    
    def _score_pair(
        self,
        older: SessionDocument,
        newer: SessionDocument,
        vectors: dict[str, list[float]] | None,
    ) -> tuple[float, list[str]]:
        """Score a pair of sessions with weighted signals.
        
        Returns:
            Tuple of (score, reasons).
        """
        score = 0.0
        reasons: list[str] = []
        
        # 1. Temporal proximity (< 24 hours)
        time_diff = newer.session_start - older.session_start
        if time_diff < 24 * 3600 * 1000:  # 24 hours in ms
            score += self.TEMPORAL_WEIGHT
            reasons.append("temporal_proximity")
        
        # 2. File overlap (> 30% shared files)
        older_files = set(older.files_edited + older.files_read)
        newer_files = set(newer.files_edited + newer.files_read)
        if older_files and newer_files:
            intersection = len(older_files & newer_files)
            union = len(older_files | newer_files)
            overlap = intersection / union if union > 0 else 0
            if overlap > 0.3:
                score += self.FILE_OVERLAP_WEIGHT
                reasons.append("file_overlap")
        
        # 3. Task similarity (embedding cosine > 0.8)
        if vectors and older.session_id in vectors and newer.session_id in vectors:
            sim = self._cosine_similarity(
                vectors[older.session_id],
                vectors[newer.session_id]
            )
            if sim > 0.8:
                score += self.EMBEDDING_WEIGHT
                reasons.append("task_similarity")
        
        # 4. Same workspace
        if older.project_root and older.project_root == newer.project_root:
            score += self.WORKSPACE_WEIGHT
            reasons.append("same_workspace")
        
        # 5. Resolution status boost
        older_resolved = self._is_resolved(older)
        newer_resolved = self._is_resolved(newer)
        if not older_resolved and newer_resolved:
            score += 0.10
            reasons.append("resolution_progression")
        
        return min(score, 1.0), reasons
    
    def _classify_relationship(
        self,
        older: SessionDocument,
        newer: SessionDocument,
        score: float,
    ) -> str:
        """Classify the relationship type based on session metadata."""
        # Check if newer supersedes older
        older_resolved = self._is_resolved(older)
        newer_resolved = self._is_resolved(newer)
        
        if not older_resolved and newer_resolved:
            # Newer solved what older couldn't
            return "supersession"
        
        if newer.task_raw and older.task_raw:
            # Check if task_raw indicates continuation
            newer_lower = newer.task_raw.lower()
            older_lower = older.task_raw.lower()
            
            continuation_keywords = ["continue", "resume", "pick up", "follow up"]
            if any(kw in newer_lower for kw in continuation_keywords):
                return "continuation"
            
            # Check for branching (parallel work on same topic)
            if score > 0.85 and self._significant_task_overlap(older_lower, newer_lower):
                return "branch"
        
        return "related"
    
    def _is_resolved(self, session: SessionDocument) -> bool:
        """Check if a session appears resolved."""
        return session.quality_tag.value == "solution_found"
    
    def _significant_task_overlap(self, task_a: str, task_b: str) -> bool:
        """Check if two tasks share significant vocabulary."""
        words_a = set(task_a.lower().split())
        words_b = set(task_b.lower().split())
        
        # Remove common stop words
        stop_words = {"the", "a", "an", "is", "was", "in", "on", "at", "to", "for", 
                      "of", "and", "or", "but", "with", "from", "by", "as"}
        words_a -= stop_words
        words_b -= stop_words
        
        if not words_a or not words_b:
            return False
        
        overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
        return overlap > 0.5
    
    @staticmethod
    def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        dot = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = math.sqrt(sum(a * a for a in vec1))
        mag2 = math.sqrt(sum(b * b for b in vec2))
        
        if mag1 == 0 or mag2 == 0:
            return 0.0
        
        return dot / (mag1 * mag2)
```

**Export:** Add to `src/smartfork/indexer/__init__.py`

---

## 3. Modified Components

### 3.1 `IndexIntelligence` (REFACTORED)

**File:** `src/smartfork/indexer/intelligence.py`  
**Current:** 5 separate LLM calls per session (title, summary, tags, quality, propositions)  
**New:** 1 structured LLM call per session

```python
# REPLACE the entire IndexIntelligence class with:

class IndexIntelligence:
    """Enriches session documents with LLM-powered intelligence.
    
    When LLM is available: uses 1 structured call for all enrichment.
    When LLM is unavailable: falls back to keyword-based heuristics.
    """
    
    def __init__(self, llm: object | None = None) -> None:
        self.llm = llm
    
    def enrich(
        self,
        session: SessionDocument,
        progress_callback: Callable[[ProgressEvent], None] | None = None,
    ) -> SessionDocument:
        """Enrich a single session."""
        if progress_callback:
            progress_callback(ProgressEvent(
                phase="enriching",
                enrich_step="structured",
                enrich_done=0,
                enrich_total=1,
            ))
        
        if self.llm:
            try:
                enrichment = self._llm_enrich_structured(session)
                session.task_raw = enrichment.title
                session.summary_doc = enrichment.summary
                session.quality_tag = QualityTag(enrichment.quality_tag)
                session.tech_tags = enrichment.tech_tags
            except Exception as e:
                logger.warning(f"LLM enrichment failed, using fallback: {e}")
                self._fallback_enrich(session)
        else:
            self._fallback_enrich(session)
        
        if progress_callback:
            progress_callback(ProgressEvent(
                phase="enriching",
                enrich_step="done",
                enrich_done=1,
                enrich_total=1,
            ))
        
        return session
    
    def _llm_enrich_structured(self, session: SessionDocument) -> SessionEnrichment:
        """Single structured LLM call for all enrichment."""
        from smartfork.models.enrichment import SessionEnrichment
        
        context = f"""
Task: {session.task_raw}
Files: {', '.join(session.files_edited[:5])}
Reasoning snippets:
"""
        for i, reasoning in enumerate(session.reasoning_docs[:2]):
            context += f"\n{i+1}. {reasoning[:200]}"
        
        prompt = f"""Analyze this coding session and return structured JSON:

{context}

Return this exact JSON structure:
{{
    "title": "Short descriptive title (max 80 chars)",
    "summary": "3-sentence summary of what happened",
    "quality_tag": "solution_found" or "dead_end" or "partial" or "reference",
    "tech_tags": ["list", "of", "technologies"]
}}

Rules:
- title: Max 80 characters, descriptive
- summary: Exactly 3 sentences covering task, approach, outcome
- quality_tag: Choose the best fit
- tech_tags: Include frameworks, libraries, languages mentioned
"""
        
        # Use structured output if available
        if hasattr(self.llm, 'complete_structured'):
            return self.llm.complete_structured(
                prompt,
                output_schema=SessionEnrichment,
                max_tokens=300,
            )
        else:
            # Fallback to text parsing
            result = self.llm.complete(prompt, max_tokens=300)
            return self._parse_enrichment_result(str(result))
    
    def _parse_enrichment_result(self, text: str) -> SessionEnrichment:
        """Parse text result into SessionEnrichment."""
        import json
        try:
            # Try to find JSON in the response
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                return SessionEnrichment(
                    title=data.get("title", "Untitled")[:80],
                    summary=data.get("summary", "")[:500],
                    quality_tag=data.get("quality_tag", "partial"),
                    tech_tags=data.get("tech_tags", []),
                )
        except (json.JSONDecodeError, ValueError):
            pass
        
        # Ultimate fallback
        return SessionEnrichment(
            title="Untitled Session",
            summary="No summary available.",
            quality_tag="partial",
            tech_tags=[],
        )
    
    def _fallback_enrich(self, session: SessionDocument) -> None:
        """Heuristic enrichment without LLM."""
        # Title
        if not session.task_raw or session.task_raw == "Untitled Session":
            session.task_raw = _extract_title_fallback(session.task_raw)
        
        # Summary
        session.summary_doc = _extract_summary_fallback(
            session.reasoning_docs, session.task_raw
        )
        
        # Quality
        session.quality_tag = _classify_quality(
            session.task_raw, session.reasoning_docs
        )
        
        # Tech tags
        all_files = session.files_edited + session.files_read + session.files_mentioned
        session.tech_tags = _extract_tech_tags(session.task_raw, all_files)
```

**Key changes:**
- Remove `_llm_title()`, `_llm_summary()`, `_llm_tech_tags()`, `_llm_quality()`, `_llm_propositions()`
- Replace with single `_llm_enrich_structured()`
- Remove propositions entirely (unused feature)
- Keep fallback functions (they still work)

---

### 3.2 `EmbeddingPipeline` (REWRITTEN)

**File:** `src/smartfork/indexer/embedder.py`  
**Current:** ChromaDB chunk storage, 5 vectors per session  
**New:** sqlite-vec session storage, 1 vector per session

```python
"""Embedding pipeline for SmartFork v2 — session-level embedding with sqlite-vec."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger

from smartfork.indexer.metadata_store import MetadataStore
from smartfork.indexer.session_essence_builder import SessionEssenceBuilder
from smartfork.models.session import SessionDocument
from smartfork.providers.protocols import EmbeddingProvider


class EmbeddingPipeline:
    """Orchestrates session embedding and sqlite-vec storage.
    
    Replaces the old chunk-based ChromaDB pipeline with session-level
    embeddings stored directly in the SQLite database via sqlite-vec.
    """
    
    def __init__(
        self,
        embedder: EmbeddingProvider,
        store: MetadataStore | None = None,
        essence_builder: SessionEssenceBuilder | None = None,
    ) -> None:
        self.embedder = embedder
        self.store = store or MetadataStore()
        self.essence_builder = essence_builder or SessionEssenceBuilder()
    
    def embed_session(self, session: SessionDocument) -> list[float] | None:
        """Embed a single session and store in sqlite-vec.
        
        Args:
            session: The session to embed.
        
        Returns:
            The embedding vector, or None if embedding failed.
        """
        try:
            # Build essence
            essence = self.essence_builder.build_essence(session)
            
            # Embed with instruction prefix (Ollama supports this)
            if hasattr(self.embedder, '_build_prompt'):
                # Ollama embedder with instruction awareness
                text = self.essence_builder.build_essence_with_instruction(session)
            else:
                text = essence
            
            # Get embedding
            vector = self.embedder.embed(text)
            
            # Store in sqlite-vec
            self.store.store_vector(session.session_id, vector)
            
            return vector
            
        except Exception as e:
            logger.error(f"Failed to embed session {session.session_id}: {e}")
            return None
    
    def embed_sessions_batch(
        self,
        sessions: list[SessionDocument],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, list[float]]:
        """Embed multiple sessions in batch.
        
        Args:
            sessions: List of sessions to embed.
            progress_callback: Optional callback(current, total).
        
        Returns:
            Dict of session_id → vector for successful embeddings.
        """
        vectors = {}
        total = len(sessions)
        
        # Build all essences first
        essences = []
        for session in sessions:
            essence = self.essence_builder.build_essence(session)
            essences.append(essence)
        
        # Batch embed if supported
        if hasattr(self.embedder, 'embed_batch'):
            try:
                all_vectors = self.embedder.embed_batch(essences)
                for session, vector in zip(sessions, all_vectors):
                    self.store.store_vector(session.session_id, vector)
                    vectors[session.session_id] = vector
                    if progress_callback:
                        progress_callback(len(vectors), total)
                return vectors
            except Exception as e:
                logger.warning(f"Batch embed failed, falling back to sequential: {e}")
        
        # Sequential fallback
        for i, session in enumerate(sessions):
            vector = self.embed_session(session)
            if vector:
                vectors[session.session_id] = vector
            if progress_callback:
                progress_callback(i + 1, total)
        
        return vectors
    
    def embed_query(self, query: str) -> list[float]:
        """Embed a search query.
        
        Args:
            query: The search query text.
        
        Returns:
            Query embedding vector.
        """
        return self.embedder.embed_query(query)
```

**Key changes:**
- Remove ChromaDB dependency entirely
- Remove `embed_and_store(chunks)` method
- Add `embed_session(session)` for single session
- Add `embed_sessions_batch(sessions)` for batch processing
- Store vectors in sqlite-vec via MetadataStore
- Remove `collection`, `persist_dir`, `batch_size` (ChromaDB-specific)

---

### 3.3 `FullIndexer` (MODIFIED)

**File:** `src/smartfork/indexer/indexer.py`  
**Changes:**

1. Replace chunking step with essence building
2. Replace chunk embedding with session embedding
3. Add relationship detection after all sessions stored
4. Remove ChromaDB error handling

```python
# In the main indexing loop (around line 207-270):

# OLD CODE:
# chunks = self.chunker.chunk(doc)
# stats["chunked"] += len(chunks)
# if self.embedder:
#     stored = self.embedder.embed_and_store(chunks, ...)

# NEW CODE:
# Build essence (no chunking)
essence = SessionEssenceBuilder().build_essence(doc)
stats["chunked"] = 1  # One "unit" per session now

# Embed session (not chunks)
if self.embedder:
    vector = self.embedder.embed_session(doc)
    if vector:
        stats["stored"] += 1

# Enrich (1 call instead of 5)
self.intelligence.enrich(doc, progress_callback=enrich_progress)

# Store metadata (same as before)
self.store.upsert_session(doc)
```

**After all sessions are processed, add relationship detection:**

```python
# NEW: Relationship detection (runs after all sessions stored)
if self.store and parsed_sessions:
    logger.info("Detecting session relationships...")
    detector = RelationshipDetector(self.store)
    
    # Group by project
    by_project = defaultdict(list)
    for _, doc in parsed_sessions:
        by_project[doc.project_name].append(doc)
    
    # Get vectors for similarity scoring
    vectors = {}
    if self.embedder:
        for _, doc in parsed_sessions:
            vec = self.store.get_vector(doc.session_id)
            if vec:
                vectors[doc.session_id] = vec
    
    # Detect relationships per project
    total_rels = 0
    for project, sessions in by_project.items():
        rels = detector.detect_all(sessions, vectors)
        for rel in rels:
            self.store.add_relationship(rel)
            total_rels += 1
    
    logger.info(f"Detected {total_rels} relationships across {len(by_project)} projects")
    stats["relationships"] = total_rels
```

---

## 4. Updated SupersessionDetector

**File:** `src/smartfork/indexer/supersession.py`  
**Fixes:**
1. O(n²) optimization (sort + forward-only comparison)
2. Lower no-vector threshold (currently maxes at 0.65 vs threshold 0.85)

```python
# In SupersessionDetector class:

# REPLACE find_supersessions() method:

def find_supersessions(
    self,
    sessions: list[SessionDocument],
    vectors: dict[str, list[float]] | None = None,
    intent: str = "default",
) -> list[tuple[str, str, float]]:
    """Find all supersession relationships (OPTIMIZED).
    
    Algorithm:
    1. Group sessions by project
    2. Sort each group by start time
    3. Compare only forward (i < j, where j is newer)
    4. Skip reverse comparisons entirely
    
    Complexity: O(n log n) for sort + O(n²/2) for comparisons per project.
    vs original O(n²) for all permutations including reverse order.
    """
    threshold = self.thresholds.get(intent, self.thresholds["default"])
    results: list[tuple[str, str, float]] = []
    
    # Group by project
    by_project = defaultdict(list)
    for session in sessions:
        by_project[session.project_name].append(session)
    
    for project, proj_sessions in by_project.items():
        # Sort by start time
        sorted_sessions = sorted(proj_sessions, key=lambda s: s.session_start)
        
        # Compare each session only with later sessions
        for i, older in enumerate(sorted_sessions):
            for j in range(i + 1, len(sorted_sessions)):
                newer = sorted_sessions[j]
                
                # Get vectors if available
                older_vec = vectors.get(older.session_id) if vectors else None
                newer_vec = vectors.get(newer.session_id) if vectors else None
                
                score = self.detect_supersession(older, newer, older_vec, newer_vec)
                
                if score >= threshold:
                    results.append((older.session_id, newer.session_id, score))
    
    return results

# FIX detect_supersession() threshold issue:

def detect_supersession(...) -> float:
    # ... existing code ...
    
    # CURRENT BUG: Without vectors, max score is ~0.65 (0.5 + 0.1 + 0.05)
    # But default threshold is 0.85, so it NEVER triggers without vectors.
    
    # FIX: When vectors are absent, boost more aggressively
    # OR: Lower base score when no vectors
    
    similarity = 0.5  # base
    
    if older_vector and newer_vector:
        vec_sim = _cosine_similarity(older_vector, newer_vector)
        similarity = 0.3 + (0.7 * vec_sim)
    else:
        # No vectors available: boost based on stronger text signals
        # This is a heuristic when vectors aren't available
        similarity = 0.6  # Higher base when no vectors (was 0.5)
    
    # Boost if older has low resolution status
    older_resolved = self._check_resolution(older)
    if not older_resolved:
        similarity += 0.15  # Increased from 0.1
    
    # Boost if newer has high resolution status
    newer_resolved = self._check_resolution(newer)
    if newer_resolved:
        similarity += 0.10  # Increased from 0.05
    
    return min(similarity, 1.0)
```

**Alternative fix (cleaner):** Make vectors mandatory for supersession detection. If no vectors, skip supersession detection entirely (heuristic relationships will still be detected by RelationshipDetector).

---

## 5. Deliverables

| # | Deliverable | File | Acceptance Criteria |
|---|-------------|------|-------------------|
| 1 | `SessionEssenceBuilder` | `indexer/session_essence_builder.py` | Produces ~500-5000 token essence |
| 2 | `RelationshipDetector` | `indexer/relationship_detector.py` | Detects explicit + heuristic relationships |
| 3 | Refactored `IndexIntelligence` | `indexer/intelligence.py` | 1 structured call, no propositions |
| 4 | Rewritten `EmbeddingPipeline` | `indexer/embedder.py` | No ChromaDB, sqlite-vec only |
| 5 | Updated `FullIndexer` | `indexer/indexer.py` | Session-level embed, relationship detection |
| 6 | Fixed `SupersessionDetector` | `indexer/supersession.py` | O(n²) optimized, threshold fixed |
| 7 | Tests | `tests/indexer/` | All new components tested |

---

## 6. Dependencies

### Depends on:
- Phase 1: `SessionRelationship`, `SessionEnrichment` models, sqlite-vec schema
- Phase 2: `parent_id` available in `SessionDocument`

### Blocks:
- Phase 4: Search needs vectors in sqlite-vec and relationships in DB
- Phase 5: Multi-session needs relationship chains

---

## 7. Notes for Implementer

1. **ChromaDB removal:** After this phase, no code should reference `chromadb`. Check all imports.
2. **Vector dimensions:** Ensure all vectors are 1024d (to match both Ollama and mxbai models).
3. **sqlite-vec API:** The exact SQL syntax for vector search may differ. Check the sqlite-vec documentation for `vss_search` parameters.
4. **Relationship detection scope:** Only run within a project. Cross-project relationships are noise.
5. **Progress reporting:** Update progress callbacks to show "relationship detection" phase.
6. **Memory:** For 300 sessions, relationship detection is trivial. For 10K sessions, the O(n²) per project still needs optimization (use approximate methods).
