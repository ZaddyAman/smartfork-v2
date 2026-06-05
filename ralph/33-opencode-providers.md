# Spec: US-012 — OpenCode ecosystem providers (opencode, go, zen)

## Context

The user has API keys for OpenCode's LLM gateway services. OpenCode operates two distinct endpoints under the same authentication system:

- **Go**: Subscription plan ($5 first month, then $10/month). Endpoint: `https://opencode.ai/zen/go/v1/chat/completions`. Included models: Qwen3.5 Plus, DeepSeek V4 Flash, GLM-5.1, Kimi K2.5, MiniMax M2.5.
- **Zen**: Pay-as-you-go gateway. Endpoint: `https://opencode.ai/zen/v1/chat/completions`. Same models plus premium options. Some models route to different paths (`/responses` for GPT, `/messages` for Claude) but the standard `/chat/completions` works for the models we care about.
- **Opencode**: User-friendly alias that most users expect when they say "I have opencode keys". Maps to Go endpoint.

All three share the **same API key**: `OPENCODE_API_KEY`.

## Requirements

### Factory mappings

Extend `get_llm()` in `src/smartfork/providers/llm.py` with three new provider branches:

| User types | Provider name | Base URL | Env Var | Default model |
|-----------|--------------|----------|---------|---------------|
| `opencode` | `opencode` | `https://opencode.ai/zen/go/v1` | `OPENCODE_API_KEY` | `qwen3.5-plus` |
| `go` | `go` | `https://opencode.ai/zen/go/v1` | `OPENCODE_API_KEY` | `qwen3.5-plus` |
| `zen` | `zen` | `https://opencode.ai/zen/v1` | `OPENCODE_API_KEY` | `qwen3.5-plus` |

**Important:** The base URL should NOT include the `/chat/completions` suffix. The OpenAI SDK appends that automatically. So pass `https://opencode.ai/zen/go/v1` (not `.../v1/chat/completions`).

### Implementation

In `get_llm()`, add after existing providers:

```python
if provider in ("opencode", "go"):
    return OpenAICompatibleLLM(
        model=model or "qwen3.5-plus",
        api_key=None,  # Let OpenAICompatibleLLM resolve from OPENCODE_API_KEY
        base_url="https://opencode.ai/zen/go/v1",
        provider_name=provider,
    )

if provider == "zen":
    return OpenAICompatibleLLM(
        model=model or "qwen3.5-plus",
        api_key=None,
        base_url="https://opencode.ai/zen/v1",
        provider_name="zen",
    )
```

**Note on api_key resolution:** `OpenAICompatibleLLM` will look for `OPENCODE_API_KEY` because `provider_name` is passed through. However, the current `_load_secrets()` function looks for exact key names. We need to handle the case where `provider_name` is `go` or `zen` but the env var is `OPENCODE_API_KEY`.

### API Key Resolution for OpenCode

The `OpenAICompatibleLLM` class (from US-011) resolves API keys by looking for `{PROVIDER_NAME_UPPER}_API_KEY`. For `go` and `zen`, this would look for `GO_API_KEY` and `ZEN_API_KEY`, which do not exist.

**Fix:** In the factory function, explicitly pass the resolved `OPENCODE_API_KEY` when instantiating for `opencode`, `go`, or `zen`:

```python
if provider in ("opencode", "go", "zen"):
    secrets = _load_secrets()
    api_key = secrets.get("OPENCODE_API_KEY", os.environ.get("OPENCODE_API_KEY", ""))
    if not api_key:
        raise RuntimeError(
            "OPENCODE_API_KEY not found. Set it in ~/.smartfork/secrets.env or "
            "as an environment variable. Get a key at https://opencode.ai/auth"
        )
    base_url = (
        "https://opencode.ai/zen/v1" if provider == "zen"
        else "https://opencode.ai/zen/go/v1"
    )
    return OpenAICompatibleLLM(
        model=model or "qwen3.5-plus",
        api_key=api_key,
        base_url=base_url,
        provider_name=provider,
    )
```

### Config Validation

`SmartForkConfig` in `src/smartfork/config.py` has a `_backfill_tiered_llms` validator that sets `strategic_llm_provider` and `smart_llm_provider` if they are None. This validator should **not reject** `opencode`, `go`, or `zen` as valid provider names.

Currently, the validator likely checks against a hardcoded list or has no validation. If there IS a validation list, add the three new names. If there is no validation, nothing needs to change.

## Files to Modify

1. `src/smartfork/providers/llm.py` — add factory branches for `opencode`, `go`, `zen`
2. `src/smartfork/providers/__init__.py` — export `OpenAICompatibleLLM` (already done in US-011)
3. `src/smartfork/config.py` — ensure validator accepts new provider names (if validation exists)

## Testing Strategy

In `tests/providers/test_openai_compatible.py` (or a new file):

1. `test_get_llm_opencode_returns_openai_compatible`: Monkeypatch `OPENCODE_API_KEY`, call `get_llm("opencode")`, assert instance of `OpenAICompatibleLLM`, assert `base_url` is Go endpoint
2. `test_get_llm_go_same_as_opencode`: Assert `get_llm("go")` has same base_url as `get_llm("opencode")`
3. `test_get_llm_zen_different_endpoint`: Assert `get_llm("zen")` has Zen endpoint base_url
4. `test_get_llm_opencode_missing_key`: Unset `OPENCODE_API_KEY`, assert `RuntimeError` mentions `OPENCODE_API_KEY`
5. `test_get_llm_opencode_uses_custom_model`: Pass `model="kimi-k2.5"`, assert model is set

## Constraints

- All three providers must work with the `openai` Python SDK only (no opencode-specific SDK)
- Error messages must mention `OPENCODE_API_KEY`, not `GO_API_KEY` or `ZEN_API_KEY`
- The `opencode` name is an alias for `go` — both return the same endpoint
- Backward compatibility: existing providers unchanged
