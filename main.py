# main.py — Entrypoint
# Import the app from the vectordb package. Gunicorn/Uvicorn uses main:app.
from vectordb.app import app  # noqa: F401
