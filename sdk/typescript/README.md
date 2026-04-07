# vectordb-client

TypeScript/JavaScript SDK for the [VectorDB](https://github.com/lachu97/vector-db) REST API — fully typed, works in Node.js, Deno, and edge runtimes.

## Installation

```bash
npm install vectordb-client
# or
yarn add vectordb-client
# or
pnpm add vectordb-client
```

## Quick Start

```typescript
import { VectorDBClient } from "vectordb-client";

const client = new VectorDBClient({
  baseUrl: "http://localhost:8000",
  apiKey: "your-api-key",
});

// Create a collection
await client.collections.create("articles", 384, "cosine");

// Upsert a vector
await client.vectors.upsert("articles", "doc-1", [0.1, 0.2, 0.3], {
  title: "Hello World",
  author: "Alice",
});

// Search
const results = await client.search.search("articles", [0.1, 0.2, 0.3], { k: 5 });
for (const r of results.results) {
  console.log(r.external_id, r.score, r.metadata);
}
```

## Collections

```typescript
// Create
const col = await client.collections.create("articles", 384, "cosine");

// List
const cols = await client.collections.list();

// Get
const col = await client.collections.get("articles");
console.log(col.name, col.dim, col.vector_count);

// Delete
await client.collections.delete("articles");
```

## Vectors

```typescript
// Upsert
const result = await client.vectors.upsert("articles", "doc-1", [0.1, 0.2, 0.9], {
  title: "Hello",
  tags: ["ml", "nlp"],
});
console.log(result.status); // "inserted" or "updated"

// Bulk upsert
const bulk = await client.vectors.bulkUpsert("articles", [
  { external_id: "doc-1", vector: [0.1, 0.2, 0.3], metadata: { title: "A" } },
  { external_id: "doc-2", vector: [0.4, 0.5, 0.6], metadata: { title: "B" } },
]);

// Delete
await client.vectors.delete("articles", "doc-1");

// Batch delete
await client.vectors.deleteBatch("articles", ["doc-1", "doc-2", "doc-3"]);
```

## Search

```typescript
// KNN search
const results = await client.search.search("articles", queryVector, {
  k: 10,
  filters: { author: "Alice" },
});

// Recommendations (similar to a stored vector)
const recs = await client.search.recommend("articles", "doc-1", { k: 5 });

// Cosine similarity between two stored vectors
const score = await client.search.similarity("articles", "doc-1", "doc-2");

// Rerank candidates against a query vector
const reranked = await client.search.rerank("articles", queryVector, [
  "doc-1", "doc-2", "doc-3",
]);

// Hybrid search (vector + keyword)
const hybrid = await client.search.hybridSearch(
  "articles",
  "machine learning transformers",
  queryVector,
  { k: 10, alpha: 0.7 }
);
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
console.log(health.status);            // "ok"
console.log(health.total_vectors);
console.log(health.total_collections);
```

## Requirements

- Node.js 18+ (uses native `fetch`)
- For older Node.js, pass a custom fetch implementation

```typescript
import fetch from "node-fetch";

const client = new VectorDBClient({
  baseUrl: "http://localhost:8000",
  apiKey: "your-api-key",
  fetch: fetch as unknown as typeof globalThis.fetch,
});
```

## Documentation

Full docs at [lachu97.github.io/vector-db](https://lachu97.github.io/vector-db/)
