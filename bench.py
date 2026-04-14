"""Quick latency benchmark for SQLite backend (local dev).
Run: python bench.py
"""
import os
import time
import tempfile
import statistics
import numpy as np

_tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdir}/bench.db"
os.environ["INDEX_PATH"] = os.path.join(_tmpdir, "bench_index.bin")
os.environ["API_KEY"] = "test-key"
os.environ["EMBEDDING_PROVIDER"] = "dummy"
os.environ["VECTOR_DIM"] = "384"
os.environ["MAX_ELEMENTS"] = "50000"

from fastapi.testclient import TestClient  # noqa: E402
from vectordb.app import app  # noqa: E402

HEADERS = {"x-api-key": "test-key"}
DIM = 384


def random_vec():
    return np.random.rand(DIM).tolist()


def bench(label, fn, n=200):
    """Run fn() n times and report percentiles."""
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    p50 = statistics.median(times)
    p95 = times[int(n * 0.95)]
    p99 = times[int(n * 0.99)]
    avg = statistics.mean(times)
    print(f"  {label:30s}  avg={avg:6.2f}ms  p50={p50:6.2f}ms  p95={p95:6.2f}ms  p99={p99:6.2f}ms  (n={n})")
    return times


def main():
    with TestClient(app) as client:
        # Setup: create collection
        client.post("/v1/collections", json={
            "name": "bench", "dim": DIM, "distance_metric": "cosine"
        }, headers=HEADERS)

        # Phase 1: seed data
        print("\n=== Seeding data ===")
        seed_sizes = [100, 1000, 5000]
        for target in seed_sizes:
            current = client.get("/v1/collections/bench", headers=HEADERS).json()
            current_count = current.get("data", {}).get("vector_count", 0)
            remaining = target - current_count
            if remaining <= 0:
                continue

            t0 = time.perf_counter()
            batch_size = 100
            for i in range(0, remaining, batch_size):
                batch = [
                    {"external_id": f"vec-{current_count + i + j}", "vector": random_vec(), "metadata": {"i": i + j}}
                    for j in range(min(batch_size, remaining - i))
                ]
                client.post("/v1/collections/bench/bulk_upsert", json={"vectors": batch}, headers=HEADERS)
            elapsed = time.perf_counter() - t0
            print(f"  Seeded to {target} vectors in {elapsed:.2f}s")

            # Benchmarks at this scale
            print(f"\n=== Benchmarks at {target} vectors ===")

            # Single upsert
            counter = [target]
            def do_upsert():
                counter[0] += 1
                client.post("/v1/collections/bench/upsert", json={
                    "external_id": f"bench-{counter[0]}", "vector": random_vec(), "metadata": {"t": "bench"}
                }, headers=HEADERS)
            bench("upsert (single)", do_upsert, n=100)

            # Search
            def do_search():
                client.post("/v1/collections/bench/search", json={
                    "vector": random_vec(), "top_k": 10
                }, headers=HEADERS)
            bench("search (top_k=10)", do_search, n=200)

            # Search with filter
            def do_search_filter():
                client.post("/v1/collections/bench/search", json={
                    "vector": random_vec(), "top_k": 10, "filters": {"i": 42}
                }, headers=HEADERS)
            bench("search (top_k=10 + filter)", do_search_filter, n=200)

            # Recommend
            def do_recommend():
                client.post("/v1/collections/bench/recommend/vec-0", json={
                    "top_k": 10
                }, headers=HEADERS)
            bench("recommend (top_k=10)", do_recommend, n=100)

            # Bulk upsert (10 items)
            bulk_counter = [100000]
            def do_bulk():
                bulk_counter[0] += 10
                batch = [
                    {"external_id": f"bulk-{bulk_counter[0]+j}", "vector": random_vec(), "metadata": {"b": True}}
                    for j in range(10)
                ]
                client.post("/v1/collections/bench/bulk_upsert", json={"vectors": batch}, headers=HEADERS)
            bench("bulk_upsert (10 items)", do_bulk, n=50)

            # Get collection (tests cache hit path)
            def do_get_col():
                client.get("/v1/collections/bench", headers=HEADERS)
            bench("get_collection", do_get_col, n=200)

            # List collections
            def do_list():
                client.get("/v1/collections", headers=HEADERS)
            bench("list_collections", do_list, n=100)

            print()

    print("Done.")


if __name__ == "__main__":
    main()
