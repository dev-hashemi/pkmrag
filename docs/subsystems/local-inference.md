# Local Model Inference (Ollama & FastEmbed)

Orbit is built from the ground up as a **local-first** knowledge retrieval engine. It enables completely offline semantic gap detection and relationship inference using local models via Ollama, complementing Orbit's already 100% local in-process embedding engine.

---

## 1. Dual-Layer Local Architecture

Orbit achieves 100% on-device operation with zero cloud API dependencies:

| Task | Engine | Runtime | Network / Daemon |
|------|--------|---------|-------------------|
| **Vector Embeddings** | FastEmbed (`BAAI/bge-small-en-v1.5`) | In-process ONNX Runtime (CPU) | None (zero daemon, zero network) |
| **Vector Indexing & Search** | LanceDB Columnar Store | In-process Arrow/Rust library | None (embedded filesystem) |
| **Graph Traversal** | LadybugDB (C++ openCypher) | In-process C++ database | None (embedded filesystem) |
| **L1 Query Cache** | SQLite + WAL mode | In-process relational cache | None (embedded filesystem) |
| **Relationship Inference** | Ollama (`llama3.2`, `qwen2.5`) | Local daemon (`localhost:11434`) | Localhost HTTP (Zero telemetry/cloud) |

---

## 2. Setting Up Ollama for Orbit

### 2.1 Install & Pull Models

Install Ollama from [ollama.com](https://ollama.com) and pull your preferred local model:

```bash
# Lightweight 3B model (recommended for speed and memory efficiency)
ollama pull llama3.2

# Alternative highly capable 3B/7B options
ollama pull qwen2.5:3b
ollama pull mistral:7b
```

### 2.2 Verify with `pkmrag doctor`

Orbit's diagnostic command automatically probes your local Ollama daemon:

```bash
uv run pkmrag doctor
```

Output:
```
                       In-Process Data Plane Verification                       
┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Component              ┃ Status  ┃ Version ┃ Latency ┃ Verification Details  ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━┩
│ LadybugDB Property     │  PASS   │ 0.20.4  │  46.3ms │ In-memory Cypher …    │
│ Graph                  │         │         │         │                       │
│ LanceDB Vector Engine  │  PASS   │ 0.38.0  │  16.3ms │ Arrow-backed vector … │
│ Ollama Local Engine    │  PASS   │ 0.3.12  │   2.1ms │ Ollama daemon active  │
│                        │         │         │         │ (models: llama3.2)    │
└────────────────────────┴─────────┴─────────┴─────────┴───────────────────────┘
```

> [!NOTE]
> If Ollama is not running, `pkmrag doctor` marks the check as `OFFLINE` (optional) without failing exit codes or blocking non-AI features.

---

## 3. Running Semantic Discovery Locally

### 3.1 Via CLI Flags

To run relationship discovery with Ollama:

```bash
# Discover semantic gaps and infer relationships using local Llama 3.2
uv run pkmrag discover /path/to/vault --provider ollama --model llama3.2

# Dry-run candidates without executing LLM inference
uv run pkmrag discover /path/to/vault --provider ollama --dry-run
```

### 3.2 Via Configuration (`.env`)

You can set Ollama as the default provider in your global or vault-level `.env`:

```ini
# Global or Vault .env
ORBIT_LLM_PROVIDER=ollama
ORBIT_OLLAMA_BASE_URL=http://localhost:11434/v1
ORBIT_OLLAMA_MODEL=llama3.2
```

Once configured in `.env`, simply run:

```bash
uv run pkmrag discover /path/to/vault
```

---

## 4. Key Engineering Safeguards

### 4.1 URL Auto-Normalization
Users often supply `http://localhost:11434` without the `/v1` suffix. Because OpenAI-compatible endpoints reside under `/chat/completions`, hitting Ollama without `/v1` results in a 404 error. Orbit automatically appends `/v1` if targeting localhost or loopback IPs.

### 4.2 Conversational Validation Feedback Retries
Smaller 3B/7B models occasionally deviate slightly from strict JSON schemas (e.g. returning an unlisted relationship type or malformed syntax). 

Rather than failing or silently dropping the candidate, Orbit intercepts Pydantic validation errors and initiates an in-loop conversational retry:
1. The assistant's invalid output is appended to the message history.
2. A targeted corrective prompt is submitted (e.g. `Output failed validation: Invalid relationship type 'EXTEND'. Must be one of: EXTENDS, CONTRADICTS...`).
3. The local model corrects itself on the subsequent turn, dramatically improving yield on lightweight edge models.

### 4.3 Rate Limit Bypass
Unlike public cloud APIs (OpenAI, Anthropic) which enforce token-bucket throttling (`RPM` and `TPM`), local models run on private hardware. Orbit marks local providers with `is_local=True`, completely bypassing token wait times and running inference at maximum hardware speed.
