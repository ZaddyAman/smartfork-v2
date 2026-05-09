# SmartFork v2 — Provider System (Layer 0)

> **Build target:** Pluggable LLM and Embedding backends.
> **Must implement BEFORE any layer that uses LLM/embeddings.**
> **Design:** Pluggable providers via Protocol interfaces. Default: Ollama (local, free, private). Cloud providers require user API keys.

---

## Design

SmartFork supports 6 LLM backends provider and THREE embedding backends. All are swappable via Protocol interfaces. The user chooses at setup time.

**Default for everything: Ollama (local, free, private).**
Cloud providers require user's own API key stored in `~/.smartfork/secrets.env`.

---

## LLM Provider

### File: `src/smartfork/providers/llm.py`

Three concrete implementations of the `LLMProvider` protocol:

#### 1. OllamaLLM (default)
- Model: `qwen2.5-coder:7b` (configurable)
- Client: `ollama` Python package → `ollama.generate()`
- Completely local, zero cost, no API key
- `complete()`: sends prompt → returns response text
- `complete_structured()`: uses `instructor` library to get Pydantic-validated output from local models
- **Required pip packages:** `ollama`, `instructor`

#### 2. AnthropicLLM (opt-in)
- Model: `claude-3-haiku-20240307` (configurable)
- Client: `anthropic` Python package → `messages.create()`
- Requires `ANTHROPIC_API_KEY` in `secrets.env`
- `complete()`: sends prompt as single user message
- **Required pip packages:** `anthropic`

#### 3. OpenAILLM (opt-in)
- Model: `gpt-4o-mini` (configurable)
- Client: `openai` Python package → `chat.completions.create()`
- Requires `OPENAI_API_KEY` in `secrets.env`
- `complete()`: sends prompt as single user message
- **Required pip packages:** `openai`



#### 4. opencode go/zen (opt-in)

#### 5. openrouter (opt-in)
 
 #### 6. kilo code (opt-in)

### Factory function

```python
def get_llm(provider: str = "ollama", model: str = None) -> LLMProvider:
    """Returns the correct LLM provider based on config.
    provider: "ollama" | "anthropic" | "openai"
    """
```

### Error handling for all providers
- If Ollama not installed/running: raise clear error with install instructions
- If cloud provider returns error: log, return empty string, don't crash
- If API key not found: raise clear error telling user to set up secrets.env

---

## Embedding Provider

### File: `src/smartfork/providers/embedding.py`

Three concrete implementations of the `EmbeddingProvider` protocol:

#### 1. OllamaEmbedder (default)
- Model: `qwen3-embedding:0.6b` (configurable, supports nomic-embed-text)
- Client: `ollama` Python package → `ollama.embed()`
- **Instruction-aware**: Prepends different instructions based on `doc_type`
- Default dimensions: 512 (configurable)
- `embed()`: prepends instruction prefix → calls ollama
- `embed_query()`: prepends query instruction → calls ollama
- `embed_batch()`: batch embed with same instruction
- **Required pip packages:** `ollama`

**Instruction prefixes (Anthropic's Contextual Retrieval technique):**
```python
EMBED_INSTRUCTIONS = {
    "task_doc":      "Represent this developer task description for session retrieval",
    "summary_doc":   "Represent this coding session summary for intelligent search",
    "reasoning_doc": "Represent this technical decision and rationale for retrieval",
    "proposition":   "Represent this factual statement about a coding session for retrieval",
}
QUERY_INSTRUCTION = "Find coding sessions relevant to this developer query"
```

#### 2. SentenceTransformerEmbedder (fallback)
- Model: `all-MiniLM-L6-v2` (configurable)
- Client: `sentence-transformers` Python package
- NOT instruction-aware (doc_type is ignored)
- Default dimensions: 384
- Works fully offline, no Ollama dependency
- `embed_batch()` uses native batch encoding (fast)
- **Required pip packages:** `sentence-transformers`

#### 3. OpenAIEmbedder (opt-in)
- Model: `text-embedding-3-small` (configurable)
- Client: `openai` Python package → `embeddings.create()`
- NOT instruction-aware
- Default dimensions: 1536
- Requires `OPENAI_API_KEY` in `secrets.env`
- **Required pip packages:** `openai`

### Factory function
```python
def get_embedder(provider: str = "ollama", model: str = None) -> EmbeddingProvider:
    """Returns the correct embedding provider based on config.
    provider: "ollama" | "sentence-transformers" | "openai"
    """
```

### Health check
```python
def check_ollama_available(model: str) -> bool:
    """Check if Ollama is installed, running, and has the model pulled."""

def check_embedding_model_available(provider: str, model: str) -> bool:
    """Generic health check for any embedding provider."""
```

---

## Model Change Protection

**File:** `src/smartfork/providers/guard.py`

When user changes embedding model, dimensions change → all vectors become incompatible → must re-index.

```python
class EmbeddingModelGuard:
    """Protects against incompatible embedding model changes."""
    
    @staticmethod
    def check_compatibility(current_model: str, current_dims: int, new_model: str, new_dims: int) -> bool:
        """Returns True if models are compatible (same dimensions)."""
    
    @staticmethod
    def get_warning_message(current_model: str, new_model: str, session_count: int) -> str:
        """Returns a user-friendly warning about re-index requirements."""
        # Format: "⚠ Changing embedding model from X (1024 dims) to Y (768 dims) is INCOMPATIBLE.
        #          This requires re-indexing all 1,247 sessions. Use --reindex to proceed."
```

---

## Provider Selection Flow

1. On startup, `SmartForkConfig.load()` is called
2. Config contains `llm_provider`, `llm_model`, `embedding_provider`, `embedding_model`
3. If cloud provider: check for API key in `secrets.env`
4. If embedding model changed since last run: check dimensions, warn if incompatible
5. Factory functions create the right providers
6. Providers are passed via dependency injection to all consumers

---

## Ollama Setup Helpers

```python
def ensure_ollama_model(model: str) -> None:
    """Check if model is pulled; if not, pull it with progress display."""

def list_available_ollama_models() -> List[str]:
    """Return list of locally available Ollama models."""

def recommend_model() -> str:
    """Recommend the best available local model based on hardware."""
    # If GPU: qwen2.5-coder:7b
    # If CPU only: qwen3:0.6b
    # If low RAM: qwen3:0.6b
```

---

## Implementation Order for Ralph

1. `providers/__init__.py` — empty, or exports
2. `providers/protocols.py` — LLMProvider + EmbeddingProvider protocols
3. `providers/llm.py` — OllamaLLM, AnthropicLLM, OpenAILLM, get_llm()
4. `providers/embedding.py` — OllamaEmbedder, SentenceTransformerEmbedder, OpenAIEmbedder, get_embedder()
5. `providers/guard.py` — EmbeddingModelGuard
6. `providers/helpers.py` — ensure_ollama_model, list_models, recommend_model
