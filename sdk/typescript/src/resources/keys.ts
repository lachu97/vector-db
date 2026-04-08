import { HttpClient } from "../http.js";
import type { ApiKey, KeyUsageStats, UsageSummary } from "../types.js";

export class AdminKeysResource {
  constructor(private readonly http: HttpClient) {}

  async create(
    name: string,
    role: "admin" | "readwrite" | "readonly" = "readwrite",
    expiresInDays?: number
  ): Promise<ApiKey> {
    const body: Record<string, unknown> = { name, role };
    if (expiresInDays !== undefined) body.expires_in_days = expiresInDays;
    return this.http.request<ApiKey>("POST", "/v1/admin/keys", { body });
  }

  async list(): Promise<ApiKey[]> {
    const data = await this.http.request<{ keys: ApiKey[] }>("GET", "/v1/admin/keys");
    return data.keys;
  }

  async get(keyId: number): Promise<ApiKey> {
    return this.http.request<ApiKey>("GET", `/v1/admin/keys/${keyId}`);
  }

  async update(
    keyId: number,
    changes: { name?: string; role?: string; is_active?: boolean }
  ): Promise<ApiKey> {
    return this.http.request<ApiKey>("PATCH", `/v1/admin/keys/${keyId}`, {
      body: changes,
    });
  }

  async revoke(keyId: number): Promise<ApiKey> {
    return this.update(keyId, { is_active: false });
  }

  async restore(keyId: number): Promise<ApiKey> {
    return this.update(keyId, { is_active: true });
  }

  async rotate(keyId: number): Promise<ApiKey> {
    return this.http.request<ApiKey>("POST", `/v1/admin/keys/${keyId}/rotate`);
  }

  async delete(keyId: number): Promise<{ deleted: boolean; id: number }> {
    return this.http.request("DELETE", `/v1/admin/keys/${keyId}`);
  }

  async getUsage(keyId: number): Promise<KeyUsageStats> {
    return this.http.request<KeyUsageStats>(
      "GET",
      `/v1/admin/keys/${keyId}/usage`
    );
  }

  async getUsageSummary(): Promise<UsageSummary> {
    return this.http.request<UsageSummary>(
      "GET",
      "/v1/admin/keys/usage/summary"
    );
  }
}
