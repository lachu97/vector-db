import requests
import numpy as np
import json

BASE = "http://127.0.0.1:8000"

def pretty(label, resp):
    print(f"\n--- {label} ---")
    try:
        print(json.dumps(resp.json(), indent=2))
    except Exception:
        print("Non-JSON response:")
        print(resp.text)

# 1. Health check
pretty("Health (before)", requests.get(f"{BASE}/health"))

# 2. Upsert one vector
vec = np.random.rand(384).tolist()
resp = requests.post(f"{BASE}/upsert", json={
    "external_id": "doc1",
    "vector": vec,
    "metadata": {"type": "article", "lang": "en"}
})
pretty("Upsert doc1", resp)

# 3. Bulk upsert
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
pretty("Bulk Upsert", requests.post(f"{BASE}/bulk_upsert", json=bulk))

# 4. Search
query = np.random.rand(384).tolist()
pretty("Search", requests.post(f"{BASE}/search", json={"vector": query, "k": 2}))

# 5. Delete
pretty("Delete doc1", requests.delete(f"{BASE}/delete/doc1"))

# 6. Health check after delete
pretty("Health (after delete)", requests.get(f"{BASE}/health"))
