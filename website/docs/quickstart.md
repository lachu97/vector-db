---
id: quickstart
title: Quickstart
sidebar_label: Quickstart
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## Option 1: Docker (recommended)

The fastest way to get started.

```bash
git clone https://github.com/lachu97/vector-db
cd vector-db
docker compose up --build
```

The server starts on `http://localhost:8000`. The default API key is `test-key`.

:::note
Change `API_KEY` in `docker-compose.yml` before deploying to production.
:::

## Option 2: Python (local)

```bash
git clone https://github.com/lachu97/vector-db
cd vector-db
pip install -r requirements.txt
uvicorn main:app --reload
```

---

## Your First Vectors

### 1. Create a collection

A collection holds vectors of a fixed dimension with a chosen distance metric.

<Tabs>
<TabItem value="curl" label="cURL">

```bash
curl -X POST http://localhost:8000/v1/collections \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"name": "docs", "dim": 3, "distance_metric": "cosine"}'
```

</TabItem>
<TabItem value="python" label="Python SDK">

```python
from vectordb_client import VectorDBClient

client = VectorDBClient(base_url="http://localhost:8000", api_key="test-key")
col = client.collections.create("docs", dim=3, distance_metric="cosine")
print(col.name, col.dim)
```

</TabItem>
<TabItem value="typescript" label="TypeScript SDK">

```typescript
import { VectorDBClient } from "vectordb-client";

const client = new VectorDBClient({
  baseUrl: "http://localhost:8000",
  apiKey: "test-key",
});
const col = await client.collections.create("docs", 3, "cosine");
console.log(col.name, col.dim);
```

</TabItem>
<TabItem value="cli" label="CLI">

```bash
export VECTORDB_API_KEY=test-key
vdb collections create docs --dim 3 --metric cosine
```

</TabItem>
</Tabs>

### 2. Upsert vectors

Insert vectors with optional metadata.

<Tabs>
<TabItem value="curl" label="cURL">

```bash
curl -X POST http://localhost:8000/v1/collections/docs/upsert \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "external_id": "doc-1",
    "vector": [0.1, 0.8, 0.3],
    "metadata": {"title": "Getting Started", "category": "tutorial"}
  }'
```

</TabItem>
<TabItem value="python" label="Python SDK">

```python
result = client.vectors.upsert(
    "docs",
    external_id="doc-1",
    vector=[0.1, 0.8, 0.3],
    metadata={"title": "Getting Started", "category": "tutorial"},
)
print(result.status)  # "inserted"
```

</TabItem>
<TabItem value="typescript" label="TypeScript SDK">

```typescript
const result = await client.vectors.upsert(
  "docs",
  "doc-1",
  [0.1, 0.8, 0.3],
  { title: "Getting Started", category: "tutorial" }
);
console.log(result.status); // "inserted"
```

</TabItem>
<TabItem value="cli" label="CLI">

```bash
vdb vectors upsert docs doc-1 '[0.1, 0.8, 0.3]' \
  --metadata '{"title": "Getting Started"}'
```

</TabItem>
</Tabs>

### 3. Search

Find the most similar vectors to a query.

<Tabs>
<TabItem value="curl" label="cURL">

```bash
curl -X POST http://localhost:8000/v1/collections/docs/search \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"vector": [0.1, 0.8, 0.2], "k": 5}'
```

</TabItem>
<TabItem value="python" label="Python SDK">

```python
results = client.search.search("docs", vector=[0.1, 0.8, 0.2], k=5)
for r in results:
    print(r.external_id, r.score, r.metadata)
```

</TabItem>
<TabItem value="typescript" label="TypeScript SDK">

```typescript
const results = await client.search.search("docs", [0.1, 0.8, 0.2], { k: 5 });
for (const r of results.results) {
  console.log(r.external_id, r.score, r.metadata);
}
```

</TabItem>
<TabItem value="cli" label="CLI">

```bash
vdb search docs '[0.1, 0.8, 0.2]' --k 5
```

</TabItem>
</Tabs>

---

## Explore Further

- [Collections](/concepts/collections) — Learn about namespacing, dimensions, and distance metrics
- [Hybrid Search](/concepts/hybrid-search) — Combine vector and keyword search with RRF
- [Python SDK](/sdks/python) — Full Python SDK reference with examples
- [Configuration](/deployment/configuration) — All environment variables and settings
