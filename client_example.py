# client_example.py
import requests
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')  # 384-dim

BASE = "http://127.0.0.1:8000"

def upsert_text(external_id, text, metadata=None):
    vec = model.encode(text).tolist()
    payload = {"external_id": external_id, "vector": vec, "metadata": metadata or {}}
    r = requests.post(f"{BASE}/upsert", json=payload)
    return r.json()

def search_text(qtext, k=5):
    vec = model.encode(qtext).tolist()
    payload = {"vector": vec, "k": k}
    r = requests.post(f"{BASE}/search", json=payload)
    return r.json()

if __name__ == "__main__":
    print("Upserting samples...")
    upsert_text("doc1", "How to cook pizza", {"topic": "cooking"})
    upsert_text("doc2", "PyTorch training tips", {"topic": "ml"})
    upsert_text("doc3", "Best pizza in New York", {"topic": "travel"})
    print("Searching for 'pizza tips' ...")
    print(search_text("pizza tips", k=3))
