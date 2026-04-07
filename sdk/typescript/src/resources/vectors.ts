import { HttpClient } from "../http.js";
import type { UpsertResult, BulkUpsertResult, UpsertItem, BatchDeleteResult } from "../types.js";

export class VectorsResource {
  constructor(private readonly http: HttpClient) {}

  async upsert(
    collection: string,
    externalId: string,
    vector: number[],
    metadata?: Record<string, unknown>,
    namespace?: string
  ): Promise<UpsertResult> {
    const body: Record<string, unknown> = { external_id: externalId, vector };
    if (metadata !== undefined) body.metadata = metadata;
    if (namespace !== undefined) body.namespace = namespace;

    return this.http.request<UpsertResult>(
      "POST",
      `/v1/collections/${collection}/upsert`,
      { body }
    );
  }

  async bulkUpsert(
    collection: string,
    items: UpsertItem[]
  ): Promise<BulkUpsertResult> {
    // Normalize camelCase → snake_case for the API
    const apiItems = items.map((item) => ({
      external_id: item.external_id,
      vector: item.vector,
      ...(item.metadata !== undefined && { metadata: item.metadata }),
      ...(item.namespace !== undefined && { namespace: item.namespace }),
    }));

    return this.http.request<BulkUpsertResult>(
      "POST",
      `/v1/collections/${collection}/bulk_upsert`,
      { body: { items: apiItems } }
    );
  }

  async delete(
    collection: string,
    externalId: string
  ): Promise<{ status: string; external_id: string }> {
    return this.http.request(
      "DELETE",
      `/v1/collections/${collection}/delete/${externalId}`
    );
  }

  async deleteBatch(
    collection: string,
    ids: string[]
  ): Promise<BatchDeleteResult> {
    return this.http.request<BatchDeleteResult>(
      "POST",
      `/v1/collections/${collection}/delete_batch`,
      { body: { external_ids: ids } }
    );
  }
}
