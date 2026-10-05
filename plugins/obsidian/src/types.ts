/**
 * Data models and configuration interfaces for Orbit Insights Obsidian Plugin.
 */

export interface DismissedSuggestion {
  sourcePath: string;
  targetPath: string;
  targetTitle: string;
  dismissedAt: number;
}

export interface OrbitPluginSettings {
  serverUrl: string;
  authToken: string;
  autoSyncOnSave: boolean;
  autoRefreshOnNoteOpen: boolean;
  similarityThreshold: number;
  maxSuggestions: number;
  showInlineIndicators: boolean;
  dismissedSuggestions: Record<string, DismissedSuggestion>;
}

export const DEFAULT_SETTINGS: OrbitPluginSettings = {
  serverUrl: "http://127.0.0.1:3747",
  authToken: "",
  autoSyncOnSave: true,
  autoRefreshOnNoteOpen: true,
  similarityThreshold: 0.75,
  maxSuggestions: 5,
  showInlineIndicators: true,
  dismissedSuggestions: {},
};

export interface HealthResponse {
  status: string;
  version: string;
  vault: string;
  vault_path: string;
  transport: string;
  auth_enabled: boolean;
}

export interface InferredRelationship {
  source_path: string;
  target_path: string;
  rel_type: "EXTENDS" | "CONTRADICTS" | "SUPPORTS" | "PREREQUISITE_FOR" | "REFINES" | "NONE";
  confidence: number;
  reason: string;
  direction: string;
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

export interface SemanticGapCandidate {
  source_path: string;
  target_path: string;
  similarity: number;
  hops: number;
  source_title: string;
  target_title: string;
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

export interface SearchResult {
  path: string;
  title: string;
  chunk_id: string;
  heading: string;
  content: string;
  score: number;
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
