FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Pin numpy<2 — v2 uses ARM SVE / AVX-512 which crashes in Docker on Apple Silicon
RUN pip install --no-cache-dir "numpy<2.0"
# CPU-only torch — no AVX-512, works under Rosetta
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
# Build hnswlib from source — pre-built wheel uses AVX2 which crashes under Rosetta
RUN pip install --no-cache-dir --no-binary hnswlib hnswlib
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-download sentence-transformers model as root into a fixed path.
# Avoids runtime download inside gunicorn timeout + ensures appuser can read it.
ENV SENTENCE_TRANSFORMERS_HOME=/app/.st_cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

RUN useradd -m appuser && chown -R appuser:appuser /app/.st_cache
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    WORKERS=2 \
    SENTENCE_TRANSFORMERS_HOME=/app/.st_cache \
    OPENBLAS_CORETYPE=HASWELL \
    OPENBLAS_NUM_THREADS=1 \
    NPY_DISABLE_CPU_FEATURES="AVX512F AVX512CD AVX512_SKX AVX512_CLX AVX512_CNL AVX512_ICL"

EXPOSE ${PORT}

CMD ["sh", "-c", "gunicorn main:app \
    --workers ${WORKERS} \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${PORT} \
    --log-level info \
    --timeout 120"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -f -H "x-api-key: ${API_KEY:-test-key}" http://localhost:${PORT}/v1/health || exit 1
