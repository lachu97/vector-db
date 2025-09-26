import requests
import numpy as np
import json

BASE = "http://127.0.0.1:8000"
API_KEY = "test-key"  # replace with the key you set
HEADERS = {"X-API-Key": API_KEY}

def pretty(label, resp):
    print(f"\n--- {label} ---")
    try:
        print(json.dumps(resp.json(), indent=2))
    except Exception:
        print("Non-JSON response:")
        print(resp.text)


# --------------------------
# Core API Tests
# --------------------------

pretty("Health (before)", requests.get(f"{BASE}/v1/health", headers=HEADERS))

# Upsert one vector
vec = np.random.rand(384).tolist()
resp = requests.post(f"{BASE}/v1/upsert", json={
    "external_id": "doc1",
    "vector": vec,
    "metadata": {"type": "article", "lang": "en"}
}, headers=HEADERS)
pretty("Upsert doc1", resp)

# Bulk upsert
bulk = {
    "items": [
        {
            "external_id": "doc2",
            "vector": np.random.rand(384).tolist(),
            "metadata": {"type": "blog"}
        },
        {
            "external_id": "doc3",
            "vector": np.random.rand(384).tolist(),
            "metadata": {"type": "news"}
        }
    ]
}
pretty("Bulk Upsert", requests.post(f"{BASE}/v1/bulk_upsert", json=bulk, headers=HEADERS))

# Search
query = np.random.rand(384).tolist()
pretty("Search", requests.post(f"{BASE}/v1/search", json={"vector": query, "k": 2}, headers=HEADERS))

# Delete
pretty("Delete doc1", requests.delete(f"{BASE}/v1/delete/doc1", headers=HEADERS))

# Health check after delete
pretty("Health (after delete)", requests.get(f"{BASE}/v1/health", headers=HEADERS))


# --------------------------
# Productization Layer Tests
# --------------------------

pretty("Recommend for doc2", requests.post(
    f"{BASE}/v1/recommend/doc2?k=2",
    headers=HEADERS
))

# Similarity test (doc2 vs doc3)
pretty("Similarity doc2 vs doc3", requests.post(
    f"{BASE}/v1/similarity?id1=doc2&id2=doc3",
    headers=HEADERS
))

# Rerank test
query = np.random.rand(384).tolist()
pretty("Rerank", requests.post(f"{BASE}/v1/rerank", json={
    "vector": query,
    "candidates": ["doc2", "doc3"]
}, headers=HEADERS))

# Hybrid search test
pretty("Hybrid Search", requests.post(f"{BASE}/v1/hybrid_search", json={
    "query_text": "latest tech news",
    "vector": np.random.rand(384).tolist(),
    "k": 2
}, headers=HEADERS))
