FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Build hnswlib from source — pre-built wheels use AVX2 which crashes under Rosetta/ARM
RUN pip install --no-cache-dir --no-binary hnswlib hnswlib
# Install remaining deps (torch pulls correct CPU-only wheel per arch automatically)
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m appuser
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    WORKERS=2 \
    OPENBLAS_CORETYPE=ARMV8 \
    OMP_NUM_THREADS=1

EXPOSE ${PORT}

CMD ["sh", "-c", "gunicorn main:app \
    --workers ${WORKERS} \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${PORT} \
    --log-level info \
    --timeout 120"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -f -H "x-api-key: ${API_KEY:-test-key}" http://localhost:${PORT}/v1/health || exit 1
