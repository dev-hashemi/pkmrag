/**
 * Data models and configuration interfaces for PKMRAG Insights Obsidian Plugin.
 */

export interface DismissedSuggestion {
  sourcePath: string;
  targetPath: string;
  targetTitle: string;
  dismissedAt: number;
}

export interface PkmragPluginSettings {
  serverUrl: string;
  authToken: string;
  autoSyncOnSave: boolean;
  autoRefreshOnNoteOpen: boolean;
  similarityThreshold: number;
  maxSuggestions: number;
  showInlineIndicators: boolean;
  dismissedSuggestions: Record<string, DismissedSuggestion>;
  autoStartDaemon: boolean;
  customBinaryPath: string;
  llmProvider: "openai" | "ollama" | "custom";
  llmBaseUrl: string;
  llmModel: string;
  llmApiKey: string;
  llmRpm: number;
  llmTpm: number;
}

export const DEFAULT_SETTINGS: PkmragPluginSettings = {
  serverUrl: "http://127.0.0.1:3747",
  authToken: "",
  autoSyncOnSave: true,
  autoRefreshOnNoteOpen: true,
  similarityThreshold: 0.75,
  maxSuggestions: 5,
  showInlineIndicators: true,
  dismissedSuggestions: {},
  autoStartDaemon: true,
  customBinaryPath: "",
  llmProvider: "openai",
  llmBaseUrl: "https://api.openai.com/v1",
  llmModel: "gpt-4o-mini",
  llmApiKey: "",
  llmRpm: 30,
  llmTpm: 8000,
};

export interface LlmTestResponse {
  success: boolean;
  message: string;
  latency_ms: number;
  model?: string;
  provider?: string;
}

export interface DiscoverOptions {
  threshold?: number;
  limit?: number;
  dry_run?: boolean;
  provider?: string;
  model?: string;
  base_url?: string;
  api_key?: string;
}

export interface IngestOptions {
  rebuild?: boolean;
  dialect?: string;
  target?: string;
}


export interface ActiveJobState {
  type: "ingest" | "discover";
  /** Structured pipeline stage; mirrors pkmrag.models.IngestStage. */
  stage?: "scan" | "graph" | "model_download" | "vector" | string;
  /** Unit of `cur`/`total`; "bytes" for model downloads, "items" otherwise. */
  unit?: "items" | "bytes" | string;
  phase: string;
  cur: number;
  total: number;
  percent: number;
  message?: string;
  started_at?: number;
}

export interface TaskErrorState {
  type: "ingest" | "discover";
  message: string;
  timestamp: Date;
}

export interface HealthResponse {
  status: string;
  version: string;
  vault: string;
  vault_path: string;
  transport: string;
  auth_enabled: boolean;
  is_indexed?: boolean;
  active_job?: ActiveJobState | null;
  stats?: { notes: number; links: number; tags: number };
}

export interface InferredRelationship {
  source_path: string;
  target_path: string;
  rel_type: "EXTENDS" | "CONTRADICTS" | "SUPPORTS" | "PREREQUISITE_FOR" | "REFINES" | "NONE";
  confidence: number;
  reason: string;
  model?: string;
  created_at?: string;
}

export interface NoteContext {
  path: string;
  title: string;
  tags: string[];
  outgoing_links: string[];
  backlinks: string[];
  neighbors_2hop: string[];
  is_unresolved?: boolean;
  inferred_relationships?: InferredRelationship[];
}

/** Mirrors pkmrag.models.SemanticGapCandidate — keep in sync (tests/test_api_contract.py). */
export interface SemanticGapCandidate {
  source_path: string;
  target_path: string;
  source_title: string;
  target_title: string;
  similarity: number;
  hops: number;
  bridge_path: string[];
  source_chunk_id: string;
  target_chunk_id: string;
  source_chunk_text: string;
  target_chunk_text: string;
}

export interface GapsResponse {
  candidates: SemanticGapCandidate[];
  total: number;
  duration_ms: number;
}

export interface SyncResult {
  path: string;
  status: "indexed" | "unchanged" | "deleted" | "error";
  chunks_count: number;
  links_count: number;
  tags_count: number;
  ghosts_reconciled: number;
  cache_entries_evicted: number;
  duration_ms: number;
  error_message?: string;
}

/** Mirrors pkmrag.models.SearchResult — keep in sync (tests/test_api_contract.py). */
export interface SearchResult {
  chunk_id: string;
  note_path: string;
  note_title: string;
  heading: string;
  text: string;
  score: number;
  dense_score: number | null;
  sparse_score: number | null;
  graph_boost_factor: number;
  hop_distance: number | null;
}

export interface SearchResponse {
  results: SearchResult[];
  count: number;
}

export interface VaultOverview {
  total_notes: number;
  total_links: number;
  total_tags: number;
  hub_notes: Array<{ path: string; title: string; backlinks_count: number }>;
}
