# tests/conftest.py
import os
import tempfile
import shutil

import numpy as np
import pytest
from fastapi.testclient import TestClient

# Override settings BEFORE any vectordb imports
_tmpdir = tempfile.mkdtemp()
os.environ["DB_URL"] = f"sqlite:///{_tmpdir}/test_vectors.db"
os.environ["INDEX_PATH"] = os.path.join(_tmpdir, "test_index.bin")
os.environ["API_KEY"] = "test-key"
os.environ["VECTOR_DIM"] = "384"
os.environ["MAX_ELEMENTS"] = "1000"
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"  # effectively unlimited during tests
os.environ["EMBEDDING_PROVIDER"] = "dummy"  # no model download in tests

from vectordb.app import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    """TestClient that lasts the entire test session."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def headers():
    return {"x-api-key": "test-key"}


@pytest.fixture(scope="session")
def bad_headers():
    return {"x-api-key": "wrong-key"}


def random_vector(dim=384):
    """Generate a random float vector."""
    return np.random.rand(dim).tolist()


@pytest.fixture(scope="session", autouse=True)
def cleanup_tmpdir():
    """Clean up temp directory after all tests."""
    yield
    shutil.rmtree(_tmpdir, ignore_errors=True)
