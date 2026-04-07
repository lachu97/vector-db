import requests
import numpy as np
import json

BASE = "http://127.0.0.1:8000"
API_KEY = "test-key"
HEADERS = {"X-API-Key": API_KEY}

def pretty(label, resp):
    print(f"\n--- {label} ---")
    try:
        print(json.dumps(resp.json(), indent=2))
    except Exception:
        print("Non-JSON response:")
        print(resp.text)


# --------------------------
# Collection Management
# --------------------------

pretty("Create collection 'articles'", requests.post(f"{BASE}/v1/collections", json={
    "name": "articles",
    "dim": 384,
    "distance_metric": "cosine",
}, headers=HEADERS))

pretty("List collections", requests.get(f"{BASE}/v1/collections", headers=HEADERS))

# --------------------------
# Vector Operations (collection-scoped)
# --------------------------

pretty("Health (before)", requests.get(f"{BASE}/v1/health", headers=HEADERS))

# Upsert
vec = np.random.rand(384).tolist()
pretty("Upsert doc1", requests.post(f"{BASE}/v1/collections/articles/upsert", json={
    "external_id": "doc1",
    "vector": vec,
    "metadata": {"type": "article", "lang": "en"},
    "content": "latest news about artificial intelligence",
}, headers=HEADERS))

# Bulk upsert
bulk = {
    "items": [
        {"external_id": "doc2", "vector": np.random.rand(384).tolist(),
         "metadata": {"type": "blog"}, "content": "machine learning tutorial"},
        {"external_id": "doc3", "vector": np.random.rand(384).tolist(),
         "metadata": {"type": "news"}, "content": "quantum computing breakthrough"},
    ]
}
pretty("Bulk Upsert", requests.post(f"{BASE}/v1/collections/articles/bulk_upsert", json=bulk, headers=HEADERS))

# Search
query = np.random.rand(384).tolist()
pretty("Search", requests.post(f"{BASE}/v1/collections/articles/search", json={
    "vector": query, "k": 2,
}, headers=HEADERS))

# Search with pagination
pretty("Search offset=1", requests.post(f"{BASE}/v1/collections/articles/search", json={
    "vector": query, "k": 1, "offset": 1,
}, headers=HEADERS))

# --------------------------
# Productization Features
# --------------------------

pretty("Recommend for doc2", requests.post(
    f"{BASE}/v1/collections/articles/recommend/doc2?k=2", headers=HEADERS))

pretty("Similarity doc2 vs doc3", requests.post(
    f"{BASE}/v1/collections/articles/similarity?id1=doc2&id2=doc3", headers=HEADERS))

# Rerank
pretty("Rerank", requests.post(f"{BASE}/v1/collections/articles/rerank", json={
    "vector": query,
    "candidates": ["doc1", "doc2", "doc3"],
}, headers=HEADERS))

# Hybrid search
pretty("Hybrid Search", requests.post(f"{BASE}/v1/collections/articles/hybrid_search", json={
    "query_text": "artificial intelligence",
    "vector": np.random.rand(384).tolist(),
    "k": 2,
    "alpha": 0.5,
}, headers=HEADERS))

# Batch delete
pretty("Batch Delete", requests.post(f"{BASE}/v1/collections/articles/delete_batch", json={
    "external_ids": ["doc1", "nonexistent"],
}, headers=HEADERS))

# Delete single
pretty("Delete doc2", requests.delete(f"{BASE}/v1/collections/articles/delete/doc2", headers=HEADERS))

# Health after operations
pretty("Health (after)", requests.get(f"{BASE}/v1/health", headers=HEADERS))

# Get collection info
pretty("Get collection", requests.get(f"{BASE}/v1/collections/articles", headers=HEADERS))
