# tests/test_phase5.py
"""
Phase 5: Scale & Storage Backends tests.

Covers:
- Pluggable backend architecture (backend ABC, get_backend dependency)
- SQLiteHNSWBackend correctness via the async interface
- Async endpoints (all routers use async def)
- Redis cache layer (CachingBackend) via fakeredis
- PostgreSQL backend instantiation (skipped without PG_TEST_URL)
- Backend selection via STORAGE_BACKEND config
"""
import os
import pytest
import asyncio

from tests.conftest import random_vector

ADMIN_HEADERS = {"x-api-key": "test-key"}
PG_TEST_URL = os.getenv("PG_TEST_URL", "")


# ===========================================================================
# 1. Backend abstraction
# ===========================================================================

class TestBackendAbstraction:
    def test_vector_backend_is_abstract(self):
        """VectorBackend cannot be instantiated directly."""
        from vectordb.backends.base import VectorBackend
        with pytest.raises(TypeError):
            VectorBackend()

    def test_exceptions_importable(self):
        from vectordb.backends.base import (
            CollectionNotFoundError,
            CollectionAlreadyExistsError,
            DimensionMismatchError,
            VectorNotFoundError,
        )
        assert CollectionNotFoundError("x").name == "x"
        assert CollectionAlreadyExistsError("x").name == "x"
        e = DimensionMismatchError(384, 128)
        assert e.expected == 384
        assert e.got == 128
        assert VectorNotFoundError("id1").external_id == "id1"

    def test_get_backend_dependency_exists(self):
        from vectordb.backends import get_backend
        import inspect
        assert inspect.iscoroutinefunction(get_backend)

    def test_app_has_backend_in_state(self, client):
        """The app must expose a backend in app.state."""
        from vectordb.app import app
        from vectordb.backends.base import VectorBackend
        assert isinstance(app.state.backend, VectorBackend)

    def test_default_backend_is_sqlite(self, client):
        """Default backend should be SQLiteHNSWBackend (or CachingBackend wrapping it)."""
        from vectordb.app import app
        backend = app.state.backend
        # Unwrap CachingBackend if present
        inner = getattr(backend, "_inner", backend)
        from vectordb.backends.sqlite_hnsw import SQLiteHNSWBackend
        assert isinstance(inner, SQLiteHNSWBackend)


# ===========================================================================
# 2. SQLiteHNSWBackend via async interface
# ===========================================================================

class TestSQLiteHNSWBackend:
    """Tests that directly exercise the backend's async methods."""

    @pytest.fixture(scope="class")
    def backend(self, client):
        from vectordb.app import app
        b = app.state.backend
        return getattr(b, "_inner", b)

    def test_backend_startup_ran(self, backend):
        """Startup must have completed (engine exists, index manager populated)."""
        from vectordb.backends.sqlite_hnsw import SQLiteHNSWBackend
        assert isinstance(backend, SQLiteHNSWBackend)
        assert backend._engine is not None
        assert backend._index_manager is not None

    def test_create_and_get_collection(self, backend):
        async def run():
            col = await backend.create_collection("p5-test-col", 32, "cosine")
            assert col["name"] == "p5-test-col"
            assert col["dim"] == 32
            fetched = await backend.get_collection("p5-test-col")
            assert fetched is not None
            assert fetched["name"] == "p5-test-col"
        asyncio.run(run())

    def test_collection_already_exists_raises(self, backend):
        from vectordb.backends.base import CollectionAlreadyExistsError
        async def run():
            with pytest.raises(CollectionAlreadyExistsError):
                await backend.create_collection("p5-test-col", 32, "cosine")
        asyncio.run(run())

    def test_collection_not_found_returns_none(self, backend):
        async def run():
            result = await backend.get_collection("nonexistent-xyz")
            assert result is None
        asyncio.run(run())

    def test_upsert_and_search(self, backend):
        async def run():
            vec = random_vector(32)
            result = await backend.upsert("p5-test-col", "p5-v1", vec, {"tag": "x"}, None)
            assert result["status"] == "inserted"
            results = await backend.search("p5-test-col", vec, k=1, offset=0, filters=None)
            assert len(results) == 1
            assert results[0]["external_id"] == "p5-v1"
        asyncio.run(run())

    def test_upsert_update(self, backend):
        async def run():
            vec = random_vector(32)
            await backend.upsert("p5-test-col", "p5-v1", vec, {"tag": "updated"}, None)
            result2 = await backend.upsert("p5-test-col", "p5-v1", vec, {"tag": "updated"}, None)
            assert result2["status"] == "updated"
        asyncio.run(run())

    def test_dimension_mismatch_raises(self, backend):
        from vectordb.backends.base import DimensionMismatchError
        async def run():
            with pytest.raises(DimensionMismatchError):
                await backend.upsert("p5-test-col", "bad", random_vector(64), None, None)
        asyncio.run(run())

    def test_collection_not_found_raises_on_upsert(self, backend):
        from vectordb.backends.base import CollectionNotFoundError
        async def run():
            with pytest.raises(CollectionNotFoundError):
                await backend.upsert("no-such-col", "x", random_vector(32), None, None)
        asyncio.run(run())

    def test_delete_vector(self, backend):
        from vectordb.backends.base import VectorNotFoundError
        async def run():
            await backend.upsert("p5-test-col", "p5-del", random_vector(32), None, None)
            result = await backend.delete_vector("p5-test-col", "p5-del")
            assert result["status"] == "deleted"
            with pytest.raises(VectorNotFoundError):
                await backend.delete_vector("p5-test-col", "p5-del")
        asyncio.run(run())

    def test_health_stats(self, backend):
        async def run():
            stats = await backend.health_stats()
            assert "total_vectors" in stats
            assert "total_collections" in stats
            assert isinstance(stats["collections"], list)
        asyncio.run(run())

    def test_delete_collection(self, backend):
        async def run():
            await backend.create_collection("p5-del-col", 8, "cosine")
            await backend.delete_collection("p5-del-col")
            assert await backend.get_collection("p5-del-col") is None
        asyncio.run(run())

    def test_delete_collection_not_found_raises(self, backend):
        from vectordb.backends.base import CollectionNotFoundError
        async def run():
            with pytest.raises(CollectionNotFoundError):
                await backend.delete_collection("totally-not-there")
        asyncio.run(run())


# ===========================================================================
# 3. Async endpoints (via HTTP client)
# ===========================================================================

class TestAsyncEndpoints:
    """Verify the full HTTP API still works correctly with the async backend."""

    @pytest.fixture(scope="class", autouse=True)
    def async_col(self, client):
        client.post("/v1/collections", json={
            "name": "async-test-col",
            "dim": 16,
            "distance_metric": "cosine",
        }, headers=ADMIN_HEADERS)

    def test_create_collection_async(self, client):
        resp = client.post("/v1/collections", json={
            "name": "async-new-col",
            "dim": 8,
            "distance_metric": "l2",
        }, headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "async-new-col"

    def test_upsert_async(self, client):
        resp = client.post("/v1/collections/async-test-col/upsert", json={
            "external_id": "av1",
            "vector": random_vector(16),
            "metadata": {"x": 1},
        }, headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "inserted"

    def test_bulk_upsert_async(self, client):
        items = [
            {"external_id": f"abv{i}", "vector": random_vector(16)}
            for i in range(3)
        ]
        resp = client.post(
            "/v1/collections/async-test-col/bulk_upsert",
            json={"items": items},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]["results"]) == 3

    def test_search_async(self, client):
        resp = client.post("/v1/collections/async-test-col/search", json={
            "vector": random_vector(16),
            "k": 2,
        }, headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"]["results"], list)

    def test_delete_async(self, client):
        client.post("/v1/collections/async-test-col/upsert", json={
            "external_id": "to-del",
            "vector": random_vector(16),
        }, headers=ADMIN_HEADERS)
        resp = client.delete(
            "/v1/collections/async-test-col/delete/to-del",
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "deleted"

    def test_collection_not_found_returns_404(self, client):
        resp = client.post("/v1/collections/no-such-col/search", json={
            "vector": random_vector(16),
            "k": 1,
        }, headers=ADMIN_HEADERS)
        assert resp.json()["error"]["code"] == 404

    def test_dimension_mismatch_returns_400(self, client):
        resp = client.post("/v1/collections/async-test-col/upsert", json={
            "external_id": "bad-dim",
            "vector": random_vector(999),
        }, headers=ADMIN_HEADERS)
        assert resp.json()["error"]["code"] == 400


# ===========================================================================
# 4. Redis cache layer (via fakeredis)
# ===========================================================================

class TestRedisCache:
    @pytest.fixture
    def cache_backend(self):
        """Build a CachingBackend around a real SQLiteHNSWBackend + fakeredis."""
        import fakeredis
        import fakeredis.aioredis
        from unittest.mock import patch
        from vectordb.backends.sqlite_hnsw import SQLiteHNSWBackend
        from vectordb.cache import CachingBackend, _RedisCache
        from vectordb.config import get_settings

        settings = get_settings()
        inner = SQLiteHNSWBackend(settings.db_url, settings)

        # Monkey-patch _RedisCache to use fakeredis
        original_init = _RedisCache.__init__

        def fake_init(self, redis_url, ttl):
            self._client = fakeredis.aioredis.FakeRedis(decode_responses=True)
            self._ttl = ttl

        with patch.object(_RedisCache, "__init__", fake_init):
            cb = CachingBackend(inner, "redis://fake", ttl=60)

        return cb

    def test_cache_hit_on_search(self, cache_backend):
        """Second search with same params returns cached result."""
        async def run():
            await cache_backend.startup()
            await cache_backend.create_collection("cache-col", 8, "cosine")
            vec = random_vector(8)
            await cache_backend.upsert("cache-col", "c1", vec, None, None)

            first = await cache_backend.search("cache-col", vec, k=1, offset=0, filters=None)
            second = await cache_backend.search("cache-col", vec, k=1, offset=0, filters=None)
            assert first == second
            await cache_backend.shutdown()
        asyncio.run(run())

    def test_cache_invalidated_on_upsert(self, cache_backend):
        """Cache is invalidated after a write operation."""
        async def run():
            await cache_backend.startup()
            # Create fresh collection for this test
            try:
                await cache_backend.create_collection("cache-inv-col", 8, "cosine")
            except Exception:
                pass

            vec1 = random_vector(8)
            await cache_backend.upsert("cache-inv-col", "ci1", vec1, None, None)

            # Populate cache
            await cache_backend.search("cache-inv-col", vec1, k=1, offset=0, filters=None)

            # Write should invalidate
            vec2 = random_vector(8)
            await cache_backend.upsert("cache-inv-col", "ci2", vec2, None, None)

            # New search goes to backend (not stale cache)
            results = await cache_backend.search("cache-inv-col", vec2, k=2, offset=0, filters=None)
            ids = [r["external_id"] for r in results]
            assert "ci2" in ids
            await cache_backend.shutdown()
        asyncio.run(run())

    def test_cache_key_functions(self):
        """Cache keys are deterministic and include all parameters."""
        from vectordb.cache import _search_key, _recommend_key, _hybrid_key

        k1 = _search_key("col", [1.0, 2.0], 5, 0, {"a": "b"})
        k2 = _search_key("col", [1.0, 2.0], 5, 0, {"a": "b"})
        k3 = _search_key("col", [1.0, 2.0], 10, 0, {"a": "b"})  # different k

        assert k1 == k2
        assert k1 != k3
        assert k1.startswith("search:")

        rk = _recommend_key("col", "v1", 5, 50)
        assert rk.startswith("recommend:")

        hk = _hybrid_key("col", "query", [1.0], 5, 0, 0.5, None)
        assert hk.startswith("hybrid:")

    def test_caching_backend_wraps_correctly(self, client):
        """Root endpoint exposes cache info."""
        resp = client.get("/")
        assert "cache" in resp.json()


# ===========================================================================
# 5. PostgreSQL backend (skipped without PG_TEST_URL)
# ===========================================================================

@pytest.mark.skipif(not PG_TEST_URL, reason="PG_TEST_URL not set — skipping PostgreSQL tests")
class TestPostgresVectorBackend:
    @pytest.fixture(scope="class")
    def pg_backend(self):
        from vectordb.backends.postgres_pgvector import PostgresVectorBackend
        from vectordb.config import get_settings
        settings = get_settings()
        return PostgresVectorBackend(PG_TEST_URL, settings)

    def test_startup(self, pg_backend):
        async def run():
            await pg_backend.startup()
        asyncio.run(run())

    def test_create_collection(self, pg_backend):
        async def run():
            col = await pg_backend.create_collection("pg-test", 32, "cosine")
            assert col["name"] == "pg-test"
        asyncio.run(run())

    def test_upsert_and_search(self, pg_backend):
        async def run():
            vec = random_vector(32)
            await pg_backend.upsert("pg-test", "pg-v1", vec, {"k": "v"}, None)
            results = await pg_backend.search("pg-test", vec, k=1, offset=0, filters=None)
            assert len(results) >= 1
            assert results[0]["external_id"] == "pg-v1"
        asyncio.run(run())

    def test_shutdown(self, pg_backend):
        async def run():
            await pg_backend.delete_collection("pg-test")
            await pg_backend.shutdown()
        asyncio.run(run())


@pytest.mark.skipif(not PG_TEST_URL, reason="PG_TEST_URL not set — skipping PostgreSQL tests")
class TestPostgresNewFeatures:
    """Tests for description, update_collection, count_vectors, export_vectors on Postgres."""

    @pytest.fixture(scope="class")
    def pg_backend(self):
        from vectordb.backends.postgres_pgvector import PostgresVectorBackend
        from vectordb.config import get_settings
        settings = get_settings()
        backend = PostgresVectorBackend(PG_TEST_URL, settings)
        asyncio.run(backend.startup())
        yield backend
        # cleanup
        async def teardown():
            try:
                await backend.delete_collection("pg-desc")
            except Exception:
                pass
            try:
                await backend.delete_collection("pg-export")
            except Exception:
                pass
            await backend.shutdown()
        asyncio.run(teardown())

    def test_create_with_description(self, pg_backend):
        async def run():
            col = await pg_backend.create_collection("pg-desc", 16, "cosine", description="test desc")
            assert col["description"] == "test desc"
        asyncio.run(run())

    def test_update_collection_description(self, pg_backend):
        async def run():
            updated = await pg_backend.update_collection("pg-desc", "updated!")
            assert updated is not None
            assert updated["description"] == "updated!"
        asyncio.run(run())

    def test_update_collection_clear_description(self, pg_backend):
        async def run():
            updated = await pg_backend.update_collection("pg-desc", None)
            assert updated is not None
            assert updated["description"] is None
        asyncio.run(run())

    def test_update_nonexistent_collection(self, pg_backend):
        async def run():
            result = await pg_backend.update_collection("nonexistent-pg", "x")
            assert result is None
        asyncio.run(run())

    def test_count_vectors_empty(self, pg_backend):
        async def run():
            count = await pg_backend.count_vectors("pg-desc")
            assert count == 0
        asyncio.run(run())

    def test_count_vectors_with_data(self, pg_backend):
        async def run():
            await pg_backend.upsert("pg-desc", "c1", random_vector(16), None, None)
            await pg_backend.upsert("pg-desc", "c2", random_vector(16), None, None)
            count = await pg_backend.count_vectors("pg-desc")
            assert count == 2
        asyncio.run(run())

    def test_export_vectors(self, pg_backend):
        async def run():
            await pg_backend.create_collection("pg-export", 16, "cosine")
            for i in range(5):
                await pg_backend.upsert("pg-export", f"ex{i}", random_vector(16), {"i": i}, None)
            exported = await pg_backend.export_vectors("pg-export", limit=10)
            assert len(exported) == 5
            assert "external_id" in exported[0]
            assert "vector" in exported[0]
            assert len(exported[0]["vector"]) == 16
        asyncio.run(run())

    def test_export_with_limit(self, pg_backend):
        async def run():
            exported = await pg_backend.export_vectors("pg-export", limit=2)
            assert len(exported) == 2
        asyncio.run(run())

    def test_description_in_list(self, pg_backend):
        async def run():
            await pg_backend.update_collection("pg-desc", "listed")
            cols = await pg_backend.list_collections()
            found = next((c for c in cols if c["name"] == "pg-desc"), None)
            assert found is not None
            assert found["description"] == "listed"
        asyncio.run(run())

    def test_description_in_get(self, pg_backend):
        async def run():
            col = await pg_backend.get_collection("pg-desc")
            assert col is not None
            assert col["description"] == "listed"
        asyncio.run(run())


# ===========================================================================
# 6. Config: backend selection
# ===========================================================================

class TestBackendConfig:
    def test_default_storage_backend_is_sqlite(self):
        from vectordb.config import get_settings
        assert get_settings().storage_backend == "sqlite"

    def test_redis_url_defaults_empty(self):
        from vectordb.config import get_settings
        assert get_settings().redis_url == ""

    def test_cache_ttl_default(self):
        from vectordb.config import get_settings
        assert get_settings().cache_ttl == 60

    def test_backend_factory_returns_sqlite(self):
        from vectordb.config import get_settings
        from vectordb.backends.sqlite_hnsw import SQLiteHNSWBackend
        from vectordb.app import _create_backend
        backend = _create_backend(get_settings())
        assert isinstance(backend, SQLiteHNSWBackend)

    def test_root_endpoint_shows_backend(self, client):
        resp = client.get("/")
        data = resp.json()
        assert data["backend"] == "sqlite"
        assert data["cache"] == "none"
