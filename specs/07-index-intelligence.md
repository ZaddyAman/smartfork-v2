# SmartFork v2 — Index-Time Intelligence (Layer 3)

> **Design:** LLM-powered enrichment that runs ONCE per session at index time. Benefits every future search.
> **Default LLM:** Local Ollama (qwen2.5-coder:7b). Cloud opt-in.
> **Fallback:** All steps degrade gracefully when LLM is unavailable.

---

## IndexIntelligence

**File:** `src/smartfork/indexer/intelligence.py`

```python
class IndexIntelligence:
    def __init__(self, llm: LLMProvider): ...
    def enrich(self, doc: SessionDocument) -> SessionDocument: ...
    def enrich_batch(self, docs: List[SessionDocument], 
                     on_progress=None) -> List[SessionDocument]: ...
```

---

## Step 1: Session Titling

**Cost:** ~1 second, ~50 tokens

**Prompt:**
```
Based on this coding session, generate a 5-8 word descriptive title.
Session task: {task_raw[:200]}
Files edited: {', '.join(files_edited[:5])}
Return ONLY the title, nothing else.
```

**Post-processing:** Strip quotes, truncate to 80 chars.

**Fallback:** First 60 chars of task_raw, cleaned.

---

## Step 2: Session Summarization

**Cost:** ~3 seconds, ~200 tokens

**Prompt:**
```
Summarize this coding session in exactly 3 sentences:
1. What was built, fixed, or investigated?
2. What approach or key decisions were made?
3. What was the outcome?

Session: {task_raw}
Key files: {', '.join(files_edited[:5])}
Duration: {duration_minutes} min
Key exchanges: {reasoning_docs[:3]}

Return only the 3 sentences, no labels or bullet points.
```

**Post-processing:**
- Remove `<think>`, `</think>`, markdown artifacts
- Ensure exactly 3 sentences (split by `. `, take first 3)
- If LLM returns garbage: use fallback

**Fallback:** First 2 reasoning blocks, truncated.

---

## Step 3: Quality Tagging

**Cost:** ~2 seconds, ~50 tokens

**Output:** One of `SOLUTION_FOUND`, `DEAD_END`, `PARTIAL`, `REFERENCE`

**Prompt:**
```
Classify this coding session's outcome as EXACTLY one of:
- SOLUTION_FOUND: Working code was produced, tests pass, task completed
- DEAD_END: Session abandoned without resolution, approach was wrong
- PARTIAL: Some progress made but incomplete, has useful fragments
- REFERENCE: Setup, config, or exploration without a specific solution

Evidence — Summary: {summary_doc}
Evidence — Last exchanges: {last_2_reasoning_blocks}

Return ONLY the tag name, nothing else.
```

**Post-processing:** Map LLM output to QualityTag enum. If ambiguous, default to UNKNOWN.

**Fallback:** UNKNOWN

---

## Step 4: Tech Tagging

**Cost:** ~2 seconds, ~80 tokens

**Output:** List of technology names detected in the session

**Prompt:**
```
Extract specific technologies, frameworks, libraries, and tools from this session.
Return as comma-separated names only (e.g., "FastAPI, JWT, PostgreSQL, Docker").

Session: {task_raw[:200]}
Files: {', '.join(files_edited[:10])}
Summary: {summary_doc}
```

**Post-processing:**
- Split by comma, strip whitespace
- Remove duplicates (case-insensitive)
- Remove entries > 30 chars (noise)
- Merge with languages from file extensions
- Return sorted unique list

**Fallback:** Only file-extension-based language detection.

---

## Step 5: Proposition Extraction

**Cost:** ~5 seconds per session (3 reasoning blocks × 1 call each), ~300 tokens

**Output:** Atomic factual statements about the session

**Prompt (per reasoning block, max 3 blocks):**
```
Extract key technical facts from this text. One fact per line. No bullet points.
Keep each fact under 200 characters. Skip opinions and questions.

Text: {reasoning_block[:500]}
```

**Post-processing:**
- Split by newlines
- Filter: len 10-200 chars, not containing "?", not starting with "I think", not code
- Deduplicate
- Max 10 propositions per session

**Fallback:** Extract sentences containing tech keywords (FastAPI, JWT, Docker, etc.) via regex.

---

## Batch Processing

```python
def enrich_batch(self, docs: List[SessionDocument], 
                 on_progress=None) -> List[SessionDocument]:
    enriched = []
    for i, doc in enumerate(docs):
        try:
            enriched.append(self.enrich(doc))
        except Exception:
            enriched.append(doc)  # Return unenriched on failure
        if on_progress:
            on_progress(i + 1, len(docs))
    return enriched
```

---

## Performance Design

- Processed AFTER embedding (so search works even without enrichment)
- Batch mode for initial indexing
- Individual mode for incremental (watcher)
- All steps run sequentially per session to minimize context switching
- Token budgets: titling(50) + summary(200) + quality(50) + tech(80) + propositions(300) = ~680 tokens/session
- With Ollama qwen2.5-coder:7b: ~10-15 seconds per session on GPU, ~30-60 seconds on CPU
- Skip enrichment if `config.auto_tag` and `config.auto_summarize` are False

---

## Testing

- Test each step independently with mock LLM
- Test full enrichment pipeline
- Test fallback behavior when LLM raises
- Test batch with empty list
- Test with session that has no reasoning blocks
- Verify QualityTag is always a valid enum value
- Verify tech tags don't contain duplicates
