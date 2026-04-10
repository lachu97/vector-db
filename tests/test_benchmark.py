# tests/test_benchmark.py
"""
Performance benchmark tests.
Asserts that critical operations complete within target latency.
"""
import time
import numpy as np


def rv(dim=384):
    return np.random.rand(dim).tolist()


LATENCY_TARGET_MS = 20


class TestSearchLatency:
    """Search must complete under 20ms."""

    def _setup_collection(self, client, headers, name, count=50):
        client.post("/v1/collections", json={"name": name, "dim": 384}, headers=headers)
        items = [{"external_id": f"bench-{i}", "vector": rv(), "metadata": {"i": i}} for i in range(count)]
        client.post(f"/v1/collections/{name}/bulk_upsert", json={"items": items}, headers=headers)

    def test_search_k10_under_20ms(self, client, headers):
        self._setup_collection(client, headers, "bench-search", count=100)

        # Warm up (first search may load index)
        client.post("/v1/collections/bench-search/search",
                     json={"vector": rv(), "k": 10}, headers=headers)

        # Measure 10 searches, take median
        times = []
        for _ in range(10):
            t0 = time.perf_counter()
            r = client.post("/v1/collections/bench-search/search",
                            json={"vector": rv(), "k": 10}, headers=headers)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            assert r.status_code == 200
            times.append(elapsed_ms)

        median_ms = sorted(times)[len(times) // 2]
        assert median_ms < LATENCY_TARGET_MS, f"Median search latency {median_ms:.1f}ms exceeds {LATENCY_TARGET_MS}ms target"

    def test_search_k50_under_20ms(self, client, headers):
        self._setup_collection(client, headers, "bench-search-k50", count=200)

        client.post("/v1/collections/bench-search-k50/search",
                     json={"vector": rv(), "k": 50}, headers=headers)

        times = []
        for _ in range(10):
            t0 = time.perf_counter()
            r = client.post("/v1/collections/bench-search-k50/search",
                            json={"vector": rv(), "k": 50}, headers=headers)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            assert r.status_code == 200
            times.append(elapsed_ms)

        median_ms = sorted(times)[len(times) // 2]
        assert median_ms < LATENCY_TARGET_MS, f"Median search latency {median_ms:.1f}ms exceeds {LATENCY_TARGET_MS}ms target"

    def test_search_with_filters_under_20ms(self, client, headers):
        self._setup_collection(client, headers, "bench-filter", count=100)

        client.post("/v1/collections/bench-filter/search",
                     json={"vector": rv(), "k": 10, "filters": {"i": 5}}, headers=headers)

        times = []
        for _ in range(10):
            t0 = time.perf_counter()
            r = client.post("/v1/collections/bench-filter/search",
                            json={"vector": rv(), "k": 10, "filters": {"i": 5}}, headers=headers)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            assert r.status_code == 200
            times.append(elapsed_ms)

        median_ms = sorted(times)[len(times) // 2]
        assert median_ms < LATENCY_TARGET_MS, f"Median filtered search latency {median_ms:.1f}ms exceeds {LATENCY_TARGET_MS}ms target"


class TestUpsertLatency:
    """Single upsert must complete under 20ms."""

    def test_upsert_under_20ms(self, client, headers):
        client.post("/v1/collections", json={"name": "bench-upsert", "dim": 384}, headers=headers)

        # Warm up
        client.post("/v1/collections/bench-upsert/upsert",
                     json={"external_id": "warmup", "vector": rv()}, headers=headers)

        times = []
        for i in range(10):
            t0 = time.perf_counter()
            r = client.post("/v1/collections/bench-upsert/upsert",
                            json={"external_id": f"perf-{i}", "vector": rv()}, headers=headers)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            assert r.status_code == 200
            times.append(elapsed_ms)

        median_ms = sorted(times)[len(times) // 2]
        assert median_ms < LATENCY_TARGET_MS, f"Median upsert latency {median_ms:.1f}ms exceeds {LATENCY_TARGET_MS}ms target"


class TestRecommendLatency:
    """Recommend must complete under 20ms."""

    def test_recommend_under_20ms(self, client, headers):
        client.post("/v1/collections", json={"name": "bench-rec", "dim": 384}, headers=headers)
        items = [{"external_id": f"rec-{i}", "vector": rv()} for i in range(50)]
        client.post("/v1/collections/bench-rec/bulk_upsert", json={"items": items}, headers=headers)

        # Warm up
        client.post("/v1/collections/bench-rec/recommend/rec-0",
                     json={"k": 5}, headers=headers)

        times = []
        for i in range(10):
            t0 = time.perf_counter()
            r = client.post(f"/v1/collections/bench-rec/recommend/rec-{i % 50}",
                            json={"k": 10}, headers=headers)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            assert r.status_code == 200
            times.append(elapsed_ms)

        median_ms = sorted(times)[len(times) // 2]
        assert median_ms < LATENCY_TARGET_MS, f"Median recommend latency {median_ms:.1f}ms exceeds {LATENCY_TARGET_MS}ms target"


class TestHealthLatency:
    """Health endpoint must be fast even with many collections."""

    def test_health_under_20ms(self, client, headers):
        # Warm up
        client.get("/v1/health", headers=headers)

        times = []
        for _ in range(10):
            t0 = time.perf_counter()
            r = client.get("/v1/health", headers=headers)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            assert r.status_code == 200
            times.append(elapsed_ms)

        median_ms = sorted(times)[len(times) // 2]
        assert median_ms < LATENCY_TARGET_MS, f"Median health latency {median_ms:.1f}ms exceeds {LATENCY_TARGET_MS}ms target"
