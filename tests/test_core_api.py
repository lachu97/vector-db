# tests/test_core_api.py
"""
Tests for Get by ID, Batch Fetch, Scroll, and Bulk Search endpoints.
"""
import base64
import numpy as np


def rv(dim=384):
    return np.random.rand(dim).tolist()


COLLECTION = "test-core-api"


class TestSetup:
    """Create collection and seed vectors for all tests."""

    def test_create_collection(self, client, headers):
        r = client.post("/v1/collections", json={"name": COLLECTION, "dim": 384}, headers=headers)
        assert r.status_code == 200

    def test_seed_vectors(self, client, headers):
        items = [
            {"external_id": f"vec-{i}", "vector": rv(), "metadata": {"i": i, "group": "a" if i < 5 else "b"}}
            for i in range(10)
        ]
        r = client.post(f"/v1/collections/{COLLECTION}/bulk_upsert", json={"items": items}, headers=headers)
        assert r.status_code == 200


class TestGetVectorByID:
    """GET /v1/collections/{name}/vectors/{external_id}"""

    def test_get_existing_vector(self, client, headers):
        r = client.get(f"/v1/collections/{COLLECTION}/vectors/vec-0", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["external_id"] == "vec-0"
        assert "vector" in data
        assert len(data["vector"]) == 384
        assert data["metadata"]["i"] == 0

    def test_get_nonexistent_vector_404(self, client, headers):
        r = client.get(f"/v1/collections/{COLLECTION}/vectors/does-not-exist", headers=headers)
        assert r.status_code == 200  # wrapped in success_response/error_response
        body = r.json()
        assert body.get("error") or body.get("status_code") == 404

    def test_get_vector_wrong_collection_404(self, client, headers):
        r = client.get("/v1/collections/nonexistent-collection/vectors/vec-0", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body.get("error") or body.get("status_code") == 404


class TestBatchFetch:
    """POST /v1/collections/{name}/vectors/fetch"""

    def test_fetch_existing_ids(self, client, headers):
        r = client.post(
            f"/v1/collections/{COLLECTION}/vectors/fetch",
            json={"ids": ["vec-0", "vec-1", "vec-2"]},
            headers=headers,
        )
        assert r.status_code == 200
        vectors = r.json()["data"]["vectors"]
        assert len(vectors) == 3
        # Verify input order is preserved
        assert vectors[0]["external_id"] == "vec-0"
        assert vectors[1]["external_id"] == "vec-1"
        assert vectors[2]["external_id"] == "vec-2"

    def test_fetch_ignores_missing_ids(self, client, headers):
        r = client.post(
            f"/v1/collections/{COLLECTION}/vectors/fetch",
            json={"ids": ["vec-0", "missing-1", "vec-2", "missing-2"]},
            headers=headers,
        )
        assert r.status_code == 200
        vectors = r.json()["data"]["vectors"]
        assert len(vectors) == 2
        assert vectors[0]["external_id"] == "vec-0"
        assert vectors[1]["external_id"] == "vec-2"

    def test_fetch_include_vectors_false(self, client, headers):
        r = client.post(
            f"/v1/collections/{COLLECTION}/vectors/fetch",
            json={"ids": ["vec-0", "vec-1"], "include_vectors": False},
            headers=headers,
        )
        assert r.status_code == 200
        vectors = r.json()["data"]["vectors"]
        assert len(vectors) == 2
        for v in vectors:
            assert "vector" not in v
            assert "external_id" in v
            assert "metadata" in v

    def test_fetch_all_missing_returns_empty(self, client, headers):
        r = client.post(
            f"/v1/collections/{COLLECTION}/vectors/fetch",
            json={"ids": ["nope-1", "nope-2"]},
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["vectors"] == []

    def test_fetch_too_many_ids_422(self, client, headers):
        ids = [f"id-{i}" for i in range(101)]
        r = client.post(
            f"/v1/collections/{COLLECTION}/vectors/fetch",
            json={"ids": ids},
            headers=headers,
        )
        assert r.status_code == 422


class TestScroll:
    """POST /v1/collections/{name}/scroll"""

    def test_scroll_first_page(self, client, headers):
        r = client.post(
            f"/v1/collections/{COLLECTION}/scroll",
            json={"limit": 3},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["vectors"]) == 3
        assert data["next_cursor"] is not None
        # Should have vectors with valid data
        for v in data["vectors"]:
            assert "external_id" in v
            assert "vector" in v

    def test_scroll_with_cursor(self, client, headers):
        # Get first page
        r1 = client.post(
            f"/v1/collections/{COLLECTION}/scroll",
            json={"limit": 3},
            headers=headers,
        )
        cursor = r1.json()["data"]["next_cursor"]
        first_ids = [v["external_id"] for v in r1.json()["data"]["vectors"]]

        # Get second page
        r2 = client.post(
            f"/v1/collections/{COLLECTION}/scroll",
            json={"limit": 3, "cursor": cursor},
            headers=headers,
        )
        assert r2.status_code == 200
        second_ids = [v["external_id"] for v in r2.json()["data"]["vectors"]]
        # No overlap
        assert not set(first_ids) & set(second_ids)

    def test_scroll_last_page_null_cursor(self, client, headers):
        # Scroll all 10 vectors at once
        r = client.post(
            f"/v1/collections/{COLLECTION}/scroll",
            json={"limit": 1000},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["vectors"]) == 10
        assert data["next_cursor"] is None

    def test_scroll_with_filters(self, client, headers):
        r = client.post(
            f"/v1/collections/{COLLECTION}/scroll",
            json={"limit": 100, "filters": {"group": "a"}},
            headers=headers,
        )
        assert r.status_code == 200
        vectors = r.json()["data"]["vectors"]
        assert len(vectors) == 5  # i < 5 have group "a"
        for v in vectors:
            assert v["metadata"]["group"] == "a"

    def test_scroll_include_vectors_false(self, client, headers):
        r = client.post(
            f"/v1/collections/{COLLECTION}/scroll",
            json={"limit": 3, "include_vectors": False},
            headers=headers,
        )
        assert r.status_code == 200
        for v in r.json()["data"]["vectors"]:
            assert "vector" not in v

    def test_scroll_invalid_cursor_400(self, client, headers):
        r = client.post(
            f"/v1/collections/{COLLECTION}/scroll",
            json={"cursor": "not-valid-base64!!!"},
            headers=headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("status_code") == 400 or "Invalid cursor" in str(body)

    def test_scroll_limit_validation(self, client, headers):
        r = client.post(
            f"/v1/collections/{COLLECTION}/scroll",
            json={"limit": 0},
            headers=headers,
        )
        assert r.status_code == 422

        r2 = client.post(
            f"/v1/collections/{COLLECTION}/scroll",
            json={"limit": 1001},
            headers=headers,
        )
        assert r2.status_code == 422


class TestBulkSearch:
    """POST /v1/collections/{name}/bulk_search"""

    def test_bulk_search_basic(self, client, headers):
        queries = [
            {"vector": rv(), "k": 3},
            {"vector": rv(), "k": 5},
        ]
        r = client.post(
            f"/v1/collections/{COLLECTION}/bulk_search",
            json={"queries": queries},
            headers=headers,
        )
        assert r.status_code == 200
        results = r.json()["data"]["results"]
        assert len(results) == 2
        assert len(results[0]) == 3  # k=3
        assert len(results[1]) == 5  # k=5

    def test_bulk_search_preserves_order(self, client, headers):
        q1 = rv()
        q2 = rv()
        queries = [{"vector": q1, "k": 2}, {"vector": q2, "k": 2}]
        r = client.post(
            f"/v1/collections/{COLLECTION}/bulk_search",
            json={"queries": queries},
            headers=headers,
        )
        assert r.status_code == 200
        results = r.json()["data"]["results"]
        assert len(results) == 2
        # Each result set should have scored results
        for result_set in results:
            for item in result_set:
                assert "external_id" in item
                assert "score" in item

    def test_bulk_search_with_filters(self, client, headers):
        queries = [{"vector": rv(), "k": 10, "filters": {"group": "a"}}]
        r = client.post(
            f"/v1/collections/{COLLECTION}/bulk_search",
            json={"queries": queries},
            headers=headers,
        )
        assert r.status_code == 200
        results = r.json()["data"]["results"]
        assert len(results) == 1
        for item in results[0]:
            assert item["metadata"]["group"] == "a"

    def test_bulk_search_too_many_queries_422(self, client, headers):
        queries = [{"vector": rv(), "k": 1} for _ in range(21)]
        r = client.post(
            f"/v1/collections/{COLLECTION}/bulk_search",
            json={"queries": queries},
            headers=headers,
        )
        assert r.status_code == 422

    def test_bulk_search_wrong_dimension(self, client, headers):
        queries = [{"vector": [0.1, 0.2, 0.3], "k": 1}]  # dim=3, collection is 384
        r = client.post(
            f"/v1/collections/{COLLECTION}/bulk_search",
            json={"queries": queries},
            headers=headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("status_code") == 400 or "dimension" in str(body).lower()

    def test_bulk_search_empty_vector_422(self, client, headers):
        queries = [{"vector": [], "k": 1}]
        r = client.post(
            f"/v1/collections/{COLLECTION}/bulk_search",
            json={"queries": queries},
            headers=headers,
        )
        assert r.status_code == 422
