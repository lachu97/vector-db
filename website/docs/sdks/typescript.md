---
id: typescript
title: TypeScript SDK
sidebar_label: TypeScript SDK
---

## Installation

```bash
npm install vectordb-client
```

Or with yarn/pnpm:

```bash
yarn add vectordb-client
pnpm add vectordb-client
```

## Initializing the Client

```typescript
import { VectorDBClient } from "vectordb-client";

const client = new VectorDBClient({
  baseUrl: "http://localhost:8000",
  apiKey: "your-api-key",
});
```

The SDK uses the native `fetch` API (available in Node.js 18+, browsers, Deno, and edge runtimes). For older Node.js, pass a custom fetch:

```typescript
import fetch from "node-fetch";

const client = new VectorDBClient({
  baseUrl: "http://localhost:8000",
  apiKey: "your-api-key",
  fetch: fetch as unknown as typeof globalThis.fetch,
});
```

---

## Auth (Registration & Login)

```typescript
// Register a new user (no apiKey needed for this call)
const result = await client.auth.register("user@example.com", "securepassword");
const apiKey = result.api_key.key; // Use this key for subsequent calls

// Login
const loginResult = await client.auth.login("user@example.com", "securepassword");
```

---

## Collections

```typescript
// Create (with optional description)
const col = await client.collections.create("articles", 384, "cosine", "Blog article embeddings");

// List
const cols = await client.collections.list();
cols.forEach((c) => console.log(c.name, c.dim, c.vector_count, c.description));

// Get
const col = await client.collections.get("articles");

// Update description
const updated = await client.collections.update("articles", "New description");

// Clear description
await client.collections.update("articles", null);

// Export all vectors
const exported = await client.collections.export("articles", 5000);
console.log(exported.count); // number of vectors
exported.vectors.forEach((v) => console.log(v.external_id, v.vector.length));

// Delete
await client.collections.delete("articles");
```

## Vectors

```typescript
// Upsert with a raw vector
const result = await client.vectors.upsert(
  "articles",
  "doc-1",
  [0.1, 0.2, 0.9],
  { title: "Hello", tags: ["ml", "nlp"] }
);
console.log(result.status); // "inserted" or "updated"

// Upsert with text — the server embeds it for you
const textResult = await client.vectors.upsert(
  "articles",
  "doc-2",
  undefined, // no vector
  { title: "Intro" },
  undefined, // no namespace
  { text: "An intro to vector databases" }
);

// Opt into timing metrics (embedding_ms, storage_ms, total_ms)
const timed = await client.vectors.upsert(
  "articles",
  "doc-3",
  undefined,
  undefined,
  undefined,
  { text: "Another article", includeTiming: true }
);
console.log(timed.timing_ms?.embedding_ms, timed.timing_ms?.total_ms);

// Bulk upsert — mix vectors and text in the same batch
const items = [
  { external_id: "doc-a", vector: vectors[0], metadata: { i: 0 } },
  { external_id: "doc-b", text: "Second article body" },
];
const bulk = await client.vectors.bulkUpsert("articles", items, {
  includeTiming: true,
});
console.log(bulk.timing_ms?.embedding_ms, bulk.timing_ms?.storage_ms);

// Delete
await client.vectors.delete("articles", "doc-1");

// Batch delete
const deleted = await client.vectors.deleteBatch("articles", ["doc-1", "doc-2"]);
console.log(deleted.deleted_count);
```

## Search

```typescript
// KNN search with a raw vector (returns total_count for pagination)
const results = await client.search.search("articles", queryVector, {
  k: 10,
  filters: { tags: "ml" },
});
console.log(`Showing ${results.results.length} of ${results.total_count} total`);
for (const r of results.results) {
  console.log(r.external_id, r.score, r.metadata);
}

// Search with plain text — the server embeds the query for you (cached)
const textResults = await client.search.search("articles", undefined, {
  text: "machine learning tutorials",
  k: 10,
});

// Opt into timing metrics (embedding_ms, search_ms, total_ms)
const timedResults = await client.search.search("articles", undefined, {
  text: "deep learning",
  k: 10,
  includeTiming: true,
});
console.log(timedResults.timing_ms?.embedding_ms, timedResults.timing_ms?.search_ms);

// Recommendations
const recs = await client.search.recommend("articles", "doc-1", { k: 5 });

// Similarity between two stored vectors
const score = await client.search.similarity("articles", "doc-1", "doc-2");

// Rerank with a vector...
const reranked = await client.search.rerank("articles", queryVector, [
  "doc-1",
  "doc-2",
  "doc-3",
]);

// ...or rerank with text
const textReranked = await client.search.rerank(
  "articles",
  undefined,
  ["doc-1", "doc-2", "doc-3"],
  { text: "machine learning best practices", includeTiming: true }
);

// Hybrid search — vector is now optional; backend auto-embeds query_text
const hybrid = await client.search.hybridSearch(
  "articles",
  "machine learning transformers",
  undefined, // no vector needed
  { k: 10, alpha: 0.7, includeTiming: true }
);
```

## API Keys

Manage API keys programmatically (requires admin role):

```typescript
// Create a key with optional expiry
const key = await client.keys.create("production-app", "readwrite", 90);
console.log(key.key); // only shown once — save it!

// List all keys
const keys = await client.keys.list();
keys.forEach((k) => console.log(k.id, k.name, k.role, k.is_active));

// Get a single key
const fetched = await client.keys.get(2);

// Update name/role
await client.keys.update(2, { name: "renamed-key", role: "readonly" });

// Revoke / Restore
await client.keys.revoke(2);
await client.keys.restore(2);

// Rotate (regenerate key value)
const rotated = await client.keys.rotate(2);
console.log(rotated.key); // new key value — shown once

// Usage stats for a key
const usage = await client.keys.getUsage(2);
console.log(usage.total_requests, usage.last_24h, usage.by_endpoint);

// Usage summary across all keys
const summary = await client.keys.getUsageSummary();
console.log(summary.overall.total_requests);

// Delete
await client.keys.delete(2);
```

## RAG (Document Upload & Query)

```typescript
// Upload a text document to a collection
const upload = await client.documents.upload("articles", fileBlob, "document.txt");
console.log(upload.document_id);   // UUID of the uploaded document
console.log(upload.chunks_created); // number of chunks generated

// Upload with timing metrics
const timedUpload = await client.documents.upload(
  "articles",
  fileBlob,
  "document.txt",
  { includeTiming: true }
);
console.log(timedUpload.timing_ms?.embedding_ms, timedUpload.timing_ms?.total_ms);

// Query a collection with natural language
const queryResults = await client.query.query(
  "How does vector indexing work?",
  "articles",
  { top_k: 5, filters: { source: "docs" }, includeTiming: true }
);
console.log(queryResults.timing_ms?.embedding_ms, queryResults.timing_ms?.search_ms);
for (const r of queryResults.results) {
  console.log(r.text, r.score, r.metadata, r.external_id);
}
```

## Error Handling

```typescript
import {
  VectorDBError,
  NotFoundError,
  AlreadyExistsError,
  DimensionMismatchError,
  AuthenticationError,
  RateLimitError,
} from "vectordb-client";

try {
  await client.collections.create("my-col", 384);
} catch (err) {
  if (err instanceof AlreadyExistsError) {
    console.log("Collection already exists");
  } else if (err instanceof DimensionMismatchError) {
    console.log("Wrong vector dimension");
  } else if (err instanceof AuthenticationError) {
    console.log("Invalid API key");
  } else if (err instanceof VectorDBError) {
    console.log(`Error ${err.statusCode}: ${err.message}`);
  }
}
```

## Health Check

```typescript
const health = await client.observability.health();
console.log(health.status);           // "ok"
console.log(health.total_vectors);
console.log(health.total_collections);
```

## Full TypeScript Types

All methods are fully typed. Key types:

```typescript
import type {
  Collection,           // { name, dim, distance_metric, vector_count, description? }
  VectorResult,         // { external_id, score, metadata }
  SearchResult,         // { results, collection, k, total_count, offset, timing_ms? }
  UpsertResult,         // { external_id, status, timing_ms? }
  BulkUpsertResult,     // { results, timing_ms? }
  TimingInfo,           // { total_ms, embedding_ms?, storage_ms?, search_ms? }
  ExportResult,         // { collection, dim, distance_metric, count, vectors }
  DocumentUploadResult, // { document_id, chunks_created, timing_ms? }
  QueryResult,          // { query, collection, results, timing_ms? }
  ApiKey,               // { id, name, role, is_active, created_at, expires_at?, key? }
  KeyUsageStats,        // { total_requests, last_24h, last_7d, last_30d, by_endpoint }
  UsageSummary,         // { overall, by_key }
  HealthStats,          // { status, total_vectors, total_collections, collections }
  SearchOptions,        // { k?, offset?, filters?, includeTiming? }
} from "vectordb-client";
```
