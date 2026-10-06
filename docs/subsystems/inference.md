# Subsystem: Inference Layer

The inference subsystem abstracts frontier LLM reasoning capabilities for classifying conceptual relationships between notes without hardcoding specific cloud vendors.

---

## 🏗️ Architecture & Protocols
- **Protocol:** [`InferenceProvider`](file:///home/ali/projects/my/project-orbit/src/pkmrag/inference/base.py)
- **Default Implementation:** [`OpenAICompatibleProvider`](file:///home/ali/projects/my/project-orbit/src/pkmrag/inference/provider.py)
- **Rate Limiting:** [`RateLimiter`](file:///home/ali/projects/my/project-orbit/src/pkmrag/inference/limiter.py)

---

## 🔒 Pluggable Interface

The core retrieval engine consumes LLMs strictly through the `InferenceProvider` protocol:

```python
class InferenceProvider(Protocol):
    def infer_relationship(
        self,
        source_title: str,
        source_text: str,
        target_title: str,
        target_text: str,
    ) -> InferredRelationshipResult: ...
```

This ensures zero vendor lock-in; any OpenAI-compatible endpoint (OpenAI, Anthropic via proxy, Ollama, LM Studio, vLLM) can be targeted by specifying `OPENAI_BASE_URL` and `OPENAI_API_KEY`.

---

## ⏱️ Dual-Token Rate Limiting

To comply with API quotas during bulk vault classification, the `RateLimiter` implements dual token buckets:
1. **Requests Per Minute (RPM):** Controls network request bursts.
2. **Tokens Per Minute (TPM):** Estimates prompt and completion tokens, enforcing backoff delays when approaching throughput limits.

---

## 🎯 Structured Output Schema

The provider enforces structured JSON schema responses returning typed relationship classifications:

```json
{
  "relationship": "EXTENDS | CONTRADICTS | SUPPORTS | PREREQUISITE_FOR | REFINES | NONE",
  "confidence": 0.85,
  "reason": "Note B implements the algorithm specified in Note A."
}
```
