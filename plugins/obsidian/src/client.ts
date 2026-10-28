/**
 * HTTP and SSE Client communicating with PKMRAG local daemon.
 */

import { App } from "obsidian";
import { connectEventStream } from "./client_events";

import {
  DiscoverEstimateOptions,
  DiscoverOptions,
  DiscoveryEstimate,
  GapsResponse,
  HealthResponse,
  IngestOptions,
  LlmTestResponse,
  NoteContext,
  PkmragPluginSettings,
  SearchResponse,
  SearchResult,
  SemanticGapCandidate,
  SyncResult,
} from "./types";


export class PkmragClient {
  constructor(public settings: PkmragPluginSettings, public app?: App) {}

  /** Attempt to read .pkmrag/server_token from active vault filesystem. */
  async autoDiscoverVaultToken(app?: App): Promise<string | null> {
    const targetApp = app || this.app;
    try {
      if (targetApp?.vault?.adapter) {
        if (await targetApp.vault.adapter.exists(".pkmrag/server_token")) {
          const content = (await targetApp.vault.adapter.read(".pkmrag/server_token")).trim();
          if (content.length > 0) {
            this.settings.authToken = content;
            return content;
          }
        }
      }
    } catch (err) {
      console.warn("[PKMRAG] Could not auto-read server_token:", err);
    }
    return null;
  }

  async ensureAuthToken(): Promise<void> {
    if (!this.settings.authToken || this.settings.authToken.trim().length === 0) {
      await this.autoDiscoverVaultToken();
    }
  }

  private getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (this.settings.authToken && this.settings.authToken.trim().length > 0) {
      const tok = this.settings.authToken.trim();
      headers["Authorization"] = `Bearer ${tok}`;
      headers["X-Pkmrag-Token"] = tok;
    }
    return headers;
  }

  /** Health probe verifying PKMRAG daemon connectivity. */
  async checkHealth(): Promise<HealthResponse> {
    const url = `${this.settings.serverUrl.replace(/\/+$/, "")}/health`;
    const res = await fetch(url, { method: "GET" });
    if (!res.ok) throw new Error(`Health check failed with HTTP ${res.status}`);
    return (await res.json()) as HealthResponse;
  }

  /** Ask running PKMRAG daemon to cleanly shut down. */
  async requestShutdown(): Promise<boolean> {
    try {
      await this.ensureAuthToken();
      const base = this.settings.serverUrl.replace(/\/+$/, "");
      const res = await fetch(`${base}/api/v1/shutdown`, {
        method: "POST",
        headers: this.getHeaders(),
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  /** Retrieve graph context for a note. */
  async getNoteContext(notePath: string): Promise<NoteContext | null> {
    await this.ensureAuthToken();
    const base = this.settings.serverUrl.replace(/\/+$/, "");
    const url = `${base}/api/v1/context?note_path=${encodeURIComponent(notePath)}`;
    const res = await fetch(url, { method: "GET", headers: this.getHeaders() });
    if (res.status === 404) return null;
    if (res.status === 503) throw new Error("VAULT_UNINDEXED");
    if (!res.ok) throw new Error(`Context fetch failed with HTTP ${res.status}`);
    return (await res.json()) as NoteContext;
  }

  /** Retrieve unlinked note candidates with high semantic similarity. */
  async getGaps(
    notePath?: string,
    threshold?: number,
    limit?: number
  ): Promise<SemanticGapCandidate[]> {
    await this.ensureAuthToken();
    const base = this.settings.serverUrl.replace(/\/+$/, "");
    const thresh = threshold ?? this.settings.similarityThreshold;
    const lim = limit ?? 50;
    let url = `${base}/api/v1/gaps?threshold=${thresh}&limit=${lim}`;
    if (notePath) url += `&note_path=${encodeURIComponent(notePath)}`;

    const res = await fetch(url, { method: "GET", headers: this.getHeaders() });
    if (res.status === 503) throw new Error("VAULT_UNINDEXED");
    if (!res.ok) throw new Error(`Gaps fetch failed with HTTP ${res.status}`);
    const data = (await res.json()) as GapsResponse;
    return data.candidates || [];
  }

  /** Incrementally reindex a single note after edits and evict stale cache. */
  async reindexNote(notePath: string): Promise<SyncResult> {
    await this.ensureAuthToken();
    const base = this.settings.serverUrl.replace(/\/+$/, "");
    const url = `${base}/api/v1/reindex`;
    const res = await fetch(url, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify({ note_path: notePath }),
    });
    if (!res.ok) throw new Error(`Reindex failed with HTTP ${res.status}`);
    return (await res.json()) as SyncResult;
  }

  /** Delta synchronize all modified or newly created vault notes. */
  async syncVault(): Promise<SyncResult[]> {
    await this.ensureAuthToken();
    const base = this.settings.serverUrl.replace(/\/+$/, "");
    const url = `${base}/api/v1/sync`;
    const res = await fetch(url, { method: "POST", headers: this.getHeaders() });
    if (!res.ok) throw new Error(`Vault sync failed with HTTP ${res.status}`);
    const data = await res.json();
    return data.results || [];
  }

  /** Search knowledge base chunks biased by graph proximity to an anchor note. */
  async searchVault(query: string, near?: string, limit?: number): Promise<SearchResult[]> {
    await this.ensureAuthToken();
    const base = this.settings.serverUrl.replace(/\/+$/, "");
    const url = `${base}/api/v1/search`;
    const payload: Record<string, unknown> = { query: query.trim(), limit: limit || 5 };
    if (near) payload.near = near;

    const res = await fetch(url, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`Search failed with HTTP ${res.status}`);
    const data = (await res.json()) as SearchResponse;
    return data.results || [];
  }

  /** Subscribe to live SSE events from PKMRAG server. */
  connectEvents(onEvent: (event: string, data: Record<string, unknown>) => void): EventSource | null {
    return connectEventStream(this.settings.serverUrl, this.settings.authToken, onEvent);
  }

  /** Test LLM connection, latency, and schema formatting. */
  async testLlm(payload?: Record<string, unknown>): Promise<LlmTestResponse> {
    await this.ensureAuthToken();
    const base = this.settings.serverUrl.replace(/\/+$/, "");
    const body = payload || {
      provider: this.settings.llmProvider,
      base_url: this.settings.llmBaseUrl,
      model: this.settings.llmModel,
      api_key: this.settings.llmApiKey,
    };
    const res = await fetch(`${base}/api/v1/llm/test`, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`LLM test failed with HTTP ${res.status}`);
    return (await res.json()) as LlmTestResponse;
  }

  private async postJson<T>(endpoint: string, payload: unknown): Promise<T> {
    await this.ensureAuthToken();
    const base = this.settings.serverUrl.replace(/\/+$/, "");
    let res = await fetch(`${base}${endpoint}`, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify(payload),
    });
    if (res.status === 401) {
      await this.autoDiscoverVaultToken();
      res = await fetch(`${base}${endpoint}`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify(payload),
      });
    }
    if (!res.ok) throw new Error(`Request to ${endpoint} failed with HTTP ${res.status}`);
    return (await res.json()) as T;
  }

  /** Trigger vault ingestion / full rebuild in background. */
  async triggerIngest(options?: IngestOptions): Promise<{ status: string; message: string }> {
    return this.postJson<{ status: string; message: string }>("/api/v1/ingest", options || {});
  }

  /** Pre-flight token and candidate estimation for AI gap discovery. */
  async estimateDiscover(options?: DiscoverEstimateOptions): Promise<DiscoveryEstimate> {
    return this.postJson<DiscoveryEstimate>("/api/v1/discover/estimate", {
      threshold: options?.threshold ?? this.settings.similarityThreshold,
      limit: options?.limit ?? 20,
      note_path: options?.note_path,
      provider: options?.provider ?? this.settings.llmProvider,
      base_url: options?.base_url ?? this.settings.llmBaseUrl,
      model: options?.model ?? this.settings.llmModel,
      api_key: options?.api_key ?? this.settings.llmApiKey,
    });
  }

  /** Trigger AI semantic gap discovery and relationship inference. */
  async triggerDiscover(options?: DiscoverOptions): Promise<{ status: string; message: string }> {
    return this.postJson<{ status: string; message: string }>("/api/v1/discover", {
      threshold: options?.threshold ?? this.settings.similarityThreshold,
      limit: options?.limit ?? 20,
      dry_run: options?.dry_run ?? false,
      note_path: options?.note_path,
      provider: options?.provider ?? this.settings.llmProvider,
      base_url: options?.base_url ?? this.settings.llmBaseUrl,
      model: options?.model ?? this.settings.llmModel,
      api_key: options?.api_key ?? this.settings.llmApiKey,
    });
  }

  /**
   * Fetch vault runtime settings from backend.
   */
  async getVaultConfig(): Promise<Record<string, unknown>> {
    const base = this.settings.serverUrl.replace(/\/+$/, "");
    const res = await fetch(`${base}/api/v1/settings`, {
      method: "GET",
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      throw new Error(`Settings fetch failed with HTTP ${res.status}`);
    }
    return (await res.json()) as Record<string, unknown>;
  }

  /**
   * Save vault runtime settings to backend.
   */
  async saveVaultConfig(cfg: Record<string, unknown>): Promise<Record<string, unknown>> {
    const base = this.settings.serverUrl.replace(/\/+$/, "");
    const res = await fetch(`${base}/api/v1/settings`, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify(cfg),
    });
    if (!res.ok) {
      throw new Error(`Settings save failed with HTTP ${res.status}`);
    }
    return (await res.json()) as Record<string, unknown>;
  }
}

