# tests/test_phase6_cli.py
"""
Phase 6: CLI tests.

All tests use Click's CliRunner with a mocked VectorDBClient so no server
is needed. Tests verify:
- Correct commands are dispatched
- Arguments and options are parsed correctly
- Table and JSON output modes produce expected content
- Errors surface cleanly with a non-zero exit code
"""
from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from vectordb_client.cli.main import cli
from vectordb_client.exceptions import NotFoundError, AlreadyExistsError, VectorDBError
from vectordb_client.models import (
    Collection,
    UpsertResult,
    BulkUpsertResult,
    SearchResult,
    VectorResult,
    HealthStats,
)

BASE_ARGS = ["--api-key", "test-key"]


def _run(*args, output="table", input=None):
    """Invoke the CLI with BASE_ARGS prepended.
    Pass output= to set --output before the subcommand (required by Click)."""
    runner = CliRunner()
    return runner.invoke(
        cli, [*BASE_ARGS, "-o", output, *args], catch_exceptions=False, input=input
    )


def _make_collection(**kwargs):
    defaults = dict(name="col", dim=8, distance_metric="cosine", vector_count=0)
    defaults.update(kwargs)
    return Collection(**defaults)


def _make_search_result(n=2):
    results = [VectorResult(f"v{i}", round(0.9 - i * 0.05, 4), {"tag": f"t{i}"}) for i in range(n)]
    return SearchResult(results=results, collection="col", k=n)


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------

class TestCLIHealth:
    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_health_table(self, MockClient):
        h = HealthStats(
            status="ok",
            total_vectors=42,
            total_collections=3,
            collections=[{"name": "a", "vector_count": 10, "dim": 8}],
            uptime_seconds=99.5,
        )
        MockClient.return_value.observability.health.return_value = h

        result = _run("health")
        assert result.exit_code == 0
        assert "OK" in result.output
        assert "42" in result.output
        assert "99.5" in result.output

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_health_json(self, MockClient):
        h = HealthStats(
            status="ok",
            total_vectors=5,
            total_collections=1,
            collections=[],
            uptime_seconds=10.0,
        )
        MockClient.return_value.observability.health.return_value = h

        result = _run("health", output="json")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["total_vectors"] == 5

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_health_error_exits_1(self, MockClient):
        MockClient.return_value.observability.health.side_effect = VectorDBError("server error")

        runner = CliRunner()
        result = runner.invoke(cli, [*BASE_ARGS, "health"])
        assert result.exit_code == 1
        assert "Error" in result.output


# ---------------------------------------------------------------------------
# ping
# ---------------------------------------------------------------------------

class TestCLIPing:
    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_ping_success(self, MockClient):
        MockClient.return_value.ping.return_value = True
        result = _run("ping")
        assert result.exit_code == 0
        assert "OK" in result.output

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_ping_failure(self, MockClient):
        MockClient.return_value.ping.return_value = False
        runner = CliRunner()
        result = runner.invoke(cli, [*BASE_ARGS, "ping"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# collections
# ---------------------------------------------------------------------------

class TestCLICollections:
    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_list_table(self, MockClient):
        MockClient.return_value.collections.list.return_value = [
            _make_collection(name="a", dim=8, distance_metric="cosine", vector_count=10),
            _make_collection(name="b", dim=128, distance_metric="l2", vector_count=5),
        ]
        result = _run("collections", "list")
        assert result.exit_code == 0
        assert "a" in result.output
        assert "b" in result.output
        assert "128" in result.output

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_list_json(self, MockClient):
        MockClient.return_value.collections.list.return_value = [
            _make_collection(name="col1", dim=8, distance_metric="l2", vector_count=3),
        ]
        result = _run("collections", "list", output="json")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["name"] == "col1"

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_list_empty(self, MockClient):
        MockClient.return_value.collections.list.return_value = []
        result = _run("collections", "list")
        assert result.exit_code == 0
        assert "No collections" in result.output

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_create_table(self, MockClient):
        MockClient.return_value.collections.create.return_value = _make_collection(
            name="new-col", dim=32, distance_metric="l2"
        )
        result = _run("collections", "create", "new-col", "--dim", "32", "--metric", "l2")
        assert result.exit_code == 0
        assert "new-col" in result.output
        assert "32" in result.output

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_create_requires_dim(self, MockClient):
        result = _run("collections", "create", "col-without-dim")
        assert result.exit_code != 0

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_create_already_exists_error(self, MockClient):
        MockClient.return_value.collections.create.side_effect = AlreadyExistsError("exists")
        runner = CliRunner()
        result = runner.invoke(cli, [*BASE_ARGS, "collections", "create", "dup", "--dim", "8"])
        assert result.exit_code == 1
        assert "Error" in result.output

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_get_table(self, MockClient):
        MockClient.return_value.collections.get.return_value = _make_collection(
            name="my-col", dim=64, distance_metric="ip", vector_count=7
        )
        result = _run("collections", "get", "my-col")
        assert result.exit_code == 0
        assert "my-col" in result.output
        assert "64" in result.output
        assert "ip" in result.output

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_get_not_found_error(self, MockClient):
        MockClient.return_value.collections.get.side_effect = NotFoundError("not found")
        runner = CliRunner()
        result = runner.invoke(cli, [*BASE_ARGS, "collections", "get", "missing"])
        assert result.exit_code == 1

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_delete_with_yes_flag(self, MockClient):
        MockClient.return_value.collections.delete.return_value = {"status": "deleted"}
        result = _run("collections", "delete", "col", "--yes")
        assert result.exit_code == 0
        assert "Deleted" in result.output
        MockClient.return_value.collections.delete.assert_called_once_with("col")

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_delete_prompts_without_yes(self, MockClient):
        MockClient.return_value.collections.delete.return_value = {"status": "deleted"}
        runner = CliRunner()
        # confirm with 'y'
        result = runner.invoke(
            cli, [*BASE_ARGS, "collections", "delete", "col"], input="y\n"
        )
        assert result.exit_code == 0

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_delete_aborts_on_no(self, MockClient):
        runner = CliRunner()
        result = runner.invoke(
            cli, [*BASE_ARGS, "collections", "delete", "col"], input="n\n"
        )
        assert result.exit_code != 0
        MockClient.return_value.collections.delete.assert_not_called()


# ---------------------------------------------------------------------------
# vectors
# ---------------------------------------------------------------------------

class TestCLIVectors:
    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_upsert_insert(self, MockClient):
        MockClient.return_value.vectors.upsert.return_value = UpsertResult("v1", "inserted")
        result = _run("vectors", "upsert", "col", "v1", "[0.1, 0.2, 0.3]")
        assert result.exit_code == 0
        assert "inserted" in result.output

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_upsert_update(self, MockClient):
        MockClient.return_value.vectors.upsert.return_value = UpsertResult("v1", "updated")
        result = _run("vectors", "upsert", "col", "v1", "[0.1, 0.2]")
        assert result.exit_code == 0
        assert "updated" in result.output

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_upsert_with_metadata(self, MockClient):
        MockClient.return_value.vectors.upsert.return_value = UpsertResult("v1", "inserted")
        result = _run("vectors", "upsert", "col", "v1", "[0.1]", "--metadata", '{"tag": "a"}')
        assert result.exit_code == 0
        _, call_kwargs = MockClient.return_value.vectors.upsert.call_args
        assert call_kwargs.get("metadata") == {"tag": "a"} or \
               MockClient.return_value.vectors.upsert.call_args[0][3] == {"tag": "a"}

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_upsert_bad_vector_json(self, MockClient):
        result = _run("vectors", "upsert", "col", "v1", "not-json")
        assert result.exit_code != 0

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_upsert_vector_not_list(self, MockClient):
        result = _run("vectors", "upsert", "col", "v1", '{"key": 1}')
        assert result.exit_code != 0

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_upsert_vector_from_file(self, MockClient):
        MockClient.return_value.vectors.upsert.return_value = UpsertResult("v1", "inserted")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([0.1, 0.2, 0.3], f)
            path = f.name
        try:
            result = _run("vectors", "upsert", "col", "v1", f"@{path}")
            assert result.exit_code == 0
        finally:
            os.unlink(path)

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_upsert_vector_file_not_found(self, MockClient):
        result = _run("vectors", "upsert", "col", "v1", "@/nonexistent/file.json")
        assert result.exit_code != 0

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_delete_single(self, MockClient):
        MockClient.return_value.vectors.delete.return_value = {"status": "deleted"}
        result = _run("vectors", "delete", "col", "v1")
        assert result.exit_code == 0
        assert "v1" in result.output

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_delete_batch(self, MockClient):
        MockClient.return_value.vectors.delete_batch.return_value = {
            "deleted_count": 3,
            "not_found": [],
        }
        result = _run("vectors", "delete-batch", "col", "v1", "v2", "v3")
        assert result.exit_code == 0
        assert "3" in result.output

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_delete_batch_partial_not_found(self, MockClient):
        MockClient.return_value.vectors.delete_batch.return_value = {
            "deleted_count": 1,
            "not_found": ["v2"],
        }
        result = _run("vectors", "delete-batch", "col", "v1", "v2")
        assert result.exit_code == 0
        assert "v2" in result.output  # not_found shows up

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_upsert_json_output(self, MockClient):
        MockClient.return_value.vectors.upsert.return_value = UpsertResult("v1", "inserted")
        result = _run("vectors", "upsert", "col", "v1", "[0.1]", output="json")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "inserted"
        assert data["external_id"] == "v1"


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

class TestCLISearch:
    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_search_table(self, MockClient):
        MockClient.return_value.search.search.return_value = _make_search_result(2)
        result = _run("search", "col", "[0.1, 0.2]", "--k", "2")
        assert result.exit_code == 0
        assert "v0" in result.output
        assert "v1" in result.output
        # Verify k was passed
        _, kwargs = MockClient.return_value.search.search.call_args
        assert kwargs.get("k") == 2 or MockClient.return_value.search.search.call_args[0][2] == 2

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_search_json(self, MockClient):
        MockClient.return_value.search.search.return_value = _make_search_result(1)
        result = _run("search", "col", "[0.1]", output="json")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["external_id"] == "v0"

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_search_no_results(self, MockClient):
        MockClient.return_value.search.search.return_value = SearchResult(
            results=[], collection="col", k=10
        )
        result = _run("search", "col", "[0.1]")
        assert result.exit_code == 0
        assert "No results" in result.output

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_search_with_filter(self, MockClient):
        MockClient.return_value.search.search.return_value = _make_search_result(1)
        result = _run("search", "col", "[0.1]", "--filter", "tag=foo")
        assert result.exit_code == 0
        call_args = MockClient.return_value.search.search.call_args
        filters = call_args[1].get("filters") or call_args[0][3]
        assert filters == {"tag": "foo"}

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_search_not_found_error(self, MockClient):
        MockClient.return_value.search.search.side_effect = NotFoundError("not found")
        runner = CliRunner()
        result = runner.invoke(cli, [*BASE_ARGS, "search", "missing", "[0.1]"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# recommend
# ---------------------------------------------------------------------------

class TestCLIRecommend:
    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_recommend_table(self, MockClient):
        MockClient.return_value.search.recommend.return_value = _make_search_result(3)
        result = _run("recommend", "col", "v0", "--k", "3")
        assert result.exit_code == 0
        assert "v1" in result.output
        MockClient.return_value.search.recommend.assert_called_once_with("col", "v0", k=3)

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_recommend_not_found(self, MockClient):
        MockClient.return_value.search.recommend.side_effect = NotFoundError("not found")
        runner = CliRunner()
        result = runner.invoke(cli, [*BASE_ARGS, "recommend", "col", "missing-id"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# similarity
# ---------------------------------------------------------------------------

class TestCLISimilarity:
    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_similarity_table(self, MockClient):
        MockClient.return_value.search.similarity.return_value = 0.97
        result = _run("similarity", "col", "v1", "v2")
        assert result.exit_code == 0
        assert "0.97" in result.output
        MockClient.return_value.search.similarity.assert_called_once_with("col", "v1", "v2")

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_similarity_json(self, MockClient):
        MockClient.return_value.search.similarity.return_value = 0.88
        result = _run("similarity", "col", "v1", "v2", output="json")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert abs(data["score"] - 0.88) < 0.001


# ---------------------------------------------------------------------------
# hybrid-search
# ---------------------------------------------------------------------------

class TestCLIHybridSearch:
    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_hybrid_search_table(self, MockClient):
        MockClient.return_value.search.hybrid_search.return_value = _make_search_result(2)
        result = _run("hybrid-search", "col", "hello world", "[0.1, 0.2]", "--alpha", "0.7")
        assert result.exit_code == 0
        assert "v0" in result.output
        call_args = MockClient.return_value.search.hybrid_search.call_args
        assert call_args[1].get("alpha") == 0.7 or call_args[0][4] == 0.7

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_hybrid_search_bad_alpha(self, MockClient):
        result = _run("hybrid-search", "col", "text", "[0.1]", "--alpha", "1.5")
        assert result.exit_code != 0

    @patch("vectordb_client.cli.main.VectorDBClient")
    def test_hybrid_search_json(self, MockClient):
        MockClient.return_value.search.hybrid_search.return_value = _make_search_result(1)
        result = _run("hybrid-search", "col", "query", "[0.1]", output="json")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1


# ---------------------------------------------------------------------------
# Global options and _parse_vector/_parse_metadata
# ---------------------------------------------------------------------------

class TestCLIGlobalOptions:
    def test_missing_api_key_fails(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["health"])
        assert result.exit_code != 0

    def test_api_key_from_env(self):
        runner = CliRunner()
        env = {"VECTORDB_API_KEY": "env-key"}
        with patch("vectordb_client.cli.main.VectorDBClient") as MockClient:
            h = HealthStats(
                status="ok", total_vectors=0, total_collections=0,
                collections=[], uptime_seconds=1.0
            )
            MockClient.return_value.observability.health.return_value = h
            result = runner.invoke(cli, ["health"], env=env)
        assert result.exit_code == 0
        MockClient.assert_called_once()
        _, kwargs = MockClient.call_args
        assert kwargs.get("api_key") == "env-key" or MockClient.call_args[0][1] == "env-key"

    def test_version_flag(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert "0.1.0" in result.output

    def test_help_flag(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "collections" in result.output


class TestCLIOutputFormatters:
    """Test _output.py directly for edge cases."""

    def test_table_with_many_columns(self):
        from vectordb_client.cli._output import print_collections
        import io, sys
        old = sys.stdout
        sys.stdout = io.StringIO()
        print_collections(
            [{"name": "a", "dim": 8, "distance_metric": "cosine", "vector_count": 0}],
            "table",
        )
        out = sys.stdout.getvalue()
        sys.stdout = old
        assert "a" in out
        assert "NAME" in out

    def test_json_output_is_valid(self):
        from vectordb_client.cli._output import print_search_results
        import io, sys
        old = sys.stdout
        sys.stdout = io.StringIO()
        print_search_results(
            [{"external_id": "v1", "score": 0.9, "metadata": {}}],
            "json",
        )
        out = sys.stdout.getvalue()
        sys.stdout = old
        data = json.loads(out)
        assert data[0]["external_id"] == "v1"

    def test_print_health_collections_table(self):
        from vectordb_client.cli._output import print_health
        import io, sys
        old = sys.stdout
        sys.stdout = io.StringIO()
        print_health(
            {
                "status": "ok",
                "uptime_seconds": 10,
                "total_collections": 1,
                "total_vectors": 5,
                "collections": [{"name": "c1", "vector_count": 5, "dim": 8}],
            },
            "table",
        )
        out = sys.stdout.getvalue()
        sys.stdout = old
        assert "c1" in out
