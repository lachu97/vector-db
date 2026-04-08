/**
 * Tests for new SDK features: description, export, total_count, keys resource.
 */

import { VectorDBClient } from "../client.js";
import type { ApiResponse } from "../types.js";

function ok<T>(data: T): ApiResponse<T> {
  return { status: "success", data, error: null };
}

function mockFetch(responses: Array<{ body: unknown; status?: number }>): jest.Mock {
  let call = 0;
  return jest.fn().mockImplementation(async () => {
    const r = responses[call++ % responses.length];
    const status = r.status ?? 200;
    return { ok: status >= 200 && status < 300, status, json: async () => r.body };
  });
}

function makeClient(fetch: jest.Mock): VectorDBClient {
  return new VectorDBClient({ baseUrl: "http://localhost:8000", apiKey: "test-key", fetch });
}

// ---------------------------------------------------------------------------
// Collection description
// ---------------------------------------------------------------------------

describe("collections.create with description", () => {
  test("sends description in body", async () => {
    const fetch = mockFetch([{
      body: ok({ name: "col", dim: 4, distance_metric: "cosine", vector_count: 0, description: "my desc" }),
    }]);
    const client = makeClient(fetch);
    const col = await client.collections.create("col", 4, "cosine", "my desc");
    expect(col.description).toBe("my desc");
    const [, init] = fetch.mock.calls[0];
    expect(JSON.parse(init.body).description).toBe("my desc");
  });

  test("omits description when not provided", async () => {
    const fetch = mockFetch([{
      body: ok({ name: "col", dim: 4, distance_metric: "cosine", vector_count: 0 }),
    }]);
    const client = makeClient(fetch);
    await client.collections.create("col", 4);
    const [, init] = fetch.mock.calls[0];
    expect(JSON.parse(init.body).description).toBeUndefined();
  });
});

describe("collections.update", () => {
  test("sends PATCH with description", async () => {
    const fetch = mockFetch([{
      body: ok({ name: "col", dim: 4, distance_metric: "cosine", vector_count: 0, description: "updated" }),
    }]);
    const client = makeClient(fetch);
    const col = await client.collections.update("col", "updated");
    expect(col.description).toBe("updated");
    const [url] = fetch.mock.calls[0];
    expect(url).toContain("/v1/collections/col");
  });

  test("sends null to clear description", async () => {
    const fetch = mockFetch([{
      body: ok({ name: "col", dim: 4, distance_metric: "cosine", vector_count: 0, description: null }),
    }]);
    const client = makeClient(fetch);
    const col = await client.collections.update("col", null);
    expect(col.description).toBeNull();
  });
});

describe("collections.export", () => {
  test("returns ExportResult", async () => {
    const fetch = mockFetch([{
      body: ok({
        collection: "col", dim: 4, distance_metric: "cosine", count: 2,
        vectors: [
          { external_id: "a", vector: [1, 2, 3, 4], metadata: {} },
          { external_id: "b", vector: [5, 6, 7, 8], metadata: {} },
        ],
      }),
    }]);
    const client = makeClient(fetch);
    const result = await client.collections.export("col");
    expect(result.count).toBe(2);
    expect(result.vectors).toHaveLength(2);
    expect(result.vectors[0].external_id).toBe("a");
    expect(result.vectors[0].vector).toHaveLength(4);
  });

  test("passes limit as query param", async () => {
    const fetch = mockFetch([{
      body: ok({ collection: "col", dim: 4, distance_metric: "cosine", count: 0, vectors: [] }),
    }]);
    const client = makeClient(fetch);
    await client.collections.export("col", 500);
    const [url] = fetch.mock.calls[0];
    expect(url).toContain("limit=500");
  });
});

// ---------------------------------------------------------------------------
// Search total_count
// ---------------------------------------------------------------------------

describe("search.search total_count", () => {
  test("returns total_count and offset", async () => {
    const fetch = mockFetch([{
      body: ok({ results: [], total_count: 42, k: 10, offset: 0 }),
    }]);
    const client = makeClient(fetch);
    const result = await client.search.search("col", [1, 2, 3, 4], { k: 10 });
    expect(result.total_count).toBe(42);
    expect(result.offset).toBe(0);
    expect(result.k).toBe(10);
  });

  test("defaults total_count to -1 when missing", async () => {
    const fetch = mockFetch([{
      body: ok({ results: [] }),
    }]);
    const client = makeClient(fetch);
    const result = await client.search.search("col", [1, 2, 3, 4]);
    expect(result.total_count).toBe(-1);
  });
});

// ---------------------------------------------------------------------------
// AdminKeysResource
// ---------------------------------------------------------------------------

describe("keys.create", () => {
  test("creates a key and returns it", async () => {
    const fetch = mockFetch([{
      body: ok({ id: 1, name: "prod", role: "readwrite", is_active: true, created_at: "2026-01-01", key: "abc123" }),
    }]);
    const client = makeClient(fetch);
    const key = await client.keys.create("prod", "readwrite");
    expect(key.id).toBe(1);
    expect(key.key).toBe("abc123");
    expect(key.role).toBe("readwrite");
  });

  test("sends expires_in_days when provided", async () => {
    const fetch = mockFetch([{
      body: ok({ id: 2, name: "tmp", role: "readonly", is_active: true, created_at: "2026-01-01", key: "xyz" }),
    }]);
    const client = makeClient(fetch);
    await client.keys.create("tmp", "readonly", 30);
    const [, init] = fetch.mock.calls[0];
    expect(JSON.parse(init.body).expires_in_days).toBe(30);
  });
});

describe("keys.list", () => {
  test("returns array of keys", async () => {
    const fetch = mockFetch([{
      body: ok({ keys: [
        { id: 1, name: "k1", role: "admin", is_active: true, created_at: "2026-01-01" },
        { id: 2, name: "k2", role: "readonly", is_active: false, created_at: "2026-01-02" },
      ]}),
    }]);
    const client = makeClient(fetch);
    const keys = await client.keys.list();
    expect(keys).toHaveLength(2);
    expect(keys[0].name).toBe("k1");
    expect(keys[1].is_active).toBe(false);
  });
});

describe("keys.revoke and restore", () => {
  test("revoke sends is_active: false", async () => {
    const fetch = mockFetch([{
      body: ok({ id: 1, name: "k", role: "readonly", is_active: false, created_at: "2026-01-01" }),
    }]);
    const client = makeClient(fetch);
    const key = await client.keys.revoke(1);
    expect(key.is_active).toBe(false);
    const [, init] = fetch.mock.calls[0];
    expect(JSON.parse(init.body).is_active).toBe(false);
  });

  test("restore sends is_active: true", async () => {
    const fetch = mockFetch([{
      body: ok({ id: 1, name: "k", role: "readonly", is_active: true, created_at: "2026-01-01" }),
    }]);
    const client = makeClient(fetch);
    const key = await client.keys.restore(1);
    expect(key.is_active).toBe(true);
  });
});

describe("keys.rotate", () => {
  test("returns new key value", async () => {
    const fetch = mockFetch([{
      body: ok({ id: 1, name: "k", role: "readwrite", is_active: true, created_at: "2026-01-01", key: "new-secret" }),
    }]);
    const client = makeClient(fetch);
    const key = await client.keys.rotate(1);
    expect(key.key).toBe("new-secret");
  });
});

describe("keys.getUsage", () => {
  test("returns usage stats", async () => {
    const fetch = mockFetch([{
      body: ok({
        key_id: 1, key_name: "prod",
        total_requests: 100, last_24h: 10, last_7d: 50, last_30d: 100,
        by_endpoint: { "/v1/collections": 60 },
      }),
    }]);
    const client = makeClient(fetch);
    const usage = await client.keys.getUsage(1);
    expect(usage.total_requests).toBe(100);
    expect(usage.by_endpoint["/v1/collections"]).toBe(60);
  });
});

describe("keys.getUsageSummary", () => {
  test("returns overall and by_key", async () => {
    const fetch = mockFetch([{
      body: ok({
        overall: { total_requests: 200, last_24h: 20, last_7d: 100, last_30d: 200, by_endpoint: {} },
        by_key: [{ key_name: "prod", total_requests: 150 }],
      }),
    }]);
    const client = makeClient(fetch);
    const summary = await client.keys.getUsageSummary();
    expect(summary.overall.total_requests).toBe(200);
    expect(summary.by_key).toHaveLength(1);
  });
});

describe("keys.delete", () => {
  test("returns deleted: true", async () => {
    const fetch = mockFetch([{
      body: ok({ deleted: true, id: 1, name: "k" }),
    }]);
    const client = makeClient(fetch);
    const result = await client.keys.delete(1);
    expect(result.deleted).toBe(true);
  });
});
