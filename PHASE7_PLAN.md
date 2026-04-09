# Phase 7: Cloud & Managed Service — Render Plan

## Why Render?

Render is a PaaS that deploys straight from GitHub. Push to `main`, it builds and deploys automatically. No CLI needed, no YAML files, no K8s — just connect your repo and go.

| Feature | Render | Fly.io | Kubernetes |
|---------|--------|--------|-----------|
| Deploy | Git push (auto) | `fly deploy` | `helm upgrade` + YAML |
| Auto TLS | Built-in | Built-in | Manual (cert-manager) |
| Managed Postgres | Yes (free tier available) | Yes | No (you manage it) |
| Managed Redis | Yes (free tier available) | Via Upstash addon | No |
| Dashboard | Web UI | CLI-first | CLI + dashboards |
| Auto-deploy from GitHub | Native | Via GitHub Actions | Via GitHub Actions |
| Free tier | Yes (750 hrs/mo) | No | No |
| Learning curve | Very low | Low | High |
| Cost to start | **$0 (free tier)** | ~$17/mo | ~$70/mo |

**Bottom line:** Render is the simplest path. Connect repo, set env vars, done. Migrate to something heavier only when you outgrow it.

---

## Architecture on Render

```
Internet
   |
   +--> api.yourvectordb.com ------> [Web Service: vectordb-api]
   |                                          |
   +--> app.yourvectordb.com ------> [Static Site or Web Service: vectordb-web]
                                              |
                                +-------------+-------------+
                                |                           |
                       [Render Postgres]            [Render Redis]
                        (managed, auto-backup)       (managed, free tier)
```

### Render Concepts

| Concept | What It Is | VectorDB Usage |
|---------|-----------|---------------|
| **Web Service** | A long-running process serving HTTP. Built from a Dockerfile or buildpack. Auto-deployed on git push. | Your FastAPI API |
| **Static Site** | Pre-built frontend served from CDN. Free. | Next.js dashboard (if exported static) |
| **PostgreSQL** | Managed Postgres instance with automatic daily backups. Free tier: 256MB, 90-day expiry. | Production database with pgvector |
| **Redis** | Managed Redis. Free tier: 25MB. | Embedding + query cache |
| **Environment Groups** | Shared env vars across services. Set once, used by all. | `DB_URL`, `REDIS_URL` shared between API + workers |
| **Blueprints** | `render.yaml` — Infrastructure as Code. Defines all services in one file. | One-click deploy of entire stack |
| **Health Checks** | Render pings your app. If it fails, it restarts. | `GET /v1/health` |

---

## Cost Breakdown

### Starter — Free Tier (0-20 users)

| Component | Spec | Cost |
|-----------|------|------|
| API (Web Service) | Free tier, 512MB RAM, spins down after 15 min inactivity | $0 |
| Postgres | Free tier, 256MB, 1GB storage | $0 |
| Redis | Free tier, 25MB | $0 |
| Frontend (Static Site) | Free, CDN | $0 |
| **Total** | | **$0/mo** |

**Limitations:** Free tier spins down after inactivity (cold starts ~30-60s). Postgres expires after 90 days (must recreate or upgrade). Fine for development and early beta users.

### Growth — Paid Tier (20-500 users): ~$26/mo

| Component | Spec | Cost |
|-----------|------|------|
| API (Web Service) | Starter plan, 512MB RAM, always on | $7/mo |
| Postgres | Starter plan, 1GB RAM, 1GB storage, daily backups | $7/mo |
| Redis | Starter plan, 25MB, persistence | $5/mo |
| Frontend (Static Site) | Free | $0 |
| **Total** | | **~$19/mo** |

### Scale (500+ users): ~$85/mo

| Component | Spec | Cost |
|-----------|------|------|
| API (Web Service) | Standard plan, 2GB RAM | $25/mo |
| Postgres | Standard plan, 4GB RAM, 10GB storage, PITR | $45/mo |
| Redis | Standard plan, 100MB | $10/mo |
| Frontend (Static Site) | Free | $0 |
| Extra API instance | +1 instance for HA | $25/mo |
| **Total** | | **~$105/mo** |

---

## Sub-Phases and Timeline

### Sub-Phase 7.1: Deploy to Render (Week 1)

**Goal:** API + Postgres + Redis live on Render, auto-deploying from GitHub.

**Steps:**

1. **Create `render.yaml`** (Blueprint) at repo root — defines all services
2. **Go to Render Dashboard** → New → Blueprint → Connect GitHub repo
3. Render reads `render.yaml`, creates all services automatically
4. **Set secrets** in Render Dashboard (or via `render.yaml` `envVars`)
5. API is live at `vectordb-api.onrender.com` with auto-TLS
6. Attach custom domain later

**Files to create:**

| File | Purpose |
|------|---------|
| `render.yaml` | Blueprint — defines API service, Postgres, Redis |
| `Dockerfile` (modify) | Multi-stage build for smaller/faster image |
| `.dockerignore` (modify) | Exclude tests, docs, SDKs, .git |
| `scripts/migrate.sh` (new) | Run Alembic migrations on deploy |

**`render.yaml`:**
```yaml
databases:
  - name: vectordb-db
    plan: free       # upgrade to starter ($7/mo) for production
    databaseName: vectordb
    user: vectordb
    postgresSQLMajorVersion: "16"
    ipAllowList: []  # only internal access

services:
  - type: redis
    name: vectordb-redis
    plan: free       # upgrade to starter ($5/mo) for persistence
    ipAllowList: []

  - type: web
    name: vectordb-api
    runtime: docker
    plan: free       # upgrade to starter ($7/mo) to stay always-on
    region: ohio
    dockerfilePath: ./Dockerfile
    healthCheckPath: /
    envVars:
      - key: STORAGE_BACKEND
        value: postgres
      - key: EMBEDDING_PROVIDER
        value: sentence-transformers
      - key: LOG_FORMAT
        value: json
      - key: WORKERS
        value: "2"
      - key: PORT
        value: "8000"
      - key: DB_URL
        fromDatabase:
          name: vectordb-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          name: vectordb-redis
          type: redis
          property: connectionString
      - key: API_KEY
        generateValue: true   # Render generates a random value
```

**Dockerfile update (multi-stage):**
```dockerfile
# ---------- Builder ----------
FROM python:3.13-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- Runtime ----------
FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder /install /usr/local
COPY vectordb/ vectordb/
COPY main.py alembic.ini ./
COPY migrations/ migrations/

RUN useradd -m appuser
USER appuser

ENV PYTHONUNBUFFERED=1 PORT=8000 WORKERS=2

EXPOSE ${PORT}

# Run migrations then start server
CMD sh -c "python -m alembic upgrade head && \
    gunicorn main:app \
    --workers ${WORKERS} \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${PORT} \
    --log-level info \
    --timeout 120"
```

### Sub-Phase 7.2: Tier System (Weeks 2-3)

**Goal:** Enforce free/pro/scale limits at the application layer.

**Tier limits:**

| Limit | Free | Pro ($29/mo) | Scale ($99/mo) |
|-------|------|-------------|----------------|
| Collections | 3 | 25 | Unlimited |
| Vectors (total) | 10,000 | 500,000 | 5,000,000 |
| Max dimensions | 768 | 2,048 | 10,000 |
| API requests/min | 30 | 300 | 3,000 |
| Max batch size | 100 | 1,000 | 10,000 |
| Storage | 50MB | 5GB | 50GB |
| API keys per user | 2 | 10 | 50 |
| Backups | None | Daily | Hourly + PITR |

**Files to create/modify:**

| File | Change |
|------|--------|
| `vectordb/tiers.py` (new) | `TIER_LIMITS` dict with free/pro/scale definitions |
| `vectordb/services/usage_service.py` (new) | Track per-tenant usage (API calls, vectors, storage) |
| `vectordb/routers/billing.py` (new) | `GET /v1/usage`, `GET /v1/plan` endpoints |
| `vectordb/models/db.py` (modify) | Add `tier` to User, add `TenantUsage` model |
| `vectordb/auth.py` (modify) | Include `tier` in `ApiKeyInfo` |
| `vectordb/middleware.py` (modify) | Per-tier rate limits instead of global |
| `vectordb/app.py` (modify) | Register billing router |

**Implementation order:**
1. Add `tier` column to `User` model (default: `"free"`)
2. Create Alembic migration for the new column
3. Create `TIER_LIMITS` dict in `vectordb/tiers.py`
4. Modify `RateLimitMiddleware` to use per-tier RPM from `ApiKeyInfo`
5. Add pre-write checks in routers (collection count limit, vector count limit)
6. Add `TenantUsage` model + monthly aggregation
7. Create `GET /v1/usage` and `GET /v1/plan` endpoints
8. Manual tier assignment first; Stripe integration later

### Sub-Phase 7.3: CI/CD Pipeline (Week 4)

**Goal:** Auto-deploy on push to `main` with tests.

Render already auto-deploys on git push. We just need to add a test gate so broken code doesn't deploy.

**File: `.github/workflows/ci.yml`**
```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: vectordb_test
        ports: ['5432:5432']
        options: >-
          --health-cmd="pg_isready"
          --health-interval=10s
          --health-timeout=5s
          --health-retries=5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pytest tests/ -v --ignore=tests/test_phase6_cli.py --ignore=tests/test_phase6_python_sdk.py --ignore=tests/test_phase5.py
        env:
          EMBEDDING_PROVIDER: dummy
          API_KEY: test-key
```

**Deploy flow:**
```
PR opened → GitHub Actions runs tests
PR merged to main → GitHub Actions runs tests → Render auto-deploys
```

To prevent Render from deploying if tests fail, set the **Build Filter** in Render Dashboard to check the CI status, OR use Render's **Deploy Hook** triggered only after CI passes.

### Sub-Phase 7.4: Backup & DR (Week 5)

**Goal:** Automated backups with tested restore.

**Render Postgres backups (built-in):**
- **Free tier:** No backups (data can be lost on expire)
- **Starter ($7/mo):** Automatic daily backups, 7-day retention
- **Standard ($45/mo):** Automatic daily backups + point-in-time recovery (PITR)

**For extra safety — off-platform backup:**

Weekly `pg_dump` to an S3 bucket via GitHub Actions:

**File: `.github/workflows/backup.yml`**
```yaml
name: Weekly Database Backup
on:
  schedule:
    - cron: '0 3 * * 0'  # Sunday 3am UTC
  workflow_dispatch:

jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - name: Install PostgreSQL client
        run: sudo apt-get update && sudo apt-get install -y postgresql-client-16

      - name: Dump database
        run: pg_dump -Fc "$DB_URL" > backup.dump
        env:
          DB_URL: ${{ secrets.RENDER_DB_EXTERNAL_URL }}

      - name: Upload to S3
        uses: jakejarvis/s3-sync-action@master
        with:
          args: --include "backup.dump"
        env:
          AWS_S3_BUCKET: ${{ secrets.BACKUP_S3_BUCKET }}
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          SOURCE_DIR: '.'
          DEST_DIR: 'vectordb-backups/${{ github.run_id }}'
```

**Recovery scenarios:**

| Scenario | What happens | Recovery |
|----------|-------------|---------|
| API crash | Render auto-restarts | Automatic, ~10s |
| Bad deploy | Render → Manual Deploy → pick previous commit | 1-click, <2 min |
| Postgres issue | Restore from Render daily backup | Dashboard, 5-15 min |
| Need to migrate away | `pg_dump` from external URL, restore anywhere | 30 min |

### Sub-Phase 7.5: Tenant Isolation (Week 6)

**Already done:**
- User-scoped collections + API keys (multi-tenancy)
- Rate limiting (global)

**Still needed:**

| What | How | Priority |
|------|-----|----------|
| Per-tier rate limits | Modify `middleware.py` — read `tier` from `ApiKeyInfo` | High |
| Per-tier query timeouts | `statement_timeout` per tier on DB connections | Medium |
| Per-tier connection pool | Limit concurrent DB connections per tier | Medium |

Render provides process-level isolation by default (each web service runs in its own container). No extra work needed for compute isolation.

### Sub-Phase 7.6: Frontend Deploy (Week 6)

Deploy the dashboard as a separate Render service.

**Option A: Static Site (free, fastest)**
If `vector-db-web` can be exported as static (`next build && next export`):
- Render → New → Static Site → Connect `vector-db-web` repo
- Build command: `npm run build`
- Publish directory: `out/`
- Free, served from CDN

**Option B: Web Service (if SSR needed)**
- Render → New → Web Service → Connect repo
- Build command: `npm install && npm run build`
- Start command: `npm start`
- Starter plan: $7/mo

Add to `render.yaml`:
```yaml
  - type: web
    name: vectordb-web
    runtime: node
    plan: free
    buildCommand: npm install && npm run build
    startCommand: npm start
    envVars:
      - key: NEXT_PUBLIC_API_URL
        value: https://vectordb-api.onrender.com
```

---

## Complete `render.yaml` Blueprint

```yaml
databases:
  - name: vectordb-db
    plan: free
    databaseName: vectordb
    user: vectordb
    postgresSQLMajorVersion: "16"
    ipAllowList: []

services:
  - type: redis
    name: vectordb-redis
    plan: free
    maxmemoryPolicy: allkeys-lru
    ipAllowList: []

  - type: web
    name: vectordb-api
    runtime: docker
    plan: free
    region: ohio
    dockerfilePath: ./Dockerfile
    healthCheckPath: /
    autoDeploy: true
    envVars:
      - key: STORAGE_BACKEND
        value: postgres
      - key: EMBEDDING_PROVIDER
        value: sentence-transformers
      - key: LOG_FORMAT
        value: json
      - key: WORKERS
        value: "2"
      - key: PORT
        value: "8000"
      - key: DB_URL
        fromDatabase:
          name: vectordb-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          name: vectordb-redis
          type: redis
          property: connectionString
      - key: API_KEY
        generateValue: true
```

---

## Files Summary

### New Files

| File | Purpose |
|------|---------|
| `render.yaml` | Render Blueprint — one-click deploy of entire stack |
| `vectordb/tiers.py` | Tier definitions + limits (free/pro/scale) |
| `vectordb/services/usage_service.py` | Per-tenant usage tracking |
| `vectordb/routers/billing.py` | `GET /v1/usage`, `GET /v1/plan` endpoints |
| `.github/workflows/ci.yml` | Test on push/PR |
| `.github/workflows/backup.yml` | Weekly off-platform DB backup |

### Modified Files

| File | Change |
|------|--------|
| `Dockerfile` | Multi-stage build (builder + runtime) |
| `.dockerignore` | Exclude tests, docs, SDKs, .git |
| `vectordb/models/db.py` | Add `tier` to User, `TenantUsage` model |
| `vectordb/auth.py` | Include `tier` in `ApiKeyInfo` |
| `vectordb/middleware.py` | Per-tier rate limits |
| `vectordb/app.py` | Register billing router |

---

## Scaling on Render

### Day 1 (free tier, dev/beta): $0/mo
- Free web service (spins down on idle)
- Free Postgres (256MB, 90-day limit)
- Free Redis (25MB)
- Free static site for frontend

### Growth (paying users): ~$19/mo
- Starter web service ($7) — always on, no cold starts
- Starter Postgres ($7) — daily backups, no expiry
- Starter Redis ($5) — persistence

### Scale (500+ users): ~$105/mo
- Standard web service ($25) — 2GB RAM
- Standard Postgres ($45) — 4GB RAM, PITR
- Standard Redis ($10) — 100MB
- +1 API instance ($25) for high availability

### When to leave Render
- You need auto-scaling (Render doesn't auto-scale — you manually add instances)
- You need multi-region (Render is single-region per service)
- You need >10 instances of the same service
- Enterprise customers require VPC/private networking

At that point, move to Fly.io or Kubernetes. The app code doesn't change — just the deployment config.

---

## Quick Start (This Weekend)

### Option A: One-Click Blueprint (Easiest)

1. Push `render.yaml` to your repo
2. Go to https://dashboard.render.com → New → Blueprint
3. Connect your `lachu97/vector-db` GitHub repo
4. Render creates Postgres, Redis, and API automatically
5. API is live at `https://vectordb-api.onrender.com`
6. Set custom domain in Render Dashboard → auto-TLS

### Option B: Manual Setup

```
1. Render Dashboard → New PostgreSQL → name: vectordb-db → Create
2. Render Dashboard → New Redis → name: vectordb-redis → Create
3. Render Dashboard → New Web Service → Connect GitHub repo
   - Name: vectordb-api
   - Runtime: Docker
   - Add env vars:
     STORAGE_BACKEND=postgres
     EMBEDDING_PROVIDER=sentence-transformers
     DB_URL=(copy Internal Connection String from Postgres)
     REDIS_URL=(copy Internal Connection String from Redis)
     API_KEY=your-secure-key
   - Create Web Service
4. Wait for build + deploy (~3-5 min)
5. Visit https://vectordb-api.onrender.com/v1/health
```

**Total time: ~15 minutes. Total cost: $0.**
