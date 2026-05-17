# Spec: US-013 — 10 popular third-party OpenAI-compatible providers

## Context

Users want maximum flexibility in choosing LLM providers. The `OpenAICompatibleLLM` class from US-011 provides the generic mechanism. This story adds factory mappings for 10 popular third-party providers, each with their own base URL, API key environment variable, and default model.

All 10 providers expose OpenAI-compatible `/v1/chat/completions` endpoints and work with the standard `openai` Python SDK.

## Provider Reference Table

| Provider | Factory name | Base URL | Env Var | Default model | Free tier? |
|----------|-------------|----------|---------|---------------|------------|
| OpenRouter | `openrouter` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | `meta-llama/llama-3.3-70b-instruct:free` | Yes (`:free` models) |
| Groq | `groq` | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` | Yes |
| Google Gemini | `gemini` | `https://generativelanguage.googleapis.com/v1beta/openai/` | `GOOGLE_API_KEY` | `gemini-1.5-flash-latest` | Yes (Flash) |
| Together AI | `together` | `https://api.together.ai/v1` | `TOGETHER_API_KEY` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | No |
| Mistral AI | `mistral` | `https://api.mistral.ai/v1` | `MISTRAL_API_KEY` | `mistral-large-latest` | Limited |
| DeepSeek | `deepseek` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` | `deepseek-chat` | Promo credits |
| Fireworks AI | `fireworks` | `https://api.fireworks.ai/inference/v1` | `FIREWORKS_API_KEY` | `accounts/fireworks/models/llama-v3p1-8b-instruct` | No |
| Cohere | `cohere` | `https://api.cohere.com/v1` | `COHERE_API_KEY` | `command-r` | Limited |
| xAI (Grok) | `xai` | `https://api.x.ai/v1` | `XAI_API_KEY` | `grok-2-latest` | No |
| Perplexity | `perplexity` | `https://api.perplexity.ai` | `PERPLEXITY_API_KEY` | `sonar` | $5 credit |

## Requirements

### Factory mappings

Extend `get_llm()` in `src/smartfork/providers/llm.py` with 10 new provider branches. Each branch instantiates `OpenAICompatibleLLM` with the provider's defaults.

**Pattern for each provider:**

```python
if provider == "openrouter":
    return OpenAICompatibleLLM(
        model=model or "meta-llama/llama-3.3-70b-instruct:free",
        api_key=None,  # Let OpenAICompatibleLLM resolve OPENROUTER_API_KEY
        base_url="https://openrouter.ai/api/v1",
        provider_name="openrouter",
    )
```

**Repeat for all 10 providers** using the table above.

### Error messages

Each provider should produce a clear error when the API key is missing:

```
RuntimeError: OPENROUTER_API_KEY not found. Set it in ~/.smartfork/secrets.env or as an environment variable.
```

The `OpenAICompatibleLLM` class from US-011 handles this automatically based on `provider_name`.

### Config validation

`SmartForkConfig._backfill_tiered_llms` validator (if it validates provider names) must accept all 10 new names. If there is no validation list, nothing to change.

### Documentation

Update `AGENTS.md` (or `README.md` if requested by user) with a provider quick-reference table so users know which env vars to set. At minimum, add to `AGENTS.md`:

```markdown
## Supported LLM Providers

| Provider | Env Var | Example Model | Notes |
|----------|---------|---------------|-------|
| ollama | (none) | qwen2.5-coder:7b | Local, free |
| openai | OPENAI_API_KEY | gpt-4o-mini | Paid |
| anthropic | ANTHROPIC_API_KEY | claude-3-haiku | Paid |
| opencode / go | OPENCODE_API_KEY | qwen3.5-plus | Subscription ($10/mo) |
| zen | OPENCODE_API_KEY | qwen3.5-plus | Pay-as-you-go |
| openrouter | OPENROUTER_API_KEY | meta-llama/llama-3.3-70b-instruct:free | Free `:free` models |
| groq | GROQ_API_KEY | llama-3.3-70b-versatile | Fast, free tier |
| gemini | GOOGLE_API_KEY | gemini-1.5-flash-latest | Generous free tier |
| together | TOGETHER_API_KEY | meta-llama/Llama-3.3-70B-Instruct-Turbo | Cheap, no free tier |
| mistral | MISTRAL_API_KEY | mistral-large-latest | Limited free tier |
| deepseek | DEEPSEEK_API_KEY | deepseek-chat | Very cheap |
| fireworks | FIREWORKS_API_KEY | accounts/fireworks/models/llama-v3p1-8b-instruct | Serverless |
| cohere | COHERE_API_KEY | command-r | Limited free tier |
| xai | XAI_API_KEY | grok-2-latest | Mid-range pricing |
| perplexity | PERPLEXITY_API_KEY | sonar | $5 credit on signup |
```

## Files to Modify

1. `src/smartfork/providers/llm.py` — add 10 factory branches to `get_llm()`
2. `src/smartfork/config.py` — ensure validator accepts new provider names (if applicable)
3. `AGENTS.md` — add provider reference table

## Testing Strategy

In `tests/providers/test_openai_compatible.py`:

For **each** of the 10 providers, write a test that:
1. Monkeypatches the correct env var
2. Calls `get_llm("{provider_name}")`
3. Asserts the returned object is an `OpenAICompatibleLLM` instance
4. Asserts `base_url` and `model` match the expected defaults

Also write one "missing key" test per provider (or parameterize): unset env var → assert `RuntimeError` with correct env var name.

**Example parameterized test:**

```python
@pytest.mark.parametrize("provider,expected_base_url,expected_model", [
    ("openrouter", "https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free"),
    ("groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    # ... etc
])
def test_provider_factory(monkeypatch, provider, expected_base_url, expected_model):
    monkeypatch.setenv(f"{provider.upper()}_API_KEY", "fake-key")
    llm = get_llm(provider)
    assert isinstance(llm, OpenAICompatibleLLM)
    assert llm.base_url == expected_base_url
    assert llm.model == expected_model
```

## Constraints

- No new dependencies
- No provider-specific SDKs
- Each provider name is case-insensitive in `get_llm()`
- Backward compatibility: existing providers unchanged
- Total new code should be ~40 lines in `get_llm()` + tests
