# Phase 5 PRD: Multi-Session Intelligence

**Phase:** 5 of 7  
**Estimated Duration:** 2 days  
**Priority:** High  
**Dependencies:** Phase 4 (Search Pipeline)  

---

## 1. Overview

This phase implements the multi-session intelligence layer: following relationship chains, grouping sessions into timelines, and synthesizing narratives. This is what makes SmartFork unique — it's not just search, it's "show me the story of my work."

**Goal:**
- Build `SessionGraphEngine` for chain following and timeline generation
- Build `MultiSessionSynthesizer` for narrative generation
- Wire supersession/relationship awareness into search results and fork
- Update CLI with `--fast`, `--deep`, `--mode` flags

**Success Criteria:**
- [ ] "what happened with auth" shows timeline of related sessions
- [ ] "continue my API work" follows chain to latest session
- [ ] Superseded sessions show ⬆ annotation and are demoted
- [ ] Latest in chain shows ✅ and is boosted
- [ ] Fork from superseded session warns user
- [ ] Deep mode triggers automatically for temporal/continuation queries

---

## 2. New Components

### 2.1 `SessionGraphEngine` (NEW)

**File:** `src/smartfork/search/session_graph_engine.py`  
**Purpose:** Query the session relationship graph for multi-session insights.

```python
"""Session graph engine for SmartFork v2.

Queries the session_relationships table to follow chains, group
results, and build timelines for multi-session intelligence.
"""

from collections import defaultdict
from typing import Any

from smartfork.indexer.metadata_store import MetadataStore
from smartfork.models.relationship import Chain, TimelineEntry
from smartfork.models.session import SessionDocument


class SessionGraphEngine:
    """Engine for querying and traversing the session relationship graph."""
    
    def __init__(self, store: MetadataStore | None = None) -> None:
        self.store = store or MetadataStore()
        self._chain_cache: dict[str, list[SessionDocument]] = {}
    
    def find_chain(
        self,
        session_id: str,
        direction: str = "forward",
        max_depth: int = 10,
    ) -> list[SessionDocument]:
        """Follow continuation/supersession links from a session.
        
        Args:
            session_id: Starting session ID.
            direction: "forward" (newer) or "backward" (older).
            max_depth: Maximum chain length to follow.
        
        Returns:
            Ordered list of sessions (oldest first if forward from oldest).
        """
        if session_id in self._chain_cache:
            return self._chain_cache[session_id]
        
        chain: list[SessionDocument] = []
        visited: set[str] = set()
        current = session_id
        
        for _ in range(max_depth):
            if current in visited:
                break
            visited.add(current)
            
            # Get session document
            session_data = self.store.get_session(current)
            if not session_data:
                break
            
            # Convert dict to SessionDocument
            from smartfork.indexer.metadata_store import MetadataStore
            session = MetadataStore._row_to_session(session_data)
            
            if direction == "forward":
                chain.append(session)
                # Find next session (this session is superseded by...)
                rels = self.store.get_relationships(current, direction="from")
                continuation = [r for r in rels if r.relationship_type in ("continuation", "supersession")]
                if continuation:
                    current = continuation[0].to_session  # Follow highest confidence
                else:
                    break
            else:
                chain.insert(0, session)
                # Find previous session (this session supersedes...)
                rels = self.store.get_relationships(current, direction="to")
                superseded = [r for r in rels if r.relationship_type in ("continuation", "supersession")]
                if superseded:
                    current = superseded[0].from_session
                else:
                    break
        
        self._chain_cache[session_id] = chain
        return chain
    
    def find_related_sessions(
        self,
        query: str,
        project: str | None = None,
        max_chains: int = 5,
    ) -> list[Chain]:
        """Find all sessions related to a query, grouped into chains.
        
        Args:
            query: The search query.
            project: Optional project filter.
            max_chains: Maximum number of chains to return.
        
        Returns:
            List of Chain objects.
        """
        # Get candidate sessions from search
        from smartfork.search.deterministic import DeterministicSearchEngine
        engine = DeterministicSearchEngine(store=self.store)
        results = engine.search(query, top_k=30, project_filter=project)
        
        # Group by chains
        session_ids = [r["session_id"] for r in results]
        chains: list[Chain] = []
        covered: set[str] = set()
        
        for sid in session_ids:
            if sid in covered:
                continue
            
            # Follow chain backward to find head
            backward = self.find_chain(sid, direction="backward")
            if backward:
                head = backward[0]
            else:
                head_data = self.store.get_session(sid)
                from smartfork.indexer.metadata_store import MetadataStore
                head = MetadataStore._row_to_session(head_data) if head_data else None
            
            if not head:
                continue
            
            # Follow chain forward from head
            forward = self.find_chain(head.session_id, direction="forward")
            
            # Mark all sessions in chain as covered
            for s in forward:
                covered.add(s.session_id)
            
            # Determine chain type
            branches = self.find_branches(head.session_id)
            if branches:
                chain_type = "branched"
            elif len(forward) > 1:
                chain_type = "linear"
            else:
                chain_type = "linear"
            
            chains.append(Chain(
                sessions=forward,
                chain_type=chain_type,
                head_session_id=forward[0].session_id,
                tail_session_id=forward[-1].session_id,
            ))
            
            if len(chains) >= max_chains:
                break
        
        return chains
    
    def get_latest_in_chain(self, chain: list[SessionDocument]) -> SessionDocument:
        """Return the most recent session in a chain."""
        return chain[-1] if chain else None  # type: ignore[return-value]
    
    def find_branches(self, session_id: str) -> list[list[SessionDocument]]:
        """Find all branches diverging from a session.
        
        Returns:
            List of chains, each starting from a branch point.
        """
        branches: list[list[SessionDocument]] = []
        rels = self.store.get_relationships(session_id, direction="from")
        
        for rel in rels:
            if rel.relationship_type == "branch":
                branch_chain = self.find_chain(rel.to_session, direction="forward")
                if branch_chain:
                    branches.append(branch_chain)
        
        return branches
    
    def build_timeline(self, chain: list[SessionDocument]) -> list[TimelineEntry]:
        """Build a structured timeline from a session chain.
        
        Args:
            chain: Ordered list of sessions (oldest first).
        
        Returns:
            List of TimelineEntry objects.
        """
        timeline: list[TimelineEntry] = []
        
        for i, session in enumerate(chain):
            # Determine relationship to next session
            relationship_to_next = None
            if i < len(chain) - 1:
                next_session = chain[i + 1]
                rels = self.store.get_relationships(session.session_id, direction="from")
                for rel in rels:
                    if rel.to_session == next_session.session_id:
                        relationship_to_next = rel.relationship_type
                        break
            
            entry = TimelineEntry(
                session_id=session.session_id,
                timestamp=session.session_start,
                task=session.task_raw[:100] if session.task_raw else "Untitled",
                quality_tag=session.quality_tag.value if hasattr(session.quality_tag, 'value') else str(session.quality_tag),
                summary=session.summary_doc[:200] if session.summary_doc else "",
                relationship_to_next=relationship_to_next,
            )
            timeline.append(entry)
        
        return timeline
```

**Export:** Add to `src/smartfork/search/__init__.py`

---

### 2.2 `MultiSessionSynthesizer` (NEW)

**File:** `src/smartfork/search/multi_session_synthesizer.py`  
**Purpose:** Generate human-readable timeline and narrative from session chains.

```python
"""Multi-session synthesizer for SmartFork v2.

Uses 1 structured LLM call to generate a human-readable narrative,
timeline, and fork suggestion from grouped session chains.
"""

from loguru import logger

from smartfork.models.relationship import Chain, TimelineSummary
from smartfork.models.session import SessionDocument


class MultiSessionSynthesizer:
    """Synthesizes multi-session narratives and timelines."""
    
    def __init__(self, llm: object | None = None) -> None:
        self.llm = llm
    
    def synthesize_timeline(
        self,
        query: str,
        chains: list[Chain],
    ) -> TimelineSummary | None:
        """Generate a timeline summary from session chains.
        
        Args:
            query: The user's original query.
            chains: List of related session chains.
        
        Returns:
            TimelineSummary with narrative, timeline, and suggestions.
        """
        if not chains or not self.llm:
            return None
        
        # Build prompt from chains
        chain_text = self._format_chains_for_prompt(chains)
        
        prompt = f"""Summarize this developer's work journey based on their coding sessions.

User query: "{query}"

Session chains:
{chain_text}

Return structured JSON:
{{
    "narrative": "2-3 paragraph human-readable summary of the journey",
    "resolution_status": "solved" or "ongoing" or "dead_end" or "mixed",
    "suggested_fork_session_id": "session_id_of_latest_relevant_session"
}}

Rules:
- narrative: Tell the story chronologically. What was attempted, what succeeded, what's the current status.
- resolution_status: "solved" if latest session has solution_found, "ongoing" if partial, "dead_end" if all dead_end, "mixed" otherwise.
- suggested_fork_session_id: Recommend the most recent session in the most relevant chain.
"""
        
        try:
            if hasattr(self.llm, 'complete_structured'):
                result = self.llm.complete_structured(
                    prompt,
                    output_schema=TimelineSummary,
                    max_tokens=800,
                    temperature=0.3,
                )
                # Build timeline entries
                primary_chain = chains[0] if chains else None
                if primary_chain:
                    from smartfork.search.session_graph_engine import SessionGraphEngine
                    engine = SessionGraphEngine()
                    timeline = engine.build_timeline(primary_chain.sessions)
                    result.timeline = timeline
                return result
            else:
                result = self.llm.complete(prompt, max_tokens=800)
                return self._parse_timeline_summary(str(result), chains)
        except Exception as e:
            logger.error(f"Multi-session synthesis failed: {e}")
            return None
    
    def _format_chains_for_prompt(self, chains: list[Chain]) -> str:
        """Format chains for LLM prompt."""
        lines: list[str] = []
        for i, chain in enumerate(chains, 1):
            lines.append(f"\nChain {i}:")
            for j, session in enumerate(chain.sessions, 1):
                date = self._format_date(session.session_start)
                quality = session.quality_tag.value if hasattr(session.quality_tag, 'value') else str(session.quality_tag)
                lines.append(
                    f"  {j}. [{date}] {session.task_raw[:80]} "
                    f"(quality: {quality})"
                )
                if session.summary_doc:
                    lines.append(f"     Summary: {session.summary_doc[:150]}")
        return "\n".join(lines)
    
    def _format_date(self, timestamp: int) -> str:
        """Format timestamp as readable date."""
        from datetime import datetime
        return datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")
    
    def _parse_timeline_summary(
        self,
        text: str,
        chains: list[Chain],
    ) -> TimelineSummary:
        """Parse text response into TimelineSummary."""
        import json
        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                primary_chain = chains[0] if chains else None
                timeline = []
                if primary_chain:
                    from smartfork.search.session_graph_engine import SessionGraphEngine
                    engine = SessionGraphEngine()
                    timeline = engine.build_timeline(primary_chain.sessions)
                return TimelineSummary(
                    narrative=data.get("narrative", ""),
                    timeline=timeline,
                    suggested_fork_session_id=data.get("suggested_fork_session_id"),
                    resolution_status=data.get("resolution_status", "unknown"),
                )
        except (json.JSONDecodeError, ValueError):
            pass
        
        return TimelineSummary(
            narrative="Unable to generate narrative.",
            timeline=[],
            resolution_status="unknown",
        )
```

**Export:** Add to `src/smartfork/search/__init__.py`

---

## 3. Wiring Supersession into Search and Fork

### 3.1 Search Results Annotation

**File:** `src/smartfork/search/deterministic.py` — In `_rerank()` method  
**Already covered in Phase 4 PRD.** Key behavior:
- Query `session_relationships` for each result
- If session is superseded: `match_score *= 0.7`, add `⬆ Superseded by...` note
- If session is latest in chain: `match_score += 0.15`, add `✅ Latest in chain` note

### 3.2 Fork Command Warning

**File:** `src/smartfork/cli/commands.py` — In `fork` command  
**Before `ForkAssembler.assemble()`:**

```python
# Check if session is superseded
superseding = store.get_relationships(session_id, direction="to")
supersession_warning = ""
for rel in superseding:
    if rel.relationship_type == "supersession":
        supersession_warning = (
            f"This session was superseded by session '{rel.to_session}' "
            f"(confidence: {rel.confidence:.0%}). Consider forking from the "
            f"latest version instead."
        )
        break

# Assemble handoff with warning
handoff = assembler.assemble(
    doc,
    intent=fork_intent,
    supersession_warning=supersession_warning,
)
```

### 3.3 Fix `ForkAssembler._llm_assemble()`

**File:** `src/smartfork/fork/assembler.py`  
**Current:** `supersession_warning` parameter accepted but NOT included in LLM prompt  
**Fix:** Add warning to LLM prompt

```python
def _llm_assemble(
    self,
    session: SessionDocument,
    intent: ForkIntent,
    user_query: str,
    supersession_warning: str = "",
) -> str:
    """Generate handoff using LLM (includes supersession warning)."""
    context = f"Task: {session.task_raw}\n"
    if session.reasoning_docs:
        context += f"Reasoning: {' '.join(session.reasoning_docs[:2])}\n"
    
    # ADD THIS:
    if supersession_warning:
        context += f"\n⚠️ IMPORTANT: {supersession_warning}\n"
    
    prompt = f"Generate handoff context...\n\n{context}"
    result = self.llm.complete(prompt, max_tokens=1000)
    return str(result).strip()
```

---

## 4. CLI Updates

### 4.1 New Flags

**File:** `src/smartfork/cli/commands.py`  
**Add to `search` command:**

```python
@app.command()
def search(
    query: str,
    project: str | None = None,
    quality: str | None = None,
    top_k: int = 5,
    fast: bool = False,       # NEW: Skip LLM entirely
    deep: bool = False,       # NEW: Force multi-session mode
    mode: str = "auto",       # NEW: "auto" | "fast" | "deterministic" | "deep"
):
    """Search for sessions."""
    # Determine mode
    if fast or mode == "fast":
        search_mode = "fast"
    elif deep or mode == "deep":
        search_mode = "deep"
    else:
        search_mode = "default"  # Auto-detect
    
    # Run search
    orchestrator = SearchOrchestrator(...)
    results = orchestrator.search(
        query=query,
        top_k=top_k,
        project_filter=project,
        quality_filter=quality,
        mode=search_mode,
    )
    
    # Display results
    for card in results:
        display_card(card)
    
    # Deep mode: show timeline panel
    if search_mode == "deep" and hasattr(results[0], 'synthesis') if results else False:
        display_timeline(results[0].synthesis)
```

### 4.2 Result Card Display

**File:** `src/smartfork/cli/commands.py`  
**Update card display to show supersession annotations:**

```python
def display_card(card: ResultCard):
    """Display a search result card."""
    # Title line
    title = f"[{card.rank}] {card.title}"
    if card.supersession_note:
        title += f" · {card.supersession_note}"
    if card.quality_badge:
        title += f" · {card.quality_badge}"
    
    console.print(title)
    
    # Metadata
    meta = f"{card.project_name} · {card.time_ago}"
    console.print(meta, style="dim")
    
    # Excerpt
    if card.excerpt:
        console.print(card.excerpt)
    
    # Tags
    if card.tags:
        console.print(f"Tags: {', '.join(card.tags)}", style="cyan")
    
    # Files
    if card.files_summary:
        console.print(f"Files: {card.files_summary}", style="dim")
    
    # Fork command
    console.print(f"[dim]→ {card.fork_command}[/dim]")
    console.print()
```

---

## 5. Deliverables

| # | Deliverable | File | Acceptance Criteria |
|---|-------------|------|-------------------|
| 1 | `SessionGraphEngine` | `search/session_graph_engine.py` | Chain following, branch detection, timeline |
| 2 | `MultiSessionSynthesizer` | `search/multi_session_synthesizer.py` | Narrative + timeline + fork suggestion |
| 3 | Supersession wiring (search) | `search/deterministic.py` | ⬆/✅ annotations, boost/demote |
| 4 | Supersession wiring (fork) | `fork/assembler.py`, `cli/commands.py` | Warning on superseded fork |
| 5 | CLI flags | `cli/commands.py` | --fast, --deep, --mode |
| 6 | Tests | `tests/search/`, `tests/cli/` | All components tested |

---

## 6. Dependencies

### Depends on:
- Phase 4: SearchOrchestrator with mode routing
- Phase 1: `Chain`, `TimelineEntry`, `TimelineSummary` models

### Blocks:
- Phase 6: Cleanup can now remove old search components safely

---

## 7. Notes for Implementer

1. **Graph caching:** `SessionGraphEngine` caches chains in memory. Clear cache after indexing.
2. **Timeline display:** CLI should render timeline as a Rich Panel with vertical tree lines.
3. **Narrative fallback:** If LLM fails, show raw chain entries instead of empty narrative.
4. **Suggested fork:** Should be the tail of the primary (most relevant) chain.
5. **Confidence display:** Show confidence percentage in supersession warning (e.g., "85%").
