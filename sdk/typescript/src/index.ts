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

export type {
  ApiKey,
  Collection,
  ExportedVector,
  ExportResult,
  KeyUsageStats,
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
} from "./types.js";
