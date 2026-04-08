import { HttpClient } from "../http.js";
import type { Collection, ExportResult } from "../types.js";

export class CollectionsResource {
  constructor(private readonly http: HttpClient) {}

  async create(
    name: string,
    dim: number,
    distanceMetric: "cosine" | "l2" | "ip" = "cosine",
    description?: string
  ): Promise<Collection> {
    const body: Record<string, unknown> = { name, dim, distance_metric: distanceMetric };
    if (description !== undefined) body.description = description;
    return this.http.request<Collection>("POST", "/v1/collections", { body });
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

  async update(name: string, description: string | null): Promise<Collection> {
    return this.http.request<Collection>("PATCH", `/v1/collections/${name}`, {
      body: { description },
    });
  }

  async export(name: string, limit = 10000): Promise<ExportResult> {
    return this.http.request<ExportResult>(
      "GET",
      `/v1/collections/${name}/export`,
      { params: { limit: String(limit) } }
    );
  }

  async delete(name: string): Promise<{ status: string; name: string }> {
    return this.http.request("DELETE", `/v1/collections/${name}`);
  }
}
