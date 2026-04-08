/**
 * VectorDB TypeScript/JavaScript SDK client.
 *
 * Usage:
 *   const client = new VectorDBClient({ baseUrl: "http://localhost:8000", apiKey: "my-key" });
 *   await client.collections.create("my-col", 384, "cosine");
 *   await client.vectors.upsert("my-col", "doc-1", embeddingVector, { title: "Hello" });
 *   const results = await client.search.search("my-col", queryVector, { k: 5 });
 *   const key = await client.keys.create("my-app", "readwrite");
 */

import { HttpClient, type FetchFn } from "./http.js";
import { AdminKeysResource } from "./resources/keys.js";
import { CollectionsResource } from "./resources/collections.js";
import { VectorsResource } from "./resources/vectors.js";
import { SearchResource } from "./resources/search.js";
import { ObservabilityResource } from "./resources/observability.js";

export interface VectorDBClientOptions {
  /** Base URL of the VectorDB server, e.g. "http://localhost:8000" */
  baseUrl: string;
  /** API key for authentication */
  apiKey: string;
  /** Override the fetch implementation (useful for testing or Node < 18) */
  fetch?: FetchFn;
}

export class VectorDBClient {
  readonly collections: CollectionsResource;
  readonly vectors: VectorsResource;
  readonly search: SearchResource;
  readonly observability: ObservabilityResource;
  readonly keys: AdminKeysResource;

  private readonly http: HttpClient;

  constructor(options: VectorDBClientOptions) {
    this.http = new HttpClient(options.baseUrl, options.apiKey, options.fetch);
    this.collections = new CollectionsResource(this.http);
    this.vectors = new VectorsResource(this.http);
    this.search = new SearchResource(this.http);
    this.observability = new ObservabilityResource(this.http);
    this.keys = new AdminKeysResource(this.http);
  }

  /** Returns true if the server is reachable. */
  async ping(): Promise<boolean> {
    try {
      await this.http.request("GET", "/");
      return true;
    } catch {
      return false;
    }
  }
}
