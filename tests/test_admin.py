# tests/test_admin.py


def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "docs" in data
    assert "endpoints" in data


def test_health_requires_auth(client, bad_headers):
    resp = client.get("/v1/health", headers=bad_headers)
    assert resp.status_code == 401


def test_health(client, headers):
    resp = client.get("/v1/health", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["status"] == "ok"
    assert "total_vectors" in body["data"]
    assert "total_collections" in body["data"]
