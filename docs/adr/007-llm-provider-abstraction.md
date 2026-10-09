# ADR-007: LLM provider abstraction

Status: Accepted

## Context

Phase 8 onwards calls a language model for summaries, structured extraction, retrieval
answers and query generation. The project already supports OpenAI, and users may prefer
Gemini or a local Ollama model. Model calls cost money, fail transiently, and return text that
is not guaranteed to match the requested shape. Paper abstracts are untrusted input and can
contain prompt-injection attempts.

## Decision

**One narrow interface.** `LLMProvider.complete(messages, json_mode, temperature, max_tokens)`
returns text plus the model name and token usage. Nothing else in the codebase imports a
provider SDK.

**One HTTP client for three providers.** OpenAI, Gemini and Ollama all expose an
OpenAI-compatible `/chat/completions` endpoint, so `OpenAICompatibleChat` covers them and only
the base URL, key and model differ (`LLM_PROVIDER`, `LLM_MODEL`). Transient failures (429, 5xx,
transport errors) are retried with jittered exponential backoff. Errors never include the
response body, the prompt or the key.

**Validated structured output.** `complete_structured` asks for a JSON object, validates it
against a pydantic model, and on failure shows the model its own reply plus the field names
that were wrong, once. If that fails it raises `LLMOutputError` (HTTP 502) without echoing model
text. List fields are trimmed rather than rejected so verbosity alone does not cause retries.
Provider-native strict JSON-schema modes were not used because they are not portable across the
three providers.

**Grounding and untrusted input.** Prompts delimit source text in `<paper>` tags, state that it
is data and not instructions, and tell the model to return empty fields instead of guessing.
Model output is rendered as plain text in the UI.

**Caching.** Generated insights are stored on the `Paper` node together with a hash of the input
text and prompt version, and the model name. Requests reuse a current insight, flag a stale one,
and only call the model when forced or when the input changed. Batch generation
(`researchgraph insights`) is resumable, bounded in concurrency (`LLM_CONCURRENCY`) and isolates
per-paper failures.

**Cost control.** Generation endpoints sit behind the admin dependency (open in development,
token-protected, or disabled in production). Reading a stored insight is public.

## Consequences

- Tests use a scripted fake and never need a network or key.
- Switching provider or model is a configuration change; existing insights keep their recorded model.
- No streaming and no tool calling yet; Phase 9 adds streaming only if the UI needs it.
- Output quality was not benchmarked here; Phase 14 adds evaluation.
