import { HttpClient, raiseForResponse, unwrap } from "../http.js";
import {
  NotFoundError,
  AlreadyExistsError,
  DimensionMismatchError,
  AuthenticationError,
  RateLimitError,
  VectorDBError,
} from "../errors.js";
import type { ApiResponse } from "../types.js";

// ---------------------------------------------------------------------------
// raiseForResponse
// ---------------------------------------------------------------------------

describe("raiseForResponse", () => {
  test("404 → NotFoundError", () => {
    expect(() => raiseForResponse(404, "not found")).toThrow(NotFoundError);
  });

  test("409 → AlreadyExistsError", () => {
    expect(() => raiseForResponse(409, "exists")).toThrow(AlreadyExistsError);
  });

  test("400 + dimension → DimensionMismatchError", () => {
    expect(() => raiseForResponse(400, "dimension mismatch: expected 384, got 128")).toThrow(
      DimensionMismatchError
    );
  });

  test("401 → AuthenticationError", () => {
    expect(() => raiseForResponse(401, "unauthorized")).toThrow(AuthenticationError);
  });

  test("403 → AuthenticationError", () => {
    expect(() => raiseForResponse(403, "forbidden")).toThrow(AuthenticationError);
  });

  test("429 → RateLimitError", () => {
    expect(() => raiseForResponse(429, "too many requests")).toThrow(RateLimitError);
  });

  test("unknown code → VectorDBError", () => {
    expect(() => raiseForResponse(500, "internal error")).toThrow(VectorDBError);
  });
});

// ---------------------------------------------------------------------------
// unwrap
// ---------------------------------------------------------------------------

describe("unwrap", () => {
  test("returns data on success", () => {
    const body: ApiResponse<{ id: string }> = {
      status: "success",
      data: { id: "v1" },
      error: null,
    };
    expect(unwrap(body)).toEqual({ id: "v1" });
  });

  test("throws NotFoundError on error body with code 404", () => {
    const body: ApiResponse<null> = {
      status: "error",
      data: null,
      error: { code: 404, message: "not found" },
    };
    expect(() => unwrap(body)).toThrow(NotFoundError);
  });

  test("throws AlreadyExistsError on 409", () => {
    const body: ApiResponse<null> = {
      status: "error",
      data: null,
      error: { code: 409, message: "collection already exists" },
    };
    expect(() => unwrap(body)).toThrow(AlreadyExistsError);
  });
});

// ---------------------------------------------------------------------------
// HttpClient
// ---------------------------------------------------------------------------

function makeEnvelope<T>(data: T): ApiResponse<T> {
  return { status: "success", data, error: null };
}

function makeErrorEnvelope(code: number, message: string): ApiResponse<null> {
  return { status: "error", data: null, error: { code, message } };
}

function mockFetch(body: unknown, status = 200): jest.Mock {
  return jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
}

describe("HttpClient", () => {
  test("GET request returns unwrapped data", async () => {
    const fetchMock = mockFetch(makeEnvelope({ name: "col1", dim: 128 }));
    const client = new HttpClient("http://localhost:8000", "key", fetchMock);

    const result = await client.request("GET", "/v1/collections/col1");
    expect(result).toEqual({ name: "col1", dim: 128 });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/v1/collections/col1",
      expect.objectContaining({ method: "GET" })
    );
  });

  test("POST request sends JSON body", async () => {
    const fetchMock = mockFetch(makeEnvelope({ external_id: "v1", status: "inserted" }));
    const client = new HttpClient("http://localhost:8000", "key", fetchMock);

    const result = await client.request("POST", "/v1/collections/my-col/upsert", {
      body: { external_id: "v1", vector: [0.1, 0.2] },
    });

    expect(result).toEqual({ external_id: "v1", status: "inserted" });
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ external_id: "v1", vector: [0.1, 0.2] });
  });

  test("query params are appended to URL", async () => {
    const fetchMock = mockFetch(makeEnvelope({ score: 0.95 }));
    const client = new HttpClient("http://localhost:8000", "key", fetchMock);

    await client.request("POST", "/v1/collections/col/similarity", {
      params: { id1: "v1", id2: "v2" },
      body: {},
    });

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain("id1=v1");
    expect(url).toContain("id2=v2");
  });

  test("body error envelope throws NotFoundError", async () => {
    const fetchMock = mockFetch(makeErrorEnvelope(404, "collection not found"));
    const client = new HttpClient("http://localhost:8000", "key", fetchMock);

    await expect(client.request("GET", "/v1/collections/missing")).rejects.toThrow(
      NotFoundError
    );
  });

  test("HTTP 401 throws AuthenticationError", async () => {
    const fetchMock = mockFetch({ status: "error", data: null, error: { code: 401, message: "unauthorized" } }, 401);
    const client = new HttpClient("http://localhost:8000", "key", fetchMock);

    await expect(client.request("GET", "/v1/collections")).rejects.toThrow(
      AuthenticationError
    );
  });

  test("x-api-key header is sent", async () => {
    const fetchMock = mockFetch(makeEnvelope({}));
    const client = new HttpClient("http://localhost:8000", "my-secret", fetchMock);

    await client.request("GET", "/");
    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>)["x-api-key"]).toBe("my-secret");
  });

  test("trailing slash stripped from baseUrl", async () => {
    const fetchMock = mockFetch(makeEnvelope({}));
    const client = new HttpClient("http://localhost:8000/", "key", fetchMock);

    await client.request("GET", "/v1/collections");
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/v1/collections");
  });
});
