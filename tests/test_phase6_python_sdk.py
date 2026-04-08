# tests/test_phase6_python_sdk.py
"""
Phase 6: Python SDK tests.

Tests the SDK against the real FastAPI test server using httpx transport
to avoid needing a running server.  Both sync (VectorDBClient) and async
(AsyncVectorDBClient) clients are covered.
"""
import asyncio
import pytest
import httpx
from httpx import MockTransport

from tests.conftest import random_vector

# We use the ASGI transport so the SDK hits the real application code.
from vectordb.app import app as _fastapi_app

ADMIN_KEY = "test-key"
BAD_KEY = "wrong-key"


# ---------------------------------------------------------------------------
# Helpers: patch the SDK http internals to use the test ASGI transport
# ---------------------------------------------------------------------------

def _make_sync_client(test_client):
    """
    Build a VectorDBClient whose underlying session is the pytest TestClient
    (a requests.Session subclass), so requests hit the in-process ASGI app.
    """
    from vectordb_client.client import VectorDBClient

    client = VectorDBClient(base_url="http://testserver", api_key=ADMIN_KEY)
    # TestClient IS a requests.Session — swap it in directly.
    # We need to preserve the api-key header though.
    test_client.headers.update({
        "x-api-key": ADMIN_KEY,
        "Accept": "application/json",
    })
    client.collections._session = test_client
    client.vectors._session = test_client
    client.search._session = test_client
    client.observability._session = test_client
    return client


async def _make_async_client():
    """Build an AsyncVectorDBClient backed by the in-process ASGI app."""
    from vectordb_client.async_client import AsyncVectorDBClient

    transport = httpx.ASGITransport(app=_fastapi_app)
    http = httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"x-api-key": ADMIN_KEY, "Accept": "application/json"},
        timeout=30,
    )

    ac = AsyncVectorDBClient.__new__(AsyncVectorDBClient)
    ac._base_url = "http://testserver"
    ac._api_key = ADMIN_KEY
    ac._timeout = 30
    ac._http = http
    ac._init_resources()
    return ac, http


# ---------------------------------------------------------------------------
# Sync client tests
# ---------------------------------------------------------------------------

class TestSyncSDKCollections:
    @pytest.fixture(scope="class")
    def sdk(self, client):
        return _make_sync_client(client)

    def test_create_collection(self, sdk):
        col = sdk.collections.create("sdk-sync-col", dim=16, distance_metric="cosine")
        assert col.name == "sdk-sync-col"
        assert col.dim == 16
        assert col.distance_metric == "cosine"

    def test_list_collections(self, sdk):
        cols = sdk.collections.list()
        names = [c.name for c in cols]
        assert "sdk-sync-col" in names

    def test_get_collection(self, sdk):
        col = sdk.collections.get("sdk-sync-col")
        assert col.name == "sdk-sync-col"

    def test_get_collection_not_found(self, sdk):
        from vectordb_client.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            sdk.collections.get("totally-missing-xyz")

    def test_already_exists_error(self, sdk):
        from vectordb_client.exceptions import AlreadyExistsError
        with pytest.raises(AlreadyExistsError):
            sdk.collections.create("sdk-sync-col", dim=16)


class TestSyncSDKVectors:
    @pytest.fixture(scope="class")
    def sdk(self, client):
        sdk_client = _make_sync_client(client)
        try:
            sdk_client.collections.create("sdk-vec-col", dim=8)
        except Exception:
            pass
        return sdk_client

    def test_upsert_insert(self, sdk):
        r = sdk.vectors.upsert("sdk-vec-col", "v1", random_vector(8), {"tag": "a"})
        assert r.external_id == "v1"
        assert r.status == "inserted"

    def test_upsert_update(self, sdk):
        r = sdk.vectors.upsert("sdk-vec-col", "v1", random_vector(8), {"tag": "b"})
        assert r.status == "updated"

    def test_bulk_upsert(self, sdk):
        items = [{"external_id": f"bv{i}", "vector": random_vector(8)} for i in range(3)]
        result = sdk.vectors.bulk_upsert("sdk-vec-col", items)
        assert len(result.results) == 3
        assert all(r.status in ("inserted", "updated") for r in result.results)

    def test_bulk_upsert_inserted_property(self, sdk):
        items = [{"external_id": "new-bv-x", "vector": random_vector(8)}]
        result = sdk.vectors.bulk_upsert("sdk-vec-col", items)
        assert len(result.inserted) >= 1

    def test_delete(self, sdk):
        sdk.vectors.upsert("sdk-vec-col", "to-del", random_vector(8))
        r = sdk.vectors.delete("sdk-vec-col", "to-del")
        assert r["status"] == "deleted"

    def test_delete_batch(self, sdk):
        for i in range(3):
            sdk.vectors.upsert("sdk-vec-col", f"batch-del-{i}", random_vector(8))
        r = sdk.vectors.delete_batch("sdk-vec-col", ["batch-del-0", "batch-del-1", "batch-del-2"])
        assert r["deleted_count"] == 3

    def test_dimension_mismatch_error(self, sdk):
        from vectordb_client.exceptions import DimensionMismatchError
        with pytest.raises(DimensionMismatchError):
            sdk.vectors.upsert("sdk-vec-col", "bad", random_vector(999))


class TestSyncSDKSearch:
    @pytest.fixture(scope="class")
    def sdk(self, client):
        sdk_client = _make_sync_client(client)
        try:
            sdk_client.collections.create("sdk-search-col", dim=8)
        except Exception:
            pass
        vec = random_vector(8)
        sdk_client.vectors.upsert("sdk-search-col", "s1", vec, {"label": "alpha"})
        sdk_client.vectors.upsert("sdk-search-col", "s2", random_vector(8), {"label": "beta"})
        return sdk_client, vec

    def test_search_returns_results(self, sdk):
        client, vec = sdk
        result = client.search.search("sdk-search-col", vec, k=2)
        assert len(result) >= 1
        assert hasattr(result[0], "external_id")
        assert hasattr(result[0], "score")

    def test_search_iterable(self, sdk):
        client, vec = sdk
        result = client.search.search("sdk-search-col", vec, k=2)
        ids = [r.external_id for r in result]
        assert len(ids) >= 1

    def test_recommend(self, sdk):
        client, _ = sdk
        result = client.search.recommend("sdk-search-col", "s1", k=2)
        ids = [r.external_id for r in result]
        # s1 is excluded from its own recommendations
        assert "s1" not in ids

    def test_similarity(self, sdk):
        client, _ = sdk
        score = client.search.similarity("sdk-search-col", "s1", "s1")
        assert abs(score - 1.0) < 0.01  # same vector = max similarity

    def test_rerank(self, sdk):
        client, vec = sdk
        results = client.search.rerank("sdk-search-col", vec, ["s1", "s2"])
        assert len(results) == 2
        assert all(hasattr(r, "score") for r in results)

    def test_hybrid_search(self, sdk):
        client, vec = sdk
        result = client.search.hybrid_search("sdk-search-col", "alpha", vec, k=2)
        assert isinstance(result.results, list)

    def test_health(self, sdk):
        client, _ = sdk
        h = client.observability.health()
        assert h.status in ("ok", "healthy")
        assert h.total_collections >= 0


# ---------------------------------------------------------------------------
# Async client tests
# ---------------------------------------------------------------------------

class TestAsyncSDKCollections:
    def test_create_and_get_collection(self):
        async def run():
            ac, http = await _make_async_client()
            try:
                col = await ac.collections.create("sdk-async-col", dim=16, distance_metric="l2")
                assert col.name == "sdk-async-col"
                assert col.dim == 16
                fetched = await ac.collections.get("sdk-async-col")
                assert fetched.name == "sdk-async-col"
            finally:
                await http.aclose()
        asyncio.run(run())

    def test_list_collections_async(self):
        async def run():
            ac, http = await _make_async_client()
            try:
                cols = await ac.collections.list()
                assert isinstance(cols, list)
            finally:
                await http.aclose()
        asyncio.run(run())

    def test_already_exists_raises_async(self):
        from vectordb_client.exceptions import AlreadyExistsError
        async def run():
            ac, http = await _make_async_client()
            try:
                with pytest.raises(AlreadyExistsError):
                    await ac.collections.create("sdk-async-col", dim=16)
            finally:
                await http.aclose()
        asyncio.run(run())

    def test_not_found_raises_async(self):
        from vectordb_client.exceptions import NotFoundError
        async def run():
            ac, http = await _make_async_client()
            try:
                with pytest.raises(NotFoundError):
                    await ac.collections.get("no-such-collection-xyz")
            finally:
                await http.aclose()
        asyncio.run(run())


class TestAsyncSDKVectors:
    def test_upsert_and_search(self):
        async def run():
            ac, http = await _make_async_client()
            try:
                try:
                    await ac.collections.create("sdk-async-vec-col", dim=8)
                except Exception:
                    pass
                vec = random_vector(8)
                r = await ac.vectors.upsert("sdk-async-vec-col", "av1", vec, {"tag": "test"})
                assert r.status == "inserted"
                results = await ac.search.search("sdk-async-vec-col", vec, k=1)
                assert len(results) == 1
                assert results[0].external_id == "av1"
            finally:
                await http.aclose()
        asyncio.run(run())

    def test_bulk_upsert_async(self):
        async def run():
            ac, http = await _make_async_client()
            try:
                try:
                    await ac.collections.create("sdk-async-bulk-col", dim=8)
                except Exception:
                    pass
                items = [{"external_id": f"abv{i}", "vector": random_vector(8)} for i in range(3)]
                result = await ac.vectors.bulk_upsert("sdk-async-bulk-col", items)
                assert len(result.results) == 3
            finally:
                await http.aclose()
        asyncio.run(run())

    def test_delete_async(self):
        async def run():
            ac, http = await _make_async_client()
            try:
                try:
                    await ac.collections.create("sdk-async-del-col", dim=8)
                except Exception:
                    pass
                await ac.vectors.upsert("sdk-async-del-col", "del-v", random_vector(8))
                r = await ac.vectors.delete("sdk-async-del-col", "del-v")
                assert r["status"] == "deleted"
            finally:
                await http.aclose()
        asyncio.run(run())


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class TestSDKExceptions:
    def test_exception_hierarchy(self):
        from vectordb_client.exceptions import (
            VectorDBError,
            NotFoundError,
            AlreadyExistsError,
            DimensionMismatchError,
            AuthenticationError,
            RateLimitError,
        )
        assert issubclass(NotFoundError, VectorDBError)
        assert issubclass(AlreadyExistsError, VectorDBError)
        assert issubclass(DimensionMismatchError, VectorDBError)
        assert issubclass(AuthenticationError, VectorDBError)
        assert issubclass(RateLimitError, VectorDBError)

    def test_error_has_status_code(self):
        from vectordb_client.exceptions import NotFoundError
        err = NotFoundError("not found", status_code=404)
        assert err.status_code == 404

    def test_raise_for_response_404(self):
        from vectordb_client._http import _raise_for_response
        from vectordb_client.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            _raise_for_response(404, {"error": {"message": "not found"}})

    def test_raise_for_response_409(self):
        from vectordb_client._http import _raise_for_response
        from vectordb_client.exceptions import AlreadyExistsError
        with pytest.raises(AlreadyExistsError):
            _raise_for_response(409, {"error": {"message": "exists"}})

    def test_raise_for_response_dimension_mismatch(self):
        from vectordb_client._http import _raise_for_response
        from vectordb_client.exceptions import DimensionMismatchError
        with pytest.raises(DimensionMismatchError):
            _raise_for_response(400, {"error": {"message": "dimension mismatch"}})

    def test_raise_for_response_429(self):
        from vectordb_client._http import _raise_for_response
        from vectordb_client.exceptions import RateLimitError
        with pytest.raises(RateLimitError):
            _raise_for_response(429, {"error": {"message": "too many requests"}})

    def test_raise_for_response_auth(self):
        from vectordb_client._http import _raise_for_response
        from vectordb_client.exceptions import AuthenticationError
        with pytest.raises(AuthenticationError):
            _raise_for_response(401, {"error": {"message": "unauthorized"}})


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TestSDKModels:
    def test_collection_from_dict(self):
        from vectordb_client.models import Collection
        c = Collection.from_dict({"name": "x", "dim": 128, "distance_metric": "l2"})
        assert c.name == "x"
        assert c.dim == 128
        assert c.distance_metric == "l2"
        assert c.vector_count == 0

    def test_upsert_result(self):
        from vectordb_client.models import UpsertResult
        r = UpsertResult.from_dict({"external_id": "v1", "status": "inserted"})
        assert r.external_id == "v1"
        assert r.status == "inserted"

    def test_bulk_upsert_result_properties(self):
        from vectordb_client.models import BulkUpsertResult, UpsertResult
        result = BulkUpsertResult(results=[
            UpsertResult("a", "inserted"),
            UpsertResult("b", "updated"),
            UpsertResult("c", "inserted"),
        ])
        assert len(result.inserted) == 2
        assert len(result.updated) == 1

    def test_search_result_indexing(self):
        from vectordb_client.models import SearchResult, VectorResult
        sr = SearchResult(
            results=[VectorResult("v1", 0.9, {}), VectorResult("v2", 0.8, {})],
            collection="col",
            k=2,
        )
        assert len(sr) == 2
        assert sr[0].external_id == "v1"
        ids = [r.external_id for r in sr]
        assert ids == ["v1", "v2"]

    def test_health_stats(self):
        from vectordb_client.models import HealthStats
        h = HealthStats.from_dict({
            "status": "ok",
            "total_vectors": 100,
            "total_collections": 3,
            "collections": [],
        })
        assert h.total_vectors == 100
        assert h.total_collections == 3


# ---------------------------------------------------------------------------
# New feature tests: description, export, total_count, keys resource
# ---------------------------------------------------------------------------

class TestSyncSDKNewFeatures:
    @pytest.fixture(scope="class")
    def sdk(self, client):
        s = _make_sync_client(client)
        s.keys._session = client
        return s

    def test_create_collection_with_description(self, sdk):
        col = sdk.collections.create("sdk-desc-col", dim=16, description="test desc")
        assert col.description == "test desc"

    def test_update_collection_description(self, sdk):
        sdk.collections.create("sdk-update-desc", dim=16)
        col = sdk.collections.update("sdk-update-desc", "updated!")
        assert col.description == "updated!"

    def test_update_collection_clear_description(self, sdk):
        sdk.collections.create("sdk-clear-desc", dim=16, description="initial")
        col = sdk.collections.update("sdk-clear-desc", None)
        assert col.description is None

    def test_export_empty_collection(self, sdk):
        sdk.collections.create("sdk-export-empty", dim=16)
        result = sdk.collections.export("sdk-export-empty")
        assert result.count == 0
        assert result.vectors == []

    def test_export_with_vectors(self, sdk):
        sdk.collections.create("sdk-export-full", dim=16)
        for i in range(3):
            sdk.vectors.upsert("sdk-export-full", f"e{i}", random_vector(16))
        result = sdk.collections.export("sdk-export-full")
        assert result.count == 3
        assert len(result.vectors) == 3
        assert len(result.vectors[0].vector) == 16

    def test_search_returns_total_count(self, sdk):
        sdk.collections.create("sdk-tc-col", dim=16)
        for i in range(5):
            sdk.vectors.upsert("sdk-tc-col", f"tc{i}", random_vector(16))
        result = sdk.search.search("sdk-tc-col", random_vector(16), k=3)
        assert result.total_count >= 5
        assert result.offset == 0
        assert result.k == 3

    def test_keys_create_and_list(self, sdk):
        key = sdk.keys.create("sdk-test-key", role="readonly")
        assert key.name == "sdk-test-key"
        assert key.role == "readonly"
        assert key.key is not None  # returned at creation
        keys = sdk.keys.list()
        assert any(k.name == "sdk-test-key" for k in keys)

    def test_keys_get(self, sdk):
        key = sdk.keys.create("sdk-get-key", role="readwrite")
        fetched = sdk.keys.get(key.id)
        assert fetched.id == key.id
        assert fetched.name == "sdk-get-key"

    def test_keys_update(self, sdk):
        key = sdk.keys.create("sdk-upd-key", role="readonly")
        updated = sdk.keys.update(key.id, name="sdk-upd-key-renamed")
        assert updated.name == "sdk-upd-key-renamed"

    def test_keys_revoke_restore(self, sdk):
        key = sdk.keys.create("sdk-revoke-key", role="readonly")
        revoked = sdk.keys.revoke(key.id)
        assert revoked.is_active is False
        restored = sdk.keys.restore(key.id)
        assert restored.is_active is True

    def test_keys_rotate(self, sdk):
        key = sdk.keys.create("sdk-rotate-key", role="readonly")
        rotated = sdk.keys.rotate(key.id)
        assert rotated.key is not None
        assert rotated.key != key.key

    def test_keys_get_usage(self, sdk):
        key = sdk.keys.create("sdk-usage-key", role="readonly")
        usage = sdk.keys.get_usage(key.id)
        assert usage.total_requests >= 0
        assert "last_24h" in usage.__dataclass_fields__

    def test_keys_usage_summary(self, sdk):
        data = sdk.keys.get_usage_summary()
        assert "overall" in data
        assert "by_key" in data

    def test_keys_delete(self, sdk):
        key = sdk.keys.create("sdk-del-key", role="readonly")
        result = sdk.keys.delete(key.id)
        assert result["deleted"] is True


class TestSDKModelsNew:
    def test_collection_description_field(self):
        from vectordb_client.models import Collection
        col = Collection.from_dict({
            "name": "c", "dim": 4, "distance_metric": "cosine",
            "description": "hello",
        })
        assert col.description == "hello"

    def test_collection_no_description(self):
        from vectordb_client.models import Collection
        col = Collection.from_dict({"name": "c", "dim": 4, "distance_metric": "cosine"})
        assert col.description is None

    def test_search_result_total_count(self):
        from vectordb_client.models import SearchResult
        sr = SearchResult.from_dict(
            {"results": [], "total_count": 42, "offset": 5},
            collection="col", k=10,
        )
        assert sr.total_count == 42
        assert sr.offset == 5

    def test_export_result(self):
        from vectordb_client.models import ExportResult
        er = ExportResult.from_dict({
            "collection": "c", "dim": 4, "distance_metric": "cosine",
            "count": 1, "vectors": [{"external_id": "x", "vector": [1.0, 2.0, 3.0, 4.0]}],
        })
        assert er.count == 1
        assert er.vectors[0].external_id == "x"
        assert len(er.vectors[0].vector) == 4

    def test_api_key_model(self):
        from vectordb_client.models import ApiKey
        k = ApiKey.from_dict({
            "id": 1, "name": "prod", "role": "readwrite",
            "is_active": True, "created_at": "2026-01-01",
            "expires_at": None, "last_used_at": None, "key": "abc123",
        })
        assert k.id == 1
        assert k.key == "abc123"

    def test_key_usage_stats_model(self):
        from vectordb_client.models import KeyUsageStats
        s = KeyUsageStats.from_dict({
            "total_requests": 10, "last_24h": 2, "last_7d": 5, "last_30d": 10,
            "by_endpoint": {"/v1/search": 8}, "last_request_at": "2026-01-01",
        })
        assert s.total_requests == 10
        assert s.by_endpoint["/v1/search"] == 8
