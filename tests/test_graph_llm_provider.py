"""Tests for flexible GraphRAG LLM provider — config, encryption, extraction, endpoints."""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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
