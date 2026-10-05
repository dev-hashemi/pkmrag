# Security & Privacy Policy — Project Orbit

Project Orbit is designed from the ground up as a **local-first** knowledge retrieval engine and personal knowledge base companion.

---

## 1. Network Activity & Data Boundary

- **Localhost Only:** The Orbit Obsidian plugin communicates exclusively with the local background daemon running on loopback (`http://127.0.0.1:3747`).
- **No Cloud Dependencies by Default:** All graph storage (LadybugDB), vector indexing (LanceDB), semantic embeddings (FastEmbed CPU ONNX), and BM25 full-text queries execute 100% locally in-process on your device.
- **Zero Telemetry:** Neither Project Orbit nor the Obsidian plugin contains tracking pixels, analytics beacons, or remote telemetry collection.
- **Optional LLM Inference:** When semantic relationship discovery (`orbit discover`) is triggered, inference is executed either entirely on-device via a local Ollama daemon or through an explicitly user-configured OpenAI-compatible API key. Note contents are never shared outside these explicitly defined endpoints.

---

## 2. Authentication & Credential Storage

- **Automated Local Token Security:** The Orbit daemon generates a secure random Bearer token upon startup and writes it to `<vault>/.orbit/server_token` with restrictive owner-only permissions (`0o600`).
- **Zero Hardcoded Secrets:** Authentication credentials are exchanged strictly over loopback IPC. No passwords or API keys are stored in source code or sent to external servers.

---

## 3. Reporting Security Vulnerabilities

If you discover a security vulnerability in Project Orbit or its companion plugins, please open an issue or contact the maintainers via the GitHub repository:
https://github.com/project-orbit/project-orbit/security
