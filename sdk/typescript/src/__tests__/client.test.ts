/**
 * End-to-end tests for VectorDBClient — all resources, using fetch mocks.
 */

import { VectorDBClient } from "../client.js";
import {
  NotFoundError,
  AlreadyExistsError,
  DimensionMismatchError,
} from "../errors.js";
import type { ApiResponse } from "../types.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function ok<T>(data: T): ApiResponse<T> {
  return { status: "success", data, error: null };
}

function err(code: number, message: string): ApiResponse<null> {
  return { status: "error", data: null, error: { code, message } };
}

function mockFetch(
  responses: Array<{ body: unknown; status?: number }>
): jest.Mock {
  let call = 0;
  return jest.fn().mockImplementation(async () => {
    const r = responses[call++ % responses.length];
    const status = r.status ?? 200;
    return { ok: status >= 200 && status < 300, status, json: async () => r.body };
  });
}

function makeClient(fetch: jest.Mock): VectorDBClient {
  return new VectorDBClient({
    baseUrl: "http://localhost:8000",
    apiKey: "test-key",
    fetch,
  });
}

// ---------------------------------------------------------------------------
// CollectionsResource
// ---------------------------------------------------------------------------

describe("VectorDBClient.collections", () => {
  test("create returns a Collection", async () => {
    const fetch = mockFetch([
      {
        body: ok({
          name: "my-col",
          dim: 128,
          distance_metric: "cosine",
          vector_count: 0,
        }),
      },
    ]);
    const client = makeClient(fetch);
    const col = await client.collections.create("my-col", 128);
    expect(col.name).toBe("my-col");
    expect(col.dim).toBe(128);
    expect(col.distance_metric).toBe("cosine");
  });

  test("create sends distance_metric", async () => {
    const fetch = mockFetch([
      { body: ok({ name: "col", dim: 32, distance_metric: "l2", vector_count: 0 }) },
    ]);
    const client = makeClient(fetch);
    await client.collections.create("col", 32, "l2");
    const [, init] = fetch.mock.calls[0];
    expect(JSON.parse(init.body).distance_metric).toBe("l2");
  });

  test("list returns array of Collections", async () => {
    const fetch = mockFetch([
      {
        body: ok({
          collections: [
            { name: "a", dim: 8, distance_metric: "cosine", vector_count: 10 },
            { name: "b", dim: 16, distance_metric: "l2", vector_count: 5 },
          ],
        }),
      },
    ]);
    const client = makeClient(fetch);
    const cols = await client.collections.list();
    expect(cols).toHaveLength(2);
    expect(cols[0].name).toBe("a");
    expect(cols[1].name).toBe("b");
  });

  test("get returns a Collection", async () => {
    const fetch = mockFetch([
      { body: ok({ name: "my-col", dim: 128, distance_metric: "cosine", vector_count: 3 }) },
    ]);
    const client = makeClient(fetch);
    const col = await client.collections.get("my-col");
    expect(col.name).toBe("my-col");
    expect(col.vector_count).toBe(3);
  });

  test("get throws NotFoundError on 404 body", async () => {
    const fetch = mockFetch([{ body: err(404, "Collection 'missing' not found") }]);
    const client = makeClient(fetch);
    await expect(client.collections.get("missing")).rejects.toThrow(NotFoundError);
  });

  test("create throws AlreadyExistsError on 409 body", async () => {
    const fetch = mockFetch([{ body: err(409, "Collection 'dup' already exists") }]);
    const client = makeClient(fetch);
    await expect(client.collections.create("dup", 8)).rejects.toThrow(AlreadyExistsError);
  });

  test("delete returns status", async () => {
    const fetch = mockFetch([{ body: ok({ status: "deleted", name: "col" }) }]);
    const client = makeClient(fetch);
    const result = await client.collections.delete("col");
    expect(result.status).toBe("deleted");
  });
});

// ---------------------------------------------------------------------------
// VectorsResource
// ---------------------------------------------------------------------------

describe("VectorDBClient.vectors", () => {
  test("upsert insert", async () => {
    const fetch = mockFetch([
      { body: ok({ external_id: "v1", status: "inserted" }) },
    ]);
    const client = makeClient(fetch);
    const r = await client.vectors.upsert("col", "v1", [0.1, 0.2], { tag: "a" });
    expect(r.status).toBe("inserted");
    expect(r.external_id).toBe("v1");
  });

  test("upsert sends metadata and namespace", async () => {
    const fetch = mockFetch([
      { body: ok({ external_id: "v1", status: "inserted" }) },
    ]);
    const client = makeClient(fetch);
    await client.vectors.upsert("col", "v1", [0.1], { k: "v" }, "ns1");
    const [, init] = fetch.mock.calls[0];
    const body = JSON.parse(init.body);
    expect(body.metadata).toEqual({ k: "v" });
    expect(body.namespace).toBe("ns1");
  });

  test("upsert update", async () => {
    const fetch = mockFetch([
      { body: ok({ external_id: "v1", status: "updated" }) },
    ]);
    const client = makeClient(fetch);
    const r = await client.vectors.upsert("col", "v1", [0.1, 0.2]);
    expect(r.status).toBe("updated");
  });

  test("upsert throws DimensionMismatchError on 400 + dimension", async () => {
    const fetch = mockFetch([
      { body: err(400, "dimension mismatch: expected 8, got 128") },
    ]);
    const client = makeClient(fetch);
    await expect(client.vectors.upsert("col", "v1", Array(128).fill(0.1))).rejects.toThrow(
      DimensionMismatchError
    );
  });

  test("bulkUpsert returns results array", async () => {
    const fetch = mockFetch([
      {
        body: ok({
          results: [
            { external_id: "v1", status: "inserted" },
            { external_id: "v2", status: "inserted" },
          ],
        }),
      },
    ]);
    const client = makeClient(fetch);
    const r = await client.vectors.bulkUpsert("col", [
      { external_id: "v1", vector: [0.1] },
      { external_id: "v2", vector: [0.2] },
    ]);
    expect(r.results).toHaveLength(2);
    expect(r.results[0].status).toBe("inserted");
  });

  test("bulkUpsert sends external_ids correctly", async () => {
    const fetch = mockFetch([{ body: ok({ results: [] }) }]);
    const client = makeClient(fetch);
    await client.vectors.bulkUpsert("col", [{ external_id: "x", vector: [1] }]);
    const [, init] = fetch.mock.calls[0];
    const body = JSON.parse(init.body);
    expect(body.items[0].external_id).toBe("x");
  });

  test("delete returns status deleted", async () => {
    const fetch = mockFetch([
      { body: ok({ status: "deleted", external_id: "v1" }) },
    ]);
    const client = makeClient(fetch);
    const r = await client.vectors.delete("col", "v1");
    expect(r.status).toBe("deleted");
  });

  test("deleteBatch returns deleted_count", async () => {
    const fetch = mockFetch([
      { body: ok({ deleted: ["v1", "v2"], not_found: [], deleted_count: 2 }) },
    ]);
    const client = makeClient(fetch);
    const r = await client.vectors.deleteBatch("col", ["v1", "v2"]);
    expect(r.deleted_count).toBe(2);
    expect(r.deleted).toHaveLength(2);
  });

  test("deleteBatch sends external_ids key", async () => {
    const fetch = mockFetch([{ body: ok({ deleted: [], not_found: [], deleted_count: 0 }) }]);
    const client = makeClient(fetch);
    await client.vectors.deleteBatch("col", ["a", "b"]);
    const [, init] = fetch.mock.calls[0];
    const body = JSON.parse(init.body);
    expect(body.external_ids).toEqual(["a", "b"]);
  });
});

// ---------------------------------------------------------------------------
// SearchResource
// ---------------------------------------------------------------------------

describe("VectorDBClient.search", () => {
  const results = [
    { external_id: "v1", score: 0.95, metadata: { tag: "a" } },
    { external_id: "v2", score: 0.88, metadata: {} },
  ];

  test("search returns SearchResult with results", async () => {
    const fetch = mockFetch([{ body: ok({ results }) }]);
    const client = makeClient(fetch);
    const r = await client.search.search("col", [0.1, 0.2], { k: 5 });
    expect(r.results).toHaveLength(2);
    expect(r.k).toBe(5);
    expect(r.collection).toBe("col");
    expect(r.results[0].external_id).toBe("v1");
    expect(r.results[0].score).toBe(0.95);
  });

  test("search sends filters", async () => {
    const fetch = mockFetch([{ body: ok({ results: [] }) }]);
    const client = makeClient(fetch);
    await client.search.search("col", [0.1], { filters: { tag: "a" } });
    const [, init] = fetch.mock.calls[0];
    expect(JSON.parse(init.body).filters).toEqual({ tag: "a" });
  });

  test("search defaults k=10 offset=0", async () => {
    const fetch = mockFetch([{ body: ok({ results: [] }) }]);
    const client = makeClient(fetch);
    await client.search.search("col", [0.1]);
    const [, init] = fetch.mock.calls[0];
    const body = JSON.parse(init.body);
    expect(body.k).toBe(10);
    expect(body.offset).toBe(0);
  });

  test("recommend excludes target id from results", async () => {
    // The server handles the exclusion; we just verify the URL
    const fetch = mockFetch([{ body: ok({ results }) }]);
    const client = makeClient(fetch);
    const r = await client.search.recommend("col", "v1", { k: 3 });
    const [url] = fetch.mock.calls[0];
    expect(url).toContain("/recommend/v1");
    expect(r.results).toHaveLength(2);
  });

  test("similarity returns numeric score", async () => {
    const fetch = mockFetch([{ body: ok({ score: 0.97 }) }]);
    const client = makeClient(fetch);
    const score = await client.search.similarity("col", "v1", "v2");
    expect(score).toBeCloseTo(0.97);
    const [url] = fetch.mock.calls[0];
    expect(url).toContain("id1=v1");
    expect(url).toContain("id2=v2");
  });

  test("rerank returns sorted VectorResults", async () => {
    const fetch = mockFetch([{ body: ok({ results }) }]);
    const client = makeClient(fetch);
    const r = await client.search.rerank("col", [0.1, 0.2], ["v1", "v2"]);
    expect(r).toHaveLength(2);
    expect(r[0].score).toBe(0.95);
    const [, init] = fetch.mock.calls[0];
    const body = JSON.parse(init.body);
    expect(body.candidates).toEqual(["v1", "v2"]);
    expect(body.vector).toEqual([0.1, 0.2]);
  });

  test("hybridSearch sends query_text and alpha", async () => {
    const fetch = mockFetch([{ body: ok({ results }) }]);
    const client = makeClient(fetch);
    await client.search.hybridSearch("col", "hello world", [0.1], { alpha: 0.7 });
    const [, init] = fetch.mock.calls[0];
    const body = JSON.parse(init.body);
    expect(body.query_text).toBe("hello world");
    expect(body.alpha).toBe(0.7);
  });

  test("search throws NotFoundError for missing collection", async () => {
    const fetch = mockFetch([{ body: err(404, "Collection 'missing' not found") }]);
    const client = makeClient(fetch);
    await expect(client.search.search("missing", [0.1])).rejects.toThrow(NotFoundError);
  });
});

// ---------------------------------------------------------------------------
// ObservabilityResource
// ---------------------------------------------------------------------------

describe("VectorDBClient.observability", () => {
  test("health returns HealthStats", async () => {
    const fetch = mockFetch([
      {
        body: ok({
          status: "ok",
          total_vectors: 500,
          total_collections: 3,
          collections: [],
          uptime_seconds: 120,
        }),
      },
    ]);
    const client = makeClient(fetch);
    const h = await client.observability.health();
    expect(h.status).toBe("ok");
    expect(h.total_vectors).toBe(500);
    expect(h.total_collections).toBe(3);
    expect(h.uptime_seconds).toBe(120);
  });
});

// ---------------------------------------------------------------------------
// VectorDBClient
// ---------------------------------------------------------------------------

describe("VectorDBClient", () => {
  test("ping returns true on success", async () => {
    const fetch = mockFetch([
      { body: { message: "Welcome to Vector DB", backend: "sqlite", cache: "none" } },
    ]);
    const client = makeClient(fetch);
    expect(await client.ping()).toBe(true);
  });

  test("ping returns false on network error", async () => {
    const fetch = jest.fn().mockRejectedValue(new Error("ECONNREFUSED"));
    const client = makeClient(fetch as jest.Mock);
    expect(await client.ping()).toBe(false);
  });

  test("exposes all resource objects", () => {
    const client = new VectorDBClient({
      baseUrl: "http://localhost",
      apiKey: "k",
      fetch: jest.fn() as unknown as typeof globalThis.fetch,
    });
    expect(client.collections).toBeDefined();
    expect(client.vectors).toBeDefined();
    expect(client.search).toBeDefined();
    expect(client.observability).toBeDefined();
  });
});
