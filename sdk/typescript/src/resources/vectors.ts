import { HttpClient } from "../http.js";
import type { UpsertResult, BulkUpsertResult, UpsertItem, BatchDeleteResult } from "../types.js";

export class VectorsResource {
  constructor(private readonly http: HttpClient) {}

  async upsert(
    collection: string,
    externalId: string,
    vector?: number[],
    metadata?: Record<string, unknown>,
    namespace?: string,
    options?: { text?: string; includeTiming?: boolean }
  ): Promise<UpsertResult> {
    const body: Record<string, unknown> = { external_id: externalId };
    if (vector !== undefined) body.vector = vector;
    if (options?.text !== undefined) body.text = options.text;
    if (metadata !== undefined) body.metadata = metadata;
    if (namespace !== undefined) body.namespace = namespace;
    if (options?.includeTiming) body.include_timing = true;

    return this.http.request<UpsertResult>(
      "POST",
      `/v1/collections/${collection}/upsert`,
      { body }
    );
  }

  async bulkUpsert(
    collection: string,
    items: UpsertItem[],
    options?: { includeTiming?: boolean }
  ): Promise<BulkUpsertResult> {
    // Normalize camelCase → snake_case for the API
    const apiItems = items.map((item) => ({
      external_id: item.external_id,
      ...(item.vector !== undefined && { vector: item.vector }),
      ...(item.text !== undefined && { text: item.text }),
      ...(item.metadata !== undefined && { metadata: item.metadata }),
      ...(item.namespace !== undefined && { namespace: item.namespace }),
    }));

    const body: Record<string, unknown> = { items: apiItems };
    if (options?.includeTiming) body.include_timing = true;

    return this.http.request<BulkUpsertResult>(
      "POST",
      `/v1/collections/${collection}/bulk_upsert`,
      { body }
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
