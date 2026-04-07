# vectordb-client

Python SDK for the [VectorDB](https://github.com/lachu97/vector-db) REST API — sync and async clients, CLI tool included.

## Installation

```bash
pip install vdb-python
```

## Quick Start

```python
from vectordb_client import VectorDBClient

client = VectorDBClient(base_url="http://localhost:8000", api_key="your-key")

# Create a collection
client.collections.create("articles", dim=384, distance_metric="cosine")

# Upsert a vector
client.vectors.upsert("articles", external_id="doc-1", vector=[0.1, 0.2, ...], metadata={"title": "Hello"})

# Search
results = client.search.search("articles", vector=[0.1, 0.2, ...], k=5)
for r in results:
    print(r.external_id, r.score)
```

## Async Client

```python
from vectordb_client import AsyncVectorDBClient

async with AsyncVectorDBClient(base_url="http://localhost:8000", api_key="your-key") as client:
    await client.collections.create("articles", dim=384)
    results = await client.search.search("articles", vector=query, k=5)
```

## CLI

```bash
export VECTORDB_API_KEY=your-key
vdb collections list
vdb search articles '[0.1, 0.2, 0.3]' --k 5
vdb -o json collections get articles
```

## Documentation

Full docs at [lachu97.github.io/vector-db](https://lachu97.github.io/vector-db/)
