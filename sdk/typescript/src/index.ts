export { VectorDBClient } from "./client.js";
export type { VectorDBClientOptions } from "./client.js";

export {
  VectorDBError,
  NotFoundError,
  AlreadyExistsError,
  DimensionMismatchError,
  AuthenticationError,
  RateLimitError,
  ValidationError,
} from "./errors.js";

export type { AuthResponse } from "./resources/auth.js";

export type {
  ApiKey,
  Collection,
  DocumentUploadResult,
  ExportedVector,
  ExportResult,
  KeyUsageStats,
  QueryResult,
  QueryResultItem,
  QueryOptions,
  UsageSummary,
  UpsertResult,
  BulkUpsertResult,
  VectorResult,
  SearchResult,
  HealthStats,
  CollectionStats,
  DeleteResult,
  BatchDeleteResult,
  UpsertItem,
  SearchOptions,
  HybridSearchOptions,
  TimingInfo,
} from "./types.js";
