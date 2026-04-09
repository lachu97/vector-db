/**
 * Query resource — RAG semantic search returning text chunks.
 */
import { HttpClient } from "../http.js";
import type { QueryResult, QueryOptions } from "../types.js";

export class QueryResource {
  constructor(private readonly http: HttpClient) {}

  /**
   * Run a natural-language query against a collection.
   *
   * @param query - The query text.
   * @param collectionName - Collection to search in.
   * @param options - Optional top_k and filters.
   * @returns QueryResult containing matching text chunks with scores.
   */
  async query(
    query: string,
    collectionName: string,
    options: QueryOptions = {}
  ): Promise<QueryResult> {
    const { top_k = 5, filters, includeTiming } = options;
    const body: Record<string, unknown> = {
      query,
      collection_name: collectionName,
      top_k,
    };
    if (filters !== undefined) body.filters = filters;
    if (includeTiming) body.include_timing = true;

    return this.http.request<QueryResult>("POST", "/v1/query", { body });
  }
}
