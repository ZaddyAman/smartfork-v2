# Spec: US-011 — OpenAI-compatible provider framework

## Context

SmartFork v2 currently supports 3 LLM providers: `ollama`, `openai`, and `anthropic`. Each has its own class (`OllamaLLM`, `OpenAILLM`, `AnthropicLLM`) in `src/smartfork/providers/llm.py`. All implement the `LLMProvider` protocol defined in `src/smartfork/providers/protocols.py`:

```python
class LLMProvider(Protocol):
    def complete(self, prompt: str, max_tokens: int = 500, temperature: float = 0.1) -> str: ...
    def complete_structured(self, prompt: str, output_schema: type, max_tokens: int = 500, temperature: float = 0.1) -> object: ...
```

The factory function `get_llm(provider, model)` instantiates the correct class. Structured output is handled by the `instructor` library, which patches OpenAI or Anthropic clients to return Pydantic models.

**Problem:** Adding a new provider currently requires writing a new class (~60 lines of boilerplate). With 13 new providers requested, this would be ~800 lines of near-identical code.

**Solution:** Create a single `OpenAICompatibleLLM` class that works with any provider exposing an OpenAI-compatible `/v1/chat/completions` endpoint. This covers 13 of the 16 total providers.

## Architecture

### OpenAICompatibleLLM class

```python
class OpenAICompatibleLLM:
    """Generic LLM provider for any OpenAI-compatible API endpoint."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        provider_name: str = "openai-compatible",
    ) -> None:
        ...
```

**Parameters:**
- `model`: The model identifier to send in API requests (e.g. `qwen3.5-plus`, `llama-3.3-70b-versatile`)
- `api_key`: Optional explicit API key. If None, reads from `~/.smartfork/secrets.env` then environment variables.
- `base_url`: The provider's OpenAI-compatible base URL (e.g. `https://api.groq.com/openai/v1`). Must end with `/v1` for standard OpenAI SDK compatibility.
- `provider_name`: Human-readable name for error messages (e.g. `groq`, `opencode`).

### API Key Resolution Order

1. Explicit `api_key` argument
2. `~/.smartfork/secrets.env` — key matching `{PROVIDER_NAME_UPPER}_API_KEY`
3. Environment variable `{PROVIDER_NAME_UPPER}_API_KEY`
4. If still None → raise `RuntimeError` with message: `"{provider_name}_API_KEY not found. Set it in ~/.smartfork/secrets.env or as an environment variable."`

**Note:** `provider_name` in error messages should match what the user typed. For OpenCode providers (`go`, `zen`, `opencode`), all share the `OPENCODE_API_KEY` env var but error messages should say e.g. `"go API_KEY not found..."`.

### complete() method

Uses `openai.OpenAI(base_url=..., api_key=...)` to send a chat completion request:

```python
client = OpenAI(base_url=self.base_url, api_key=self.api_key)
response = client.chat.completions.create(
    model=self.model,
    messages=[{"role": "user", "content": prompt}],
    max_tokens=max_tokens,
    temperature=temperature,
)
return response.choices[0].message.content or ""
```

### complete_structured() method

Uses `instructor` to patch the OpenAI client for Pydantic output:

```python
import instructor
from openai import OpenAI

client = instructor.from_openai(
    OpenAI(base_url=self.base_url, api_key=self.api_key),
    mode=instructor.Mode.JSON,  # Fallback mode for providers without tool calling
)

response = client.chat.completions.create(
    model=self.model,
    max_tokens=max_tokens,
    temperature=temperature,
    response_model=output_schema,
    messages=[{"role": "user", "content": prompt}],
)
return response
```

**Important:** Use `instructor.Mode.JSON` as the default mode because some providers (OpenRouter, free tiers) do not support tool-calling. JSON mode is universally supported on OpenAI-compatible endpoints.

### Error Handling

Both methods wrap exceptions:
- `ImportError` → re-raise as `RuntimeError` with install instructions
- Any other exception → log with `loguru.logger.error()`, then raise `RuntimeError` with provider name and original error

## Files to Modify

### `src/smartfork/providers/llm.py`

Add `OpenAICompatibleLLM` class after the existing `OpenAILLM` class (before `get_llm()`).

**Do NOT modify existing classes** (`OllamaLLM`, `OpenAILLM`, `AnthropicLLM`). They remain for backward compatibility and for providers with non-standard APIs.

### `src/smartfork/providers/__init__.py`

Add `OpenAICompatibleLLM` to exports.

## Testing Strategy

Create `tests/providers/test_openai_compatible.py`:

1. `test_complete_returns_text`: Mock `openai.OpenAI` client, verify `complete()` returns `message.content`
2. `test_complete_structured_returns_model`: Mock `instructor.from_openai`, verify `complete_structured()` returns a Pydantic instance
3. `test_missing_api_key_raises`: Call with no api_key, no env var, no secrets file → assert `RuntimeError` with provider name
4. `test_api_key_from_env`: Monkeypatch `PROVIDER_API_KEY`, verify it is used
5. `test_base_url_passed_to_client`: Mock `OpenAI.__init__`, assert `base_url` kwarg matches

All tests must use `unittest.mock` — no real API calls.

## Constraints

- No new dependencies (`openai` and `instructor` already installed)
- No provider-specific SDKs (`groq`, `mistralai`, `together`, etc.)
- Maintain backward compatibility: existing `get_llm("openai")` still returns `OpenAILLM`
- The new class is an **addition**, not a replacement
