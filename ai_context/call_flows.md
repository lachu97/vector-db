# Call Flows

## Query (POST /v1/query)

```
request
  -> auth (require_readonly)
  -> router validates query length <= 1000, collection access (user_id scoped)
  -> query_service.run_query()
      -> await embed_text_cached_async(query)
          -> semaphore acquire
          -> run_in_executor(embed_text_cached)
              -> normalize_query (lower, strip, punct, collapse)
              -> Redis get (msgpack, sha256 key)
              -> LRU cache get
              -> provider.embed_text() [if cache miss]
              -> Redis set (backfill)
      -> await backend.search(collection, vector, k, offset, filters)
      -> format results [{text, score, metadata, external_id}]
      -> logger.debug(embedding_ms, search_ms, total_ms)
  -> success_response
```

## Search (POST /v1/collections/{name}/search)

```
request {vector OR text, k, offset, filters}
  -> auth (require_readonly)
  -> check_collection_access(user_id)
  -> if text and no vector: await embed_text_cached_async(text)
  -> await backend.search(collection, vector, k, offset, filters)
  -> await backend.count_vectors(collection, filters)
  -> success_response {results, total_count, k, offset}
```

## Upsert (POST /v1/collections/{name}/upsert)

```
request {external_id, vector OR text, metadata?, content?}
  -> auth (require_readwrite)
  -> check_collection_access(user_id)
  -> if text and no vector:
      -> vector = embed_text(text)  [sync, uncached]
      -> content = text  [if content not explicit]
  -> await backend.upsert(collection, external_id, vector, metadata, content)
  -> success_response {external_id, status}
```

## Bulk Upsert (POST /v1/collections/{name}/bulk_upsert)

```
request {items: [{external_id, vector OR text, ...}]}
  -> auth (require_readwrite)
  -> check_collection_access(user_id)
  -> separate items: has_vector vs text_only
  -> if text_only items: embeddings = embed_batch(texts)  [sync, uncached, batched]
  -> merge vectors back into items
  -> await backend.bulk_upsert(collection, items)
  -> success_response {results}
```

## Document Upload (POST /v1/documents/upload)

```
multipart {collection_name, file (.txt)}
  -> auth (require_readwrite)
  -> validate file ext, collection access
  -> document_service.process_document()
      -> chunk_text(file_text, 500, 50)
      -> embed_batch(chunks)  [sync, uncached]
      -> backend.bulk_upsert(collection, items with doc_id metadata)
  -> success_response {document_id, chunks_created}
```

## Hybrid Search (POST /v1/collections/{name}/hybrid_search)

```
request {query_text, vector? (optional), k, alpha, filters}
  -> auth (require_readonly)
  -> if no vector: vector = await embed_text_cached_async(query_text)
  -> await backend.hybrid_search(collection, query_text, vector, k, offset, alpha, filters)
  -> success_response
```

## Rerank (POST /v1/collections/{name}/rerank)

```
request {vector OR text, candidates}
  -> auth (require_readonly)
  -> if text and no vector: vector = await embed_text_cached_async(text)
  -> await backend.rerank(collection, vector, candidates)
  -> success_response
```

## Embedding Function Selection

| Context | Function | Cached | Async |
|---------|----------|:------:|:-----:|
| Insert (single) | `embed_text()` | No | No |
| Insert (batch) | `embed_batch()` | No | No |
| Query / Search | `embed_text_cached_async()` | Yes (Redis+LRU) | Yes |
