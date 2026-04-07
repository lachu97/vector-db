/**
 * Data types returned and accepted by the VectorDB SDK.
 */

export interface Collection {
  name: string;
  dim: number;
  distance_metric: string;
  vector_count: number;
  created_at?: string;
}

export interface UpsertResult {
  external_id: string;
  status: "inserted" | "updated";
}

export interface BulkUpsertResult {
  results: UpsertResult[];
}

export interface VectorResult {
  external_id: string;
  score: number;
  metadata: Record<string, unknown>;
}

export interface SearchResult {
  results: VectorResult[];
  collection: string;
  k: number;
}

export interface HealthStats {
  status: string;
  total_vectors: number;
  total_collections: number;
  collections: CollectionStats[];
  uptime_seconds?: number;
}

export interface CollectionStats {
  name: string;
  vector_count: number;
  dim: number;
}

export interface DeleteResult {
  status: string;
  name?: string;
}

export interface BatchDeleteResult {
  deleted: string[];
  not_found: string[];
  deleted_count: number;
}

// Request payloads

export interface UpsertItem {
  external_id: string;
  vector: number[];
  metadata?: Record<string, unknown>;
  namespace?: string;
}

export interface SearchOptions {
  k?: number;
  offset?: number;
  filters?: Record<string, unknown>;
}

export interface HybridSearchOptions extends SearchOptions {
  alpha?: number;
}

/** Internal API response envelope. */
export interface ApiResponse<T = unknown> {
  status: "success" | "error";
  data: T | null;
  error: { code: number; message: string } | null;
}
