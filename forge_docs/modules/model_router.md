# Model Router

The ForgeAI Model Router manages connection and query routing to local AI model providers.

## Core Features
1. **Lightweight Standard Client Sinks:**
   Implements providers using Python's standard `urllib.request` library, keeping the engine free of external package dependencies (like `requests` or `openai` SDK) and aligning with the Free Software policy.
2. **Provider Decoupling:**
   Exposes standard interfaces `ModelRouterService` and `ModelProvider`.
3. **Usage Auditing:**
   Returns standard `ModelResponse` objects containing parsed prompt and completion token statistics for billing, optimization, and Memory Engine ingestion.

## Standard Providers
- **Ollama Provider:**
  Submits payloads to local Ollama endpoints (e.g. `http://localhost:11434/api/generate` or `/api/chat`).
- **OpenAI-Compatible Provider:**
  Submits standard payloads to vLLM, LM Studio, or LocalAI servers (e.g. `/v1/chat/completions`).

## Example Usage
```python
from forge_core.model_router.service import ModelRouterService

router = registry.resolve(ModelRouterService)
response = router.generate("Write a quicksort in Python.")
print(response.text)
print(f"Usage: {response.usage}")
```

## Streaming
`ModelRouterService.stream_chat(messages, ...)` returns an iterator of `ChatChunk(text, done, model_name, usage)`; the last chunk has `done=True` and carries token usage.

- **Ollama** streams `/api/chat` NDJSON. Per-request options such as `options={"num_ctx": 8192}` override the server's default context window.
- **OpenAI-compatible** servers stream `/chat/completions` server-sent events.
- A provider that does not implement streaming inherits a fallback that calls `generate_chat` and returns the whole reply as one final chunk.

Stopping iteration closes the HTTP connection, which also stops generation on the server.

```python
for chunk in router.stream_chat([{"role": "user", "content": "Explain this regex: ^a+$"}]):
    print(chunk.text, end="", flush=True)
```
