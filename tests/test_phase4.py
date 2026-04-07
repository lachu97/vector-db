# tests/test_phase4.py
"""
Phase 4: Observability tests.

Covers:
- Structured logging (structlog configured, JSON/console output)
- Prometheus /metrics endpoint (format, labels, no auth)
- Enhanced /v1/health endpoint (uptime, per-collection stats)
- MetricsMiddleware (request count and latency recorded)
- OpenTelemetry tracing disabled by default (no errors)
"""
import io

import pytest
import structlog

from tests.conftest import random_vector

ADMIN_HEADERS = {"x-api-key": "test-key"}


# ===========================================================================
# 1. Structured logging (structlog)
# ===========================================================================

class TestStructuredLogging:
    def test_structlog_configured(self):
        """structlog.get_logger() returns a working bound logger."""
        logger = structlog.get_logger("test")
        # Should not raise; structured call works
        assert logger is not None

    def test_structlog_json_output(self):
        """JSON renderer produces valid JSON with expected keys."""
        import json

        output = io.StringIO()
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(10),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=output),
            cache_logger_on_first_use=False,
        )
        log = structlog.get_logger("test_json")
        log.info("test_event", key="value", count=42)

        line = output.getvalue().strip()
        assert line, "No output produced"
        parsed = json.loads(line)
        assert parsed["event"] == "test_event"
        assert parsed["key"] == "value"
        assert parsed["count"] == 42
        assert "timestamp" in parsed
        assert parsed["level"] == "info"

    def test_structlog_console_output(self):
        """Console renderer produces non-JSON human-readable output."""
        output = io.StringIO()
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.dev.ConsoleRenderer(colors=False),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(10),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=output),
            cache_logger_on_first_use=False,
        )
        log = structlog.get_logger("test_console")
        log.warning("console_event", foo="bar")

        line = output.getvalue()
        assert "console_event" in line
        assert "foo" in line


# ===========================================================================
# 2. Prometheus /metrics endpoint
# ===========================================================================

class TestPrometheusMetrics:
    def test_metrics_endpoint_accessible_without_auth(self, client):
        """/metrics must be accessible without an API key."""
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_content_type(self, client):
        """Content-Type must be Prometheus text format."""
        resp = client.get("/metrics")
        assert "text/plain" in resp.headers["content-type"]

    def test_metrics_contains_request_counter(self, client):
        """After making a request, vectordb_requests_total should appear."""
        # Make a request to generate data
        client.get("/v1/health", headers=ADMIN_HEADERS)

        resp = client.get("/metrics")
        assert resp.status_code == 200
        body = resp.text
        assert "vectordb_requests_total" in body

    def test_metrics_contains_latency_histogram(self, client):
        client.get("/v1/health", headers=ADMIN_HEADERS)
        resp = client.get("/metrics")
        assert "vectordb_request_duration_seconds" in resp.text

    def test_metrics_contains_collection_gauge(self, client):
        """vectordb_collections_total gauge should appear after /v1/health refreshes it."""
        client.get("/v1/health", headers=ADMIN_HEADERS)
        resp = client.get("/metrics")
        assert "vectordb_collections_total" in resp.text

    def test_metrics_contains_vector_gauge(self, client):
        client.get("/v1/health", headers=ADMIN_HEADERS)
        resp = client.get("/metrics")
        assert "vectordb_vectors_total" in resp.text

    def test_metrics_labels_method(self, client):
        """Labels include HTTP method."""
        client.get("/v1/health", headers=ADMIN_HEADERS)
        resp = client.get("/metrics")
        assert 'method="GET"' in resp.text

    def test_metrics_labels_status_code(self, client):
        """Labels include status code."""
        client.get("/v1/health", headers=ADMIN_HEADERS)
        resp = client.get("/metrics")
        assert 'status_code="200"' in resp.text


# ===========================================================================
# 3. Enhanced /v1/health endpoint
# ===========================================================================

class TestEnhancedHealth:
    @pytest.fixture(scope="class", autouse=True)
    def seed_collection(self, client):
        """Create a collection with vectors for health stats testing."""
        client.post("/v1/collections", json={
            "name": "health-test-col",
            "dim": 16,
            "distance_metric": "cosine",
        }, headers=ADMIN_HEADERS)
        client.post("/v1/collections/health-test-col/upsert", json={
            "external_id": "h1",
            "vector": random_vector(16),
        }, headers=ADMIN_HEADERS)

    def test_health_returns_ok(self, client):
        resp = client.get("/v1/health", headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "ok"

    def test_health_has_uptime(self, client):
        resp = client.get("/v1/health", headers=ADMIN_HEADERS)
        data = resp.json()["data"]
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], (int, float))
        assert data["uptime_seconds"] >= 0

    def test_health_has_totals(self, client):
        resp = client.get("/v1/health", headers=ADMIN_HEADERS)
        data = resp.json()["data"]
        assert "total_vectors" in data
        assert "total_collections" in data
        assert isinstance(data["total_vectors"], int)
        assert isinstance(data["total_collections"], int)

    def test_health_has_per_collection_breakdown(self, client):
        resp = client.get("/v1/health", headers=ADMIN_HEADERS)
        data = resp.json()["data"]
        assert "collections" in data
        assert isinstance(data["collections"], list)

    def test_health_collection_has_required_fields(self, client):
        resp = client.get("/v1/health", headers=ADMIN_HEADERS)
        collections = resp.json()["data"]["collections"]
        assert len(collections) > 0
        for col in collections:
            assert "name" in col
            assert "dim" in col
            assert "distance_metric" in col
            assert "vector_count" in col
            assert "index_size" in col

    def test_health_known_collection_appears(self, client):
        resp = client.get("/v1/health", headers=ADMIN_HEADERS)
        names = [c["name"] for c in resp.json()["data"]["collections"]]
        assert "health-test-col" in names

    def test_health_requires_auth(self, client, bad_headers):
        resp = client.get("/v1/health", headers=bad_headers)
        assert resp.status_code == 401

    def test_health_readonly_key_allowed(self, client):
        """readonly key can access /v1/health."""
        # Create a readonly key
        create = client.post(
            "/v1/admin/keys",
            json={"name": "health-ro", "role": "readonly"},
            headers=ADMIN_HEADERS,
        )
        ro_key = create.json()["data"]["key"]
        resp = client.get("/v1/health", headers={"x-api-key": ro_key})
        assert resp.status_code == 200


# ===========================================================================
# 4. MetricsMiddleware
# ===========================================================================

class TestMetricsMiddleware:
    def test_middleware_records_requests(self, client):
        """Every request increments vectordb_requests_total."""
        # Make a known request
        client.get("/v1/collections", headers=ADMIN_HEADERS)
        # Verify counter is in the metrics output
        resp = client.get("/metrics")
        assert "vectordb_requests_total" in resp.text

    def test_middleware_records_latency(self, client):
        client.post("/v1/collections", json={
            "name": "metrics-mw-col",
            "dim": 8,
        }, headers=ADMIN_HEADERS)
        resp = client.get("/metrics")
        assert "vectordb_request_duration_seconds_bucket" in resp.text

    def test_middleware_uses_route_template(self, client):
        """Endpoint label should use route template, not literal collection name."""
        client.get("/v1/collections/metrics-mw-col", headers=ADMIN_HEADERS)
        resp = client.get("/metrics")
        # Route template should appear, not the literal collection name
        assert "/v1/collections/{name}" in resp.text


# ===========================================================================
# 5. OpenTelemetry (disabled by default)
# ===========================================================================

class TestOpenTelemetry:
    def test_otel_disabled_by_default(self):
        """OTEL_ENABLED defaults to False — tracing setup must be a no-op."""
        from vectordb.config import get_settings
        from vectordb.tracing import setup_tracing
        from vectordb.models.db import ENGINE

        settings = get_settings()
        assert settings.otel_enabled is False

        # Calling setup_tracing with otel_enabled=False must not raise
        from fastapi import FastAPI
        mini_app = FastAPI()
        setup_tracing(mini_app, ENGINE, settings)  # should not raise

    def test_otel_settings_exist(self):
        """Config must expose all required OTel settings."""
        from vectordb.config import get_settings
        s = get_settings()
        assert hasattr(s, "otel_enabled")
        assert hasattr(s, "otel_service_name")
        assert hasattr(s, "otel_endpoint")
        assert s.otel_service_name == "vector-db"
        assert s.otel_endpoint == ""

    def test_logging_config_callable(self):
        """configure_logging must not raise for both formats."""
        from vectordb.logging_config import configure_logging
        configure_logging(log_format="json", log_level="INFO")
        configure_logging(log_format="console", log_level="WARNING")
