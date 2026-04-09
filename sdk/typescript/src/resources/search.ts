import { HttpClient } from "../http.js";
import type {
  SearchResult,
  VectorResult,
  SearchOptions,
  HybridSearchOptions,
  TimingInfo,
} from "../types.js";

export class SearchResource {
  constructor(private readonly http: HttpClient) {}

  async search(
    collection: string,
    vector?: number[],
    options: SearchOptions & { text?: string } = {}
  ): Promise<SearchResult> {
    const { k = 10, offset = 0, filters, includeTiming, text } = options;
    const body: Record<string, unknown> = { k, offset };
    if (vector !== undefined) body.vector = vector;
    if (text !== undefined) body.text = text;
    if (filters !== undefined) body.filters = filters;
    if (includeTiming) body.include_timing = true;

    const data = await this.http.request<{
      results: VectorResult[];
      total_count: number;
      k: number;
      offset: number;
      timing_ms?: TimingInfo;
    }>("POST", `/v1/collections/${collection}/search`, { body });

    return {
      results: data.results,
      collection,
      k: data.k ?? k,
      total_count: data.total_count ?? -1,
      offset: data.offset ?? offset,
      ...(data.timing_ms !== undefined && { timing_ms: data.timing_ms }),
    };
  }

  async recommend(
    collection: string,
    externalId: string,
    options: Omit<SearchOptions, "filters"> = {}
  ): Promise<SearchResult> {
    const { k = 10, offset = 0 } = options;
    const data = await this.http.request<{ results: VectorResult[] }>(
      "POST",
      `/v1/collections/${collection}/recommend/${externalId}`,
      { body: { k, offset } }
    );
    return { results: data.results, collection, k, total_count: -1, offset };
  }

  async similarity(
    collection: string,
    id1: string,
    id2: string
  ): Promise<number> {
    const data = await this.http.request<{ score: number }>(
      "POST",
      `/v1/collections/${collection}/similarity`,
      { params: { id1, id2 }, body: {} }
    );
    return data.score;
  }

  async rerank(
    collection: string,
    queryVector?: number[],
    candidates?: string[],
    options?: { text?: string; includeTiming?: boolean }
  ): Promise<VectorResult[]> {
    const body: Record<string, unknown> = {};
    if (queryVector !== undefined) body.vector = queryVector;
    if (candidates !== undefined) body.candidates = candidates;
    if (options?.text !== undefined) body.text = options.text;
    if (options?.includeTiming) body.include_timing = true;

    const data = await this.http.request<{ results: VectorResult[] }>(
      "POST",
      `/v1/collections/${collection}/rerank`,
      { body }
    );
    return data.results;
  }

  async hybridSearch(
    collection: string,
    queryText: string,
    vector?: number[],
    options: HybridSearchOptions = {}
  ): Promise<SearchResult> {
    const { k = 10, offset = 0, alpha = 0.5, filters, includeTiming } = options;
    const body: Record<string, unknown> = {
      query_text: queryText,
      k,
      offset,
      alpha,
    };
    if (vector !== undefined) body.vector = vector;
    if (filters !== undefined) body.filters = filters;
    if (includeTiming) body.include_timing = true;

    const data = await this.http.request<{
      results: VectorResult[];
      timing_ms?: TimingInfo;
    }>(
      "POST",
      `/v1/collections/${collection}/hybrid_search`,
      { body }
    );
    return {
      results: data.results,
      collection,
      k,
      total_count: -1,
      offset,
      ...(data.timing_ms !== undefined && { timing_ms: data.timing_ms }),
    };
  }
}
