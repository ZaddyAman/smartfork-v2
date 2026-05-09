# SmartFork v2 — Chunking System (Layer 2)

> **Design:** Semantically-aware text chunking that respects conversation turns and never breaks code blocks.
> **Two strategies:** MessageBoundaryChunker (default) + ContextualChunker (adds headers).

---

## Strategy 1: MessageBoundaryChunker

**File:** `src/smartfork/indexer/chunker.py`

### Core Principle

**A chunk is a complete semantic unit.** Never split a user message, assistant response, or code block across chunks.

### ChunkingConfig

```python
@dataclass
class ChunkingConfig:
    max_tokens_per_chunk: int = 512
    overlap_tokens: int = 128
    extract_keywords: bool = True
    extract_files: bool = True
    preserve_code_blocks: bool = True
```

### Algorithm

```
For each message in session:
  1. Estimate token count (words * 0.75 + penalties)
  2. If current_chunk_size + message_size <= max_tokens:
       Append message to current chunk
  3. Else:
       a. Finalize current chunk → yield it
       b. Start new chunk
       c. If overlap_tokens > 0:
            Copy last N tokens from previous chunk as prefix
       d. Append message to new chunk
  4. Finalize last chunk → yield it
```

### Token Estimation

```python
def estimate_tokens(text: str, is_code: bool = False) -> int:
    words = len(text.split())
    base = words * 0.75
    if is_code:
        base *= 1.4  # Code is more token-dense
    return int(base)
```

### Code Block Detection

A message is a "code block" if:
- It starts and ends with ``` fences
- OR > 40% of lines match code patterns (indentation, keywords, punctuation density)
- OR it's a tool output containing terminal output

Code blocks get the 1.4x token penalty.

### Per-Chunk Metadata

Each chunk carries:
- `session_id` — which session it belongs to
- `chunk_index` — position in the session (0, 1, 2, ...)
- `content_type` — "code" | "text" | "mixed"
- `files_mentioned` — file paths found in this chunk
- `keywords` — key terms extracted from this chunk
- `doc_type` — "task_doc" | "summary_doc" | "reasoning_doc" | "proposition"

---

## Strategy 2: ContextualChunker

**File:** `src/smartfork/indexer/contextual_chunker.py`

### Purpose

Implements Anthropic's Contextual Retrieval technique. Every chunk gets a **context header** so it's self-contained even when retrieved in isolation.

### Context Header Format

```
[Project: {project_name} | Session: {YYYY-MM-DD} | Task: {task_raw[:80]} | Files: {top_3_files}]
```

Example:
```
[Project: BharatLawAI | Session: 2026-03-15 | Task: Debugging JWT race condition in FastAPI middleware | Files: auth.py, middleware.py, conftest.py]
```

### When Applied

- `task_doc` chunks: header + task description
- `summary_doc` chunks: header + summary
- `reasoning_doc` chunks: header + reasoning text
- `proposition` chunks: header + proposition text

### Reasoning Block Splitting

Long reasoning blocks (> 500 chars) are split at sentence boundaries:
1. Split at `. `, `! `, `? ` followed by capital letter
2. Keep 2-sentence overlap between splits
3. Each split gets its own context header

```python
def split_reasoning(text: str, max_chars: int = 500, overlap_sentences: int = 2) -> List[str]:
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    chunks = []
    i = 0
    while i < len(sentences):
        chunk = ""
        while i < len(sentences) and len(chunk) + len(sentences[i]) < max_chars:
            chunk += sentences[i] + " "
            i += 1
        chunks.append(chunk.strip())
        i = max(0, i - overlap_sentences)  # Overlap
    return chunks
```

---

## Factory

```python
def create_chunker(config: ChunkingConfig, 
                   strategy: str = "message_boundary") -> Chunker:
    if strategy == "message_boundary":
        return MessageBoundaryChunker(config)
    elif strategy == "contextual":
        return ContextualChunker(config)
    raise ValueError(f"Unknown chunking strategy: {strategy}")
```

The `Chunker` type is a Protocol:
```python
class Chunker(Protocol):
    def chunk(self, chunks_data) -> List[Chunk]: ...
```

---

## Integration

The indexer calls:
```python
chunker = create_chunker(config, strategy="contextual")
chunks = chunker.chunk(session_doc)
embedder.embed_and_store(chunks)
```

---

## Testing

- Verify code blocks are NEVER split
- Verify context headers appear on every chunk
- Verify overlap works for long reasoning blocks
- Verify empty sessions produce zero chunks
- Test with all 7 adapter output formats
