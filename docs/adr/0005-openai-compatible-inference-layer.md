# 5. Lightweight OpenAI-Compatible Inference Layer

- **Status:** Accepted
- **Date:** 2026-09-30
- **Deciders:** Orbit Core Team

---

## Context
When introducing AI-powered semantic gap detection and relationship inference, we evaluated two architectural directions for LLM invocation:
1. **Multi-framework meta-libraries (e.g. LangChain, LlamaIndex, LiteLLM):** Large dependency trees, frequent breaking changes, heavy startup overhead.
2. **Lightweight HTTP Client over Standard OpenAI Specification:** A minimal in-process HTTP client implementing OpenAI-compatible JSON REST endpoints with custom token-bucket rate limiting.

---

## Decision
Orbit implements an in-process, protocol-based **`InferenceProvider`** backed by an **`OpenAICompatibleProvider`** using standard `httpx`:
- Conforms strictly to the widely adopted `/v1/chat/completions` API schema.
- Decoupled via `InferenceProvider` Protocol for straightforward mocking in unit tests.
- Includes a dedicated `RateLimiter` implementing token-bucket throttling for both RPM and TPM.

---

## Consequences

### Positive
- Zero heavy framework dependencies; rapid initialization and minimal wheel package footprint.
- Seamless compatibility with local zero-cost engines (Ollama, LM Studio, vLLM) and commercial APIs (OpenAI, OpenRouter, Groq).
- Deterministic structured JSON output parsing with Pydantic validation.

### Negative
- Advanced provider-specific features (e.g., custom Anthropic prompt caching headers or Google Vertex protobuf APIs) require standard OpenAI-compatible gateway adapters.
