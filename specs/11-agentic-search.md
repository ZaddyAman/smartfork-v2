# SmartFork v2 — Agentic Search (Layer 7, Path B)

> **Design:** LLM-orchestrated multi-step search. Premium path. Requires Ollama (local, free) or cloud API key.
> **Framework:** PydanticAI (orchestration) + Smolagents (parallel workers)
> **Max LLM calls:** 7 (1 understand + 3 evaluate + 2 refine + 1 synthesize)
> **Target latency:** <10 seconds with local Ollama

---

## AgenticSearchEngine

**File:** `src/smartfork/search/agentic.py`

```python
class AgenticSearchEngine:
    def __init__(self, llm: LLMProvider, embedder: EmbeddingProvider,
                 chroma_client, deterministic: DeterministicSearchEngine): ...
    
    async def search(self, query: str, n_results: int = 5,
                     max_refinement_rounds: int = 3) -> List[ResultCard]: ...
```

---

## Architecture

```
User Query
    │
    ▼
Step 1: QUERY UNDERSTANDING (PydanticAI agent, 1 LLM call)
    │  Expands query → structured intent + 3-5 search variants
    ▼
Step 2: MULTI-VARIANT SEARCH (Smolagents workers, 0 LLM calls, PARALLEL)
    │  3-5 workers, each searches with different variant + strategy
    │  Collect & deduplicate → ~25 candidates
    ▼
Step 3: RESULT EVALUATION (PydanticAI agent, 1-2 LLM calls)
    │  Agent reads top candidates, evaluates relevance, re-ranks
    ▼
Step 4: REFINEMENT LOOP (conditional, max 3 rounds)
    │  If no candidate > threshold: generate new strategies → go to Step 2
    │  If still nothing after 3 rounds: return "No matching sessions found"
    ▼
Step 5: RECOMMENDATION SYNTHESIS (PydanticAI agent, 1 LLM call)
    │  Natural language explanation for each result
    ▼
Result Cards with explanations
```

---

## Step 1: Query Understanding

**PydanticAI Agent:**

```python
query_agent = Agent(
    model=llm_provider,  # Ollama, Anthropic, or OpenAI
    result_type=QueryDecomposition,
    system_prompt="""
    You analyze developer queries about their coding session history.
    Given a query, produce a QueryDecomposition with:
    - intent: what the user is trying to do
    - core_goal: the main thing they want
    - entities: key names, terms, file names
    - search_variants: 3-5 alternative queries
    - what_should_match: what good results would contain
    - what_should_not_match: what to avoid
    """
)
```

**Output:** `QueryDecomposition` with 3-5 search variants.

---

## Step 2: Multi-Variant Parallel Search

**Smolagents Code Agents — 5 workers in parallel:**

```python
WORKER_STRATEGIES = [
    ("vector_only", lambda q: vector_search(q, n=30)),
    ("bm25_only", lambda q: bm25_search(q, n=30)),
    ("hybrid_balanced", lambda q: hybrid_search(q, alpha=0.5, n=30)),
    ("hybrid_bm25_heavy", lambda q: hybrid_search(q, alpha=0.7, n=30)),
    ("metadata_focused", lambda q: metadata_filtered_search(q, n=30)),
]
```

Each worker receives one search variant + one strategy. Workers are Smolagents `CodeAgent` instances that write Python to execute their search.

```python
async def _parallel_search(self, variants: List[str]) -> List[SearchResult]:
    tasks = []
    for variant in variants:
        for strategy_name, strategy_fn in WORKER_STRATEGIES:
            tasks.append(self._run_worker(variant, strategy_fn))
    results = await asyncio.gather(*tasks)
    return self._deduplicate(results)
```

**Collect & Deduplicate:**
- Gather results from all workers
- Group by session_id
- Keep highest score per session
- Return top ~25 candidates

---

## Step 3: Result Evaluation

**PydanticAI Agent:**

```python
eval_agent = Agent(
    model=llm_provider,
    result_type=List[EvaluatedResult],
    system_prompt="""
    You evaluate search result relevance.
    For each candidate, read the title and summary and decide if it matches.
    Rate 0-10 where 10 is perfect match.
    Explain in one sentence why.
    """
)
```

Agent receives top 25 candidates (title + summary only, NOT full transcript). Re-ranks by relevance.

```python
class EvaluatedResult:
    session_id: str
    relevance_score: float  # 0-10
    explanation: str        # One sentence
```

---

## Step 4: Refinement Loop

```python
async def search(self, query, max_rounds=3):
    variants = await self._understand_query(query)
    
    for round_num in range(max_rounds):
        candidates = await self._parallel_search(variants)
        evaluated = await self._evaluate(candidates)
        
        top_score = max((e.relevance_score for e in evaluated), default=0)
        
        if top_score >= 7.0:  # Threshold
            return await self._synthesize(evaluated[:5], query)
        
        # Generate new variants based on what failed
        variants = await self._refine_variants(query, evaluated)
    
    # Max rounds reached, nothing good found
    return _empty_result("No matching sessions found. Try broader terms.")
```

**Refinement agent analyzes WHY results failed:**
```
"User asked about race conditions in JWT but all results are about basic JWT setup.
Try variants focused on: concurrency, mutex, thread safety, token refresh conflict"
```

---

## Step 5: Recommendation Synthesis

**PydanticAI Agent:**

```python
synth_agent = Agent(
    model=llm_provider,
    result_type=List[ResultCard],
    system_prompt="""
    You synthesize search results into recommendations.
    For each result, explain WHY it matches the user's needs.
    User query: {query}
    Results: {results_json}
    """
)
```

Output: Ranked ResultCards with `relevance_explanation` populated.

Example:
```
★ Session #1a84 [0.96] — Fixing race condition in auth flow
  This specifically debugs concurrent token refresh causing 401 errors.
  Full working solution with mutex lock at the end.
  
★ Session #7c2d [0.82] — JWT refresh implementation
  Contains the base implementation that #1a84 was fixing.
  Useful for understanding the starting code.
```

---

## Fallback to Deterministic

```python
try:
    results = await agentic.search(query)
except (OllamaNotRunning, PydanticAINotInstalled):
    logger.warning("Agentic search unavailable, falling back to deterministic")
    results = deterministic.search(query)
```

- If Ollama not running → auto-fallback
- If PydanticAI/Smolagents not installed → suggest install
- TUI shows mode badge: "🔍 Agentic" vs "⚡ Deterministic"

---

## Configuration

```python
class AgenticConfig:
    max_refinement_rounds: int = 3
    relevance_threshold: float = 7.0  # 0-10
    parallel_workers: int = 5
    use_cloud_llm: bool = False  # If True, use Anthropic/OpenAI instead of Ollama
```

---

## Testing

- Test each step independently with mock LLM
- Test parallel workers are actually parallel (benchmark vs sequential)
- Test refinement loop exits after max rounds
- Test fallback to deterministic when Ollama down
- Test with query that has no good matches (should return empty gracefully)
- Test PydanticAI structured output validation (invalid output → retry)
