/**
 * Data types returned and accepted by the VectorDB SDK.
 */

export interface Collection {
  name: string;
  dim: number;
  distance_metric: string;
  vector_count: number;
  created_at?: string;
  description?: string | null;
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
  total_count: number;
  offset: number;
}

export interface ExportedVector {
  external_id: string;
  vector: number[];
  metadata: Record<string, unknown>;
}

export interface ExportResult {
  collection: string;
  dim: number;
  distance_metric: string;
  count: number;
  vectors: ExportedVector[];
}

export interface ApiKey {
  id: number;
  name: string;
  role: string;
  is_active: boolean;
  created_at: string;
  expires_at?: string | null;
  last_used_at?: string | null;
  key?: string; // only present at creation/rotation
}

export interface KeyUsageStats {
  total_requests: number;
  last_24h: number;
  last_7d: number;
  last_30d: number;
  by_endpoint: Record<string, number>;
  last_request_at?: string | null;
  key_id?: number;
  key_name?: string;
}

export interface UsageSummary {
  overall: KeyUsageStats;
  by_key: (KeyUsageStats & { key_name: string })[];
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
