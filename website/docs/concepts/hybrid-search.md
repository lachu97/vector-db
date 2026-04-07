---
id: hybrid-search
title: Hybrid Search
sidebar_label: Hybrid Search
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## What is Hybrid Search?

Hybrid search combines **vector similarity** (semantic) and **keyword matching** (lexical) into a single ranked result list. This overcomes the weaknesses of each approach alone:

- **Vector search** finds semantically similar content but may miss exact keyword matches
- **Keyword search** finds exact terms but misses paraphrases and synonyms

Hybrid search gives you both.

## How it Works

VectorDB uses **Reciprocal Rank Fusion (RRF)** to merge the two result lists.

1. Run a vector search on your query embedding → ranked list A
2. Run a word-level text match on your query string → ranked list B
3. For each document, compute: `score = α × vector_rank_score + (1-α) × text_rank_score`
4. Return the merged list sorted by combined score

The `alpha` parameter controls the blend:
- `alpha=1.0` → pure vector search
- `alpha=0.0` → pure keyword search
- `alpha=0.5` → equal weight (default)

## Usage

<Tabs>
<TabItem value="python" label="Python SDK">

```python
from sentence_transformers import SentenceTransformer
from vectordb_client import VectorDBClient

model = SentenceTransformer("all-MiniLM-L6-v2")
client = VectorDBClient(base_url="http://localhost:8000", api_key="your-key")

query = "how do neural networks learn?"
vector = model.encode(query).tolist()

results = client.search.hybrid_search(
    collection="articles",
    query_text=query,
    vector=vector,
    k=10,
    alpha=0.6,
)
for r in results:
    print(r.external_id, r.score)
```

</TabItem>
<TabItem value="typescript" label="TypeScript SDK">

```typescript
import { VectorDBClient } from "vectordb-client";

const client = new VectorDBClient({ baseUrl: "http://localhost:8000", apiKey: "your-key" });

const results = await client.search.hybridSearch(
  "articles",
  "how do neural networks learn?",
  queryVector,
  { k: 10, alpha: 0.6 }
);
```

</TabItem>
<TabItem value="cli" label="CLI">

```bash
vdb hybrid-search articles "how do neural networks learn?" '[0.1, ...]' \
  --k 10 --alpha 0.6
```

</TabItem>
<TabItem value="curl" label="cURL">

```bash
curl -X POST http://localhost:8000/v1/collections/articles/hybrid_search \
  -H "x-api-key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query_text": "how do neural networks learn?",
    "vector": [0.1, 0.2, ...],
    "k": 10,
    "alpha": 0.6
  }'
```

</TabItem>
</Tabs>

## When to Use Hybrid Search

| Scenario | Recommendation |
|----------|----------------|
| General semantic search | Pure vector (`alpha=1.0`) |
| Code search with specific terms | High keyword weight (`alpha=0.3`) |
| Product search with brand names | Hybrid (`alpha=0.5`) |
| Legal / medical documents with exact terminology | High keyword weight (`alpha=0.2`) |
| General RAG (retrieval-augmented generation) | Hybrid (`alpha=0.6-0.8`) |

## Text Matching

VectorDB's keyword search splits the query and document content on whitespace and punctuation and counts word-level overlaps. For hybrid search to work on metadata, store searchable text in vector metadata fields.

:::note
The keyword component works on the vector's stored metadata text. Make sure to include the document text or relevant keywords in the metadata when upserting.
:::
