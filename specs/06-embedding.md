# SmartFork v2 — Embedding Pipeline (Layer 2)

> **Design:** Takes chunks → embeds them with instruction prefixes → upserts to ChromaDB.
> **Instruction-aware per doc_type** (Anthropic's Contextual Retrieval technique).

---

## Instruction Prefixes

Different doc_types get different prefixes to improve retrieval precision:

```python
EMBED_INSTRUCTIONS = {
    "task_doc":      "Represent this developer task description for session retrieval",
    "summary_doc":   "Represent this coding session summary for intelligent search",
    "reasoning_doc": "Represent this technical decision and rationale for retrieval",
    "proposition":   "Represent this factual statement about a coding session for retrieval",
}

QUERY_INSTRUCTION = "Find coding sessions relevant to this developer query"
```

- At EMBED time: instruction + text → embed
- At QUERY time: QUERY_INSTRUCTION + query → embed
- SentenceTransformerEmbedder ignores instructions (pass-through)
- OllamaEmbedder and OpenAI respect them

---

## EmbeddingPipeline

**File:** `src/smartfork/indexer/embedder.py`

```python
class EmbeddingPipeline:
    def __init__(self, embedder: EmbeddingProvider, 
                 chroma_client, batch_size: int = 32):
        self.embedder = embedder
        self.collection = chroma_client.get_or_create_collection("smartfork_sessions")
        self.batch_size = batch_size
    
    def embed_and_store(self, chunks: List[Chunk]) -> int:
        """Embed chunks and upsert to ChromaDB. Returns count stored."""
        stored = 0
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i:i + self.batch_size]
            texts = [self._prepend_instruction(c) for c in batch]
            ids = [f"{c.session_id}_{c.chunk_index}" for c in batch]
            metadatas = [self._build_metadata(c) for c in batch]
            
            embeddings = self.embedder.embed_batch(texts, 
                doc_type=batch[0].doc_type)
            
            self.collection.upsert(
                ids=ids, embeddings=embeddings,
                metadatas=metadatas, documents=texts)
            stored += len(batch)
        return stored
    
    def embed_query(self, query: str) -> List[float]:
        """Embed a search query with query instruction."""
        return self.embedder.embed_query(query)
    
    def _prepend_instruction(self, chunk: Chunk) -> str:
        instruction = EMBED_INSTRUCTIONS.get(chunk.doc_type, "")
        return f"{instruction}: {chunk.text}" if instruction else chunk.text
    
    def _build_metadata(self, chunk: Chunk) -> dict:
        return {
            "session_id": chunk.session_id,
            "doc_type": chunk.doc_type,
            "chunk_index": chunk.chunk_index,
            "project_name": chunk.project_name,
            "files_mentioned": ",".join(chunk.files_mentioned[:10]),
            "keywords": ",".join(chunk.keywords[:10]) if chunk.keywords else "",
        }
```

---

## ChromaDB Setup

**File:** `src/smartfork/database/chroma_client.py`

```python
import chromadb
from chromadb.config import Settings

def get_chroma_client(persist_path: str):
    """Create ChromaDB client with persistent storage."""
    return chromadb.PersistentClient(
        path=persist_path,
        settings=Settings(anonymized_telemetry=False)
    )

def get_or_create_collection(client, name: str = "smartfork_sessions"):
    """Get or create the sessions collection with cosine distance."""
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"}
    )
```

**Key decisions:**
- `PersistentClient` — embedded, no separate server process
- `hnsw:space: cosine` — cosine distance for semantic search
- Path: `config.qdrant_db_path` (legacy name, actually ChromaDB directory)
- No telemetry

---

## Retry & Error Handling

```python
MAX_RETRIES = 3
RETRY_DELAY = 1.0  # seconds, exponential backoff

def embed_with_retry(pipeline, chunks):
    for attempt in range(MAX_RETRIES):
        try:
            return pipeline.embed_and_store(chunks)
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(RETRY_DELAY * (2 ** attempt))
```

---

## Progress Reporting

The indexer calls `embed_and_store` with a progress callback:

```python
def embed_and_store(self, chunks, on_progress=None):
    for i in range(0, len(chunks), self.batch_size):
        batch = chunks[i:i + self.batch_size]
        # ... embed and store ...
        if on_progress:
            on_progress(i + len(batch), len(chunks))
```

---

## Collection Stats

```python
def get_collection_stats(collection) -> dict:
    return {
        "count": collection.count(),
        "name": collection.name,
    }
```

---

## Testing

- Test with each embedding provider (ollama, sentence-transformers, openai)
- Test batching: exactly 32 chunks 3 times, verify 96 stored
- Test instruction prefix: verify it's in the stored document text
- Test retry: simulate failure, verify retries happen
- Test empty chunk list: should return 0, not error
