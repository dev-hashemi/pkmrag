/**
 * HTTP and SSE Client communicating with Project Orbit local daemon.
 */

import { App } from "obsidian";
import {
  GapsResponse,
  HealthResponse,
  NoteContext,
  OrbitPluginSettings,
  SearchResponse,
  SearchResult,
  SemanticGapCandidate,
  SyncResult,
} from "./types";

export class OrbitClient {
  constructor(public settings: OrbitPluginSettings) {}

  /**
   * Attempt to read .pkmrag/server_token or .orbit/server_token from active vault filesystem.
   */
  async autoDiscoverVaultToken(app: App): Promise<string | null> {
    try {
      for (const tokenPath of [".pkmrag/server_token", ".orbit/server_token"]) {
        const exists = await app.vault.adapter.exists(tokenPath);
        if (exists) {
          const content = await app.vault.adapter.read(tokenPath);
          const trimmed = content.trim();
          if (trimmed.length > 0) {
            this.settings.authToken = trimmed;
            return trimmed;
          }
        }
      }
    } catch (err) {
      console.warn("[PKMRAG] Could not auto-read server_token:", err);
    }
    return null;
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

  /**
   * Health probe verifying Orbit daemon connectivity.
   */
  async checkHealth(): Promise<HealthResponse> {
    const url = `${this.settings.serverUrl.replace(/\/+$/, "")}/health`;
    const res = await fetch(url, { method: "GET" });
    if (!res.ok) {
      throw new Error(`Health check failed with HTTP ${res.status}`);
    }
    return (await res.json()) as HealthResponse;
  }

  /**
   * Retrieve graph context (outgoing links, backlinks, tags, AI inferences) for a note.
   */
  async getNoteContext(notePath: string): Promise<NoteContext | null> {
    const base = this.settings.serverUrl.replace(/\/+$/, "");
    const url = `${base}/api/v1/context?note_path=${encodeURIComponent(notePath)}`;
    const res = await fetch(url, {
      method: "GET",
      headers: this.getHeaders(),
    });

    if (res.status === 404) {
      return null;
    }
    if (!res.ok) {
      throw new Error(`Context fetch failed with HTTP ${res.status}`);
    }
    return (await res.json()) as NoteContext;
  }

  /**
   * Retrieve unlinked note candidates with high semantic similarity.
   */
  async getGaps(
    notePath?: string,
    threshold?: number,
    limit?: number
  ): Promise<SemanticGapCandidate[]> {
    const base = this.settings.serverUrl.replace(/\/+$/, "");
    const thresh = threshold ?? this.settings.similarityThreshold;
    const lim = limit ?? this.settings.maxSuggestions;
    let url = `${base}/api/v1/gaps?threshold=${thresh}&limit=${lim}`;
    if (notePath) {
      url += `&note_path=${encodeURIComponent(notePath)}`;
    }

    const res = await fetch(url, {
      method: "GET",
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      throw new Error(`Gaps fetch failed with HTTP ${res.status}`);
    }
    const data = (await res.json()) as GapsResponse;
    return data.candidates || [];
  }

  /**
   * Incrementally reindex a single note after edits and evict stale cache.
   */
  async reindexNote(notePath: string): Promise<SyncResult> {
    const base = this.settings.serverUrl.replace(/\/+$/, "");
    const url = `${base}/api/v1/reindex`;
    const res = await fetch(url, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify({ note_path: notePath }),
    });
    if (!res.ok) {
      throw new Error(`Reindex failed with HTTP ${res.status}`);
    }
    return (await res.json()) as SyncResult;
  }

  /**
   * Delta synchronize all modified or newly created vault notes.
   */
  async syncVault(): Promise<SyncResult[]> {
    const base = this.settings.serverUrl.replace(/\/+$/, "");
    const url = `${base}/api/v1/sync`;
    const res = await fetch(url, {
      method: "POST",
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      throw new Error(`Vault sync failed with HTTP ${res.status}`);
    }
    const data = await res.json();
    return data.results || [];
  }

  /**
   * Search knowledge base chunks biased by graph proximity to an anchor note.
   */
  async searchVault(
    query: string,
    near?: string,
    limit?: number
  ): Promise<SearchResult[]> {
    const base = this.settings.serverUrl.replace(/\/+$/, "");
    const url = `${base}/api/v1/search`;
    const payload: Record<string, unknown> = {
      query: query.trim(),
      limit: limit || 5,
    };
    if (near) {
      payload.near = near;
    }

    const res = await fetch(url, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`Search failed with HTTP ${res.status}`);
    }
    const data = (await res.json()) as SearchResponse;
    return data.results || [];
  }

  /**
   * Subscribe to live SSE events from Orbit server.
   */
  connectEvents(
    onEvent: (event: string, data: Record<string, unknown>) => void
  ): EventSource | null {
    if (typeof EventSource === "undefined") {
      return null;
    }
    try {
      const base = this.settings.serverUrl.replace(/\/+$/, "");
      const tokenParam = this.settings.authToken
        ? `?token=${encodeURIComponent(this.settings.authToken)}`
        : "";
      const source = new EventSource(`${base}/api/v1/events${tokenParam}`);

      source.addEventListener("reindex", (e: MessageEvent) => {
        try {
          onEvent("reindex", JSON.parse(e.data));
        } catch {}
      });

      source.addEventListener("sync", (e: MessageEvent) => {
        try {
          onEvent("sync", JSON.parse(e.data));
        } catch {}
      });

      return source;
    } catch (err) {
      console.warn("[Orbit] Could not establish EventSource stream:", err);
      return null;
    }
  }
}
