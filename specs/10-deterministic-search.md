# SmartFork v2 — Deterministic Search (Layer 6, Path A)

> **Design:** Fast, free, always available. Zero LLM calls. Target: <500ms.
> **Pipeline:** Parse → Embed → Vector + BM25 → RRF Fusion → Metadata Filter → Rerank → Cards

---

## DeterministicSearchEngine

**File:** `src/smartfork/search/deterministic.py`

```python
class DeterministicSearchEngine:
    def __init__(self, chroma_client, bm25_index, embedder, metadata_store): ...
    
    def search(self, query: str, n_results: int = 10,
               filter_project: str = None, 
               filter_quality: str = None,
               filter_days: int = None) -> List[ResultCard]:
```

---

## Step 1: Query Parsing

**File:** `src/smartfork/search/query_parser.py`

Pure regex + keyword matching. No LLM.

```python
class QueryParser:
    def parse(self, query: str) -> QueryDecomposition:
        # Detect files: *.py, `filename.py`, backtick-wrapped
        # Detect technologies: 90+ hardcoded keywords (JWT, FastAPI, React, Docker...)
        # Detect actions: 80 verbs mapped to 8 intents
        # Detect time: "last week", "recent", "2 days ago" → time_range_days
        # Return QueryDecomposition
```

**90+ technology keywords** defined as a set. Match via word boundaries.

**Intent classification:**
| Action verbs | Intent |
|---|---|
| fix, debug, error, bug, crash, broken, resolve, troubleshoot | error_recall |
| implement, build, create, add, setup, develop, code | implementation_lookup |
| why, decide, choose, decision, approach, alternative | decision_hunting |
| how, pattern, example, snippet, template | pattern_hunting |
| remember, recall, something about, previously | vague_memory |
| last week, yesterday, recent, latest, what was I doing | temporal_lookup |
| continue, resume, pick up, carry on | continuation |

---

## Step 2: Vector Search

```python
def vector_search(query_embedding: List[float], 
                  filter_ids: List[str] = None,
                  n_results: int = 50) -> List[Tuple[str, float]]:
    """Search ChromaDB. Optional pre-filter by session IDs."""
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where={"session_id": {"$in": filter_ids}} if filter_ids else None
    )
    # Deduplicate by session_id, keep highest score
    return deduplicated_results
```

---

## Step 3: BM25 Search

```python
class BM25SearchEngine:
    def __init__(self): ...
    
    def build_index(self, sessions: List[SessionDocument]) -> None:
        """Build corpus from session documents."""
        # Corpus: one document per session
        # Text: task_raw + files_edited + domains + project_name + summary_doc
    
    def search(self, query: str, filter_ids: List[str] = None, 
               n_results: int = 50) -> List[Tuple[str, float]]:
        # Tokenize, score, normalize 0-1
```

Uses `rank_bm25.BM25Okapi` library.

---

## Step 4: RRF Fusion

**Standard RRF:** `score = Σ 1/(k + rank_i)`, k=60

**Weighted RRF:** `score = Σ weight_i * 1/(k + rank_i)`

**Intent-aware alpha (BM25 + Vector only):**
| Intent | alpha (BM25 weight) | Behavior |
|---|---|---|
| error_recall | 0.75 | Heavy BM25 — error messages have keywords |
| decision_hunting | 0.20 | Heavy vector — decisions need semantic match |
| implementation_lookup | 0.50 | Balanced |
| Others | 0.50 | Balanced |

---

## Step 5: Metadata Filter

```python
def _filter_metadata(results: List, metadata_store: MetadataStore,
                     project: str, quality: str, days: int) -> List:
    """Filter results by metadata criteria."""
```

Pre-filters using SQLite before search, then post-filters results that slipped through.

---

## Step 6: Chunk Reranker

Re-ranks top 20 candidates with 5-signal weighted scoring:

| Signal | Weight | How computed |
|---|---|---|
| Semantic | 50% | Cosine similarity: query_embedding vs chunk_embedding |
| File match | 20% | Set intersection: query files vs chunk files |
| Keyword | 15% | Set intersection: query tech vs chunk keywords |
| Content type | 10% | 1.0 if code and query.prefer_code, 0.7 mixed, 0.3 text |
| Recency | 5% | 1.0 if <7 days, then 0.5^(days/30), floor 0.1 |

```python
def rerank(candidates: List[SearchResult], 
           query_embedding: List[float],
           query: QueryDecomposition) -> List[SearchResult]:
```

---

## Step 7: Build Result Cards

```python
def _build_cards(results: List[SearchResult]) -> List[ResultCard]:
    """Convert SearchResult → ResultCard with formatting."""
    # Humanize timestamps: "3 days ago", "2 weeks ago"
    # Format duration: "47 min", "2.3 hrs"
    # Format files: "auth.py, models.py +3 more"
    # Build fork_command: "smartfork fork {session_id}"
```

---

## Caching

```python
class SearchCache:
    def __init__(self, max_size: int = 128, ttl: int = 300): ...
    def get(self, query_hash: str) -> Optional[List[ResultCard]]: ...
    def put(self, query_hash: str, results: List[ResultCard]) -> None: ...
    def invalidate_session(self, session_id: str) -> None: ...
```

MD5 hash of (query + filters) as cache key. TTL in seconds.

---

## Recency Scoring (utility)

```python
def recency_score(session_start_ms: int, now_ms: int = None) -> float:
    days = (now_ms - session_start_ms) / (1000 * 86400)
    if days < 7: return 1.0
    return max(0.1, 0.5 ** (days / 30))
```

---

## Testing

- Test all 7 pipeline steps independently
- Test RRF with identical rankings (should produce same order)
- Test metadata filter eliminates correct sessions
- Test cache hit/miss/invalidation
- Test with empty query
- Test with no results in ChromaDB
- Performance: <500ms for 10K sessions
