import { HttpClient } from "../http.js";
import type {
  SearchResult,
  VectorResult,
  SearchOptions,
  HybridSearchOptions,
} from "../types.js";

export class SearchResource {
  constructor(private readonly http: HttpClient) {}

  async search(
    collection: string,
    vector: number[],
    options: SearchOptions = {}
  ): Promise<SearchResult> {
    const { k = 10, offset = 0, filters } = options;
    const body: Record<string, unknown> = { vector, k, offset };
    if (filters !== undefined) body.filters = filters;

    const data = await this.http.request<{
      results: VectorResult[];
      total_count: number;
      k: number;
      offset: number;
    }>("POST", `/v1/collections/${collection}/search`, { body });

    return {
      results: data.results,
      collection,
      k: data.k ?? k,
      total_count: data.total_count ?? -1,
      offset: data.offset ?? offset,
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
    queryVector: number[],
    candidates: string[]
  ): Promise<VectorResult[]> {
    const data = await this.http.request<{ results: VectorResult[] }>(
      "POST",
      `/v1/collections/${collection}/rerank`,
      { body: { vector: queryVector, candidates } }
    );
    return data.results;
  }

  async hybridSearch(
    collection: string,
    queryText: string,
    vector: number[],
    options: HybridSearchOptions = {}
  ): Promise<SearchResult> {
    const { k = 10, offset = 0, alpha = 0.5, filters } = options;
    const body: Record<string, unknown> = {
      query_text: queryText,
      vector,
      k,
      offset,
      alpha,
    };
    if (filters !== undefined) body.filters = filters;

    const data = await this.http.request<{ results: VectorResult[] }>(
      "POST",
      `/v1/collections/${collection}/hybrid_search`,
      { body }
    );
    return { results: data.results, collection, k, total_count: -1, offset };
  }
}
