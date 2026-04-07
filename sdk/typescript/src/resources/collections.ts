import { HttpClient } from "../http.js";
import type { Collection } from "../types.js";

export class CollectionsResource {
  constructor(private readonly http: HttpClient) {}

  async create(
    name: string,
    dim: number,
    distanceMetric: "cosine" | "l2" | "ip" = "cosine"
  ): Promise<Collection> {
    return this.http.request<Collection>("POST", "/v1/collections", {
      body: { name, dim, distance_metric: distanceMetric },
    });
  }

  async list(): Promise<Collection[]> {
    const data = await this.http.request<{ collections: Collection[] }>(
      "GET",
      "/v1/collections"
    );
    return data.collections;
  }

  async get(name: string): Promise<Collection> {
    return this.http.request<Collection>("GET", `/v1/collections/${name}`);
  }

  async delete(name: string): Promise<{ status: string; name: string }> {
    return this.http.request("DELETE", `/v1/collections/${name}`);
  }
}
