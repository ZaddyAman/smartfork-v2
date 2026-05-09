# SmartFork v2 — Supersession Detection (Layer 4)

> **Design:** Detects when a newer session CORRECTS or SUPERSEDES an older one.
> **Zero LLM.** Pure cosine similarity + regex-based resolution detection.

---

## SupersessionDetector

**File:** `src/smartfork/indexer/supersession.py`

### Core Algorithm

```
When a new session is indexed:
  1. Get its embedding from ChromaDB
  2. Find candidate sessions: same project, older timestamp, overlapping domains
  3. Compute cosine similarity between new embedding and each candidate
  4. If similarity > threshold → mark as superseding
  5. Detect resolution status via regex on last reasoning block
```

---

### Similarity Thresholds

```python
SIMILARITY_THRESHOLDS = {
    "error_recall": 0.82,      # Bugs need high precision
    "decision_hunting": 0.80,  # Decisions are semantically distinct
    "default": 0.85,           # Conservative default
}
```

Different intents need different thresholds. Error recall is lowest because bug-fix sessions often overlap.

---

### Candidate Filtering

```python
def find_candidates(new_session: SessionDocument, 
                    existing_sessions: List[SessionDocument]) -> List[SessionDocument]:
```

**Filters (ALL must pass):**
1. Same project_name
2. At least ONE overlapping domain
3. Older timestamp (candidate.session_start < new_session.session_start)
4. Different session_id (not comparing to self)
5. Task description > 5 words (skip empty tasks)
6. Not "unknown_project" (skip unclassified)

---

### Cosine Similarity

```python
def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors. Range 0.0-1.0."""
```

Uses embeddings pre-stored in ChromaDB — zero Ollama calls at detection time.

---

### Resolution Status Detection

Runs regex on the LAST reasoning block of each session.

```python
RESOLUTION_PATTERNS = [
    (r'\bfixed\s+(?:the|this|that|it|bug|error|issue)', 1.0),
    (r'\bresolved\s+(?:the|this|that|it|bug|error|issue)', 1.0),
    (r'\bworking\s+now\b', 1.0),
    (r'\bsuccessfully\s+(?:implemented|completed|fixed|tested)\b', 1.0),
    (r'\bpasses?\s+(?:the|all)\s+tests?\b', 1.0),
]

PROBLEM_PATTERNS = [
    (r'\bstill\s+broken\b', 1.0),
    (r'\bnot\s+working\b', 1.0),
    (r'\bfailed\s+(?:to|again)\b', 1.0),
    (r'\bissue\s+persists\b', 1.0),
    (r'\bTODO\b', 0.5),
]
```

**Negation handling — critical:**
Check if "not", "no", "without", "isn't", "don't", "doesn't", "wasn't", "hasn't", "never" appears in the same sentence BEFORE the matched pattern.

"is not working now" → PROBLEM (negation detected)
"working now" → RESOLUTION (no negation)

---

### Storing Results

```python
class SupersessionLink:
    superseded_id: str
    superseding_id: str
    confidence: float      # 0.0 to 1.0
    detected_at: int       # ms
    reason: str            # e.g., "High similarity (0.89) + same project + overlapping domains"
```

Stored in `session_supersessions` table via MetadataStore.

---

## SupersessionAnnotator

**File:** `src/smartfork/search/supersession_annotator.py`

Post-search processing that adds indicators to result cards.

```python
def annotate_results(results: List[ResultCard], 
                     store: MetadataStore) -> List[ResultCard]:
```

**For each result:**
1. Check if it's superseded → add `⚠ Superseded by {id[:8]}...`
2. Check if it supersedes something → add `🔄 Fixes earlier attempt`
3. Follow chain to find LATEST session (max depth 5)
4. Apply additive boost (+0.15) to superseding sessions
5. Sort by score descending
6. Return annotated results

**NEVER silently replace a result with its superseding version.** Only add visual indicators.

---

### Chain Following

```python
def get_latest_in_chain(session_id: str, store: MetadataStore, 
                        depth: int = 0) -> str:
    """Follow supersession chain to find latest session. Max depth 5."""
    if depth > 5:
        return session_id
    superseding = store.get_superseding_sessions(session_id)
    if not superseding:
        return session_id  # This IS the latest
    # superseding is List[(session_id, confidence, detected_at)] sorted
    return get_latest_in_chain(superseding[0][0], store, depth + 1)
```

---

## Edge Cases

- **Self-supersession**: Detector must skip comparing session to itself
- **Circular chains**: Max depth 5 prevents infinite loops in chain following
- **Unknown project**: Sessions with project_name="unknown_project" are skipped
- **Short tasks**: Tasks < 5 words are skipped (too vague to meaningfully compare)
- **Empty reasoning**: If no reasoning blocks, resolution_status="unknown"

---

## Testing

- Test with two sessions on same bug (should detect supersession)
- Test with unrelated sessions (should NOT detect)
- Test negation handling ("not working" vs "working")
- Test circular chain prevention
- Test chain following to depth 5
- Test with empty reasoning blocks
