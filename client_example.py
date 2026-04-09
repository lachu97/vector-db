# client_example.py
"""Example: text-based upsert and search — no client-side embedding needed."""
import requests

BASE = "http://127.0.0.1:8000"
HEADERS = {"x-api-key": "test-key"}


def upsert_text(external_id, text, metadata=None):
    payload = {"external_id": external_id, "text": text, "metadata": metadata or {}}
    r = requests.post(f"{BASE}/v1/upsert", json=payload, headers=HEADERS)
    return r.json()


def search_text(qtext, k=5):
    payload = {"text": qtext, "k": k}
    r = requests.post(f"{BASE}/v1/search", json=payload, headers=HEADERS)
    return r.json()


if __name__ == "__main__":
    print("Upserting samples (server-side embedding)...")
    upsert_text("doc1", "How to cook pizza", {"topic": "cooking"})
    upsert_text("doc2", "PyTorch training tips", {"topic": "ml"})
    upsert_text("doc3", "Best pizza in New York", {"topic": "travel"})
    print("Searching for 'pizza tips' ...")
    print(search_text("pizza tips", k=3))
