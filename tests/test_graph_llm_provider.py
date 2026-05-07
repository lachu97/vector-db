"""Tests for flexible GraphRAG LLM provider — config, encryption, extraction, endpoints."""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGraphEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        """Encrypt then decrypt returns original dict."""
        from vectordb.services.graph_encryption import encrypt_api_keys, decrypt_api_keys
        key_hex = "a" * 64
        original = {"api_key": "sk-secret", "GEMINI_API_KEY": "gm-secret"}
        blob = encrypt_api_keys(original, key_hex)
        assert isinstance(blob, str)
        assert "sk-secret" not in blob
        result = decrypt_api_keys(blob, key_hex)
        assert result == original

    def test_encrypt_empty_dict(self):
        """Empty dict encrypts and decrypts cleanly."""
        from vectordb.services.graph_encryption import encrypt_api_keys, decrypt_api_keys
        key_hex = "b" * 64
        blob = encrypt_api_keys({}, key_hex)
        assert decrypt_api_keys(blob, key_hex) == {}

    def test_no_encryption_key_stores_plaintext(self):
        """When encryption key is empty, returns raw JSON (plaintext fallback)."""
        from vectordb.services.graph_encryption import encrypt_api_keys, decrypt_api_keys
        keys = {"api_key": "sk-plain"}
        blob = encrypt_api_keys(keys, encryption_key="")
        assert json.loads(blob) == keys
        assert decrypt_api_keys(blob, encryption_key="") == keys

    def test_wrong_key_raises(self):
        """Decrypting with wrong key raises an exception."""
        from vectordb.services.graph_encryption import encrypt_api_keys, decrypt_api_keys
        blob = encrypt_api_keys({"api_key": "secret"}, "a" * 64)
        with pytest.raises(Exception):
            decrypt_api_keys(blob, "b" * 64)


class TestLLMExtractLiteLLM:
    def test_llm_extract_no_model_returns_empty(self):
        """Empty model string returns empty lists immediately."""
        from vectordb.services.graph_extraction import llm_extract
        entities, edges = asyncio.run(llm_extract("Some text.", model="", api_keys={}))
        assert entities == []
        assert edges == []

    def test_llm_extract_none_model_returns_empty(self):
        """None model returns empty lists."""
        from vectordb.services.graph_extraction import llm_extract
        entities, edges = asyncio.run(llm_extract("Some text.", model=None, api_keys={}))
        assert entities == []
        assert edges == []

    def test_llm_extract_calls_litellm_with_model(self):
        """llm_extract passes model string and api_key to litellm.acompletion."""
        from vectordb.services.graph_extraction import llm_extract

        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"entities": [{"entity_text": "Apple", "entity_type": "ORG"}], "edges": []}'

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            entities, edges = asyncio.run(llm_extract(
                "Apple makes iPhones.",
                model="gpt-4o-mini",
                api_keys={"api_key": "sk-test"},
            ))

        mock_call.assert_called_once()
        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["api_key"] == "sk-test"
        assert len(entities) == 1
        assert entities[0]["entity_text"] == "Apple"
        assert edges == []

    def test_llm_extract_ollama_no_api_key(self):
        """Ollama model string passes no api_key kwarg."""
        from vectordb.services.graph_extraction import llm_extract

        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"entities": [], "edges": []}'

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            asyncio.run(llm_extract("text", model="ollama/llama3.2", api_keys={}))

        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs.get("api_key") is None

    def test_llm_extract_malformed_json_returns_empty(self):
        """Model returns non-JSON → empty lists, no exception."""
        from vectordb.services.graph_extraction import llm_extract

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Sure! Here are the entities..."

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            entities, edges = asyncio.run(llm_extract("text", model="gpt-4o-mini", api_keys={}))

        assert entities == []
        assert edges == []

    def test_llm_extract_exception_returns_empty(self):
        """LiteLLM raises → empty lists, no exception propagated."""
        from vectordb.services.graph_extraction import llm_extract

        with patch("litellm.acompletion", new=AsyncMock(side_effect=Exception("AuthenticationError"))):
            entities, edges = asyncio.run(llm_extract("text", model="gpt-4o-mini", api_keys={"api_key": "bad"}))

        assert entities == []
        assert edges == []

    def test_resolve_api_key_openai(self):
        """OpenAI model resolves OPENAI_API_KEY from dict."""
        from vectordb.services.graph_extraction import _resolve_api_key
        keys = {"OPENAI_API_KEY": "sk-open", "GEMINI_API_KEY": "gm-key"}
        assert _resolve_api_key("gpt-4o-mini", keys) == "sk-open"

    def test_resolve_api_key_gemini(self):
        """Gemini model resolves GEMINI_API_KEY from dict."""
        from vectordb.services.graph_extraction import _resolve_api_key
        keys = {"OPENAI_API_KEY": "sk-open", "GEMINI_API_KEY": "gm-key"}
        assert _resolve_api_key("gemini/gemini-1.5-flash", keys) == "gm-key"

    def test_resolve_api_key_anthropic(self):
        """Anthropic model resolves ANTHROPIC_API_KEY from dict."""
        from vectordb.services.graph_extraction import _resolve_api_key
        keys = {"ANTHROPIC_API_KEY": "sk-ant"}
        assert _resolve_api_key("anthropic/claude-haiku-4-5", keys) == "sk-ant"

    def test_resolve_api_key_ollama_returns_none(self):
        """Ollama model returns None (no key needed)."""
        from vectordb.services.graph_extraction import _resolve_api_key
        assert _resolve_api_key("ollama/llama3.2", {"OPENAI_API_KEY": "sk"}) is None

    def test_resolve_api_key_direct_override(self):
        """api_key in dict takes precedence over provider-specific keys."""
        from vectordb.services.graph_extraction import _resolve_api_key
        keys = {"api_key": "direct-key", "OPENAI_API_KEY": "sk-other"}
        assert _resolve_api_key("gpt-4o-mini", keys) == "direct-key"


class TestGraphSchemas:
    def test_graph_config_request_schema(self):
        """GraphConfigRequest accepts model and api_keys."""
        from vectordb.models.schemas import GraphConfigRequest
        r = GraphConfigRequest(model="ollama/llama3.2", api_keys={"api_key": "x"})
        assert r.model == "ollama/llama3.2"
        assert r.api_keys == {"api_key": "x"}

    def test_graph_config_request_all_optional(self):
        """GraphConfigRequest works with no fields (partial update)."""
        from vectordb.models.schemas import GraphConfigRequest
        r = GraphConfigRequest()
        assert r.model is None
        assert r.api_keys is None

    def test_test_model_request_schema(self):
        """TestModelRequest requires model and text."""
        from vectordb.models.schemas import TestModelRequest
        r = TestModelRequest(model="gpt-4o-mini", text="Apple acquired Beats.")
        assert r.model == "gpt-4o-mini"
        assert r.api_keys == {}

    def test_benchmark_request_max_models(self):
        """BenchmarkRequest rejects more than 5 models."""
        from vectordb.models.schemas import BenchmarkRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            BenchmarkRequest(models=["m1", "m2", "m3", "m4", "m5", "m6"], text="text")


class TestGraphConfigEndpoint:
    def test_patch_graph_config_sets_model(self, client):
        """PATCH /graph/config stores model on collection."""
        client.post("/v1/collections", json={"name": "cfg-test", "dim": 4}, headers={"x-api-key": "test-key"})
        resp = client.patch(
            "/v1/collections/cfg-test/graph/config",
            json={"model": "ollama/llama3.2"},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["model"] == "ollama/llama3.2"
        assert data["api_keys_set"] is False

    def test_patch_graph_config_sets_api_keys(self, client):
        """PATCH /graph/config encrypts and stores api_keys."""
        client.post("/v1/collections", json={"name": "cfg-keys", "dim": 4}, headers={"x-api-key": "test-key"})
        resp = client.patch(
            "/v1/collections/cfg-keys/graph/config",
            json={"model": "gpt-4o-mini", "api_keys": {"OPENAI_API_KEY": "sk-test"}},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["api_keys_set"] is True

    def test_patch_graph_config_404_on_unknown_collection(self, client):
        """Returns error for unknown collection."""
        resp = client.patch(
            "/v1/collections/no-such/graph/config",
            json={"model": "gpt-4o-mini"},
            headers={"x-api-key": "test-key"},
        )
        assert resp.json()["error"]["code"] == 404


class TestConfig:
    def test_new_graph_config_fields_present(self):
        """Config has encryption key and provider key fields; old ollama vars removed."""
        from vectordb.config import Settings
        s = Settings(
            _env_file=None,
            graph_encryption_key="",
            openai_api_key="sk-test",
            gemini_api_key="gem-test",
            anthropic_api_key="ant-test",
        )
        assert hasattr(s, "graph_encryption_key")
        assert hasattr(s, "gemini_api_key")
        assert hasattr(s, "anthropic_api_key")
        assert not hasattr(s, "graph_llm_provider")
        assert not hasattr(s, "graph_ollama_base_url")
        assert not hasattr(s, "graph_ollama_model")
        assert s.graph_extraction_model == "gpt-4o-mini"  # default preserved
