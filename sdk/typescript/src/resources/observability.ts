import { HttpClient } from "../http.js";
import type { HealthStats } from "../types.js";

export class ObservabilityResource {
  constructor(private readonly http: HttpClient) {}

  async health(): Promise<HealthStats> {
    return this.http.request<HealthStats>("GET", "/v1/health");
  }
}
