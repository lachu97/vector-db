# Phase 7: Cloud & Managed Service — Fly.io Plan

## Why Fly.io?

Fly.io gives you most of what Kubernetes offers — auto-restart, scaling, load balancing, TLS, multi-region — without needing to learn K8s. You deploy with `fly deploy` (like `docker compose up` but in the cloud).

| Feature | Fly.io | Kubernetes |
|---------|--------|-----------|
| Deploy command | `fly deploy` | `helm upgrade` + 20 YAML files |
| Auto TLS/SSL | Built-in, free | You configure Ingress + cert-manager |
| Load balancing | Built-in | You configure Services + Ingress |
| Auto-restart on crash | Built-in | Built-in |
| Scaling | `fly scale count 3` | Edit Deployment replicas + HPA |
| Managed Postgres | `fly postgres create` | You manage StatefulSet or pay for RDS |
| Learning curve | Low (just a CLI) | High (weeks to learn) |
| Cost to start | ~$10-20/mo | ~$70-150/mo |
| When to outgrow | 100+ machines, complex networking | N/A (it's the destination) |

**Bottom line:** Start on Fly.io now, migrate to K8s only if/when you outgrow it (likely not for a long time).

---

## Architecture on Fly.io

```
Internet
   |
   +--> api.yourvectordb.com -----> [Fly Machine: vectordb-api] x2
   |                                        |
   +--> app.yourvectordb.com -----> [Fly Machine: vectordb-web] x1
                                            |
                              +-------------+-------------+
                              |                           |
                     [Fly Postgres cluster]        [Fly Redis (Upstash)]
                      (automatic failover)          (managed, free tier)
```

### Fly.io Concepts You Need

| Concept | What It Is | VectorDB Usage |
|---------|-----------|---------------|
| **Machine** | A lightweight VM running your Docker image. Like a container but with its own IP. | One instance of your API |
| **App** | A group of machines behind one hostname. Fly load-balances across them. | `vectordb-api` app, `vectordb-web` app |
| **fly.toml** | Config file (like docker-compose.yml). Defines how to build, run, scale, health-check. | One per app |
| **Volume** | Persistent disk attached to a machine. Survives restarts. | Only needed if using SQLite (not for Postgres backend) |
| **Secrets** | Encrypted env vars. Set via `fly secrets set DB_URL=...` | Database URL, Redis URL, API key |
| **Regions** | Fly runs your app in specific data centers worldwide. | Start with one region (e.g., `iad` for US East) |

---

## Cost Breakdown

### Starter (handles free + early pro tiers)

| Component | Spec | Cost |
|-----------|------|------|
| API machines (2x) | shared-cpu-1x, 512MB RAM | ~$7/mo total |
| Web machine (1x) | shared-cpu-1x, 256MB RAM | ~$3/mo |
| Fly Postgres | 1 shared-cpu, 1GB RAM, 10GB disk | ~$7/mo |
| Upstash Redis (Fly addon) | Free tier (10k cmds/day) | $0 |
| **Total** | | **~$17/mo** |

### Growth (50+ users, pro tiers)

| Component | Spec | Cost |
|-----------|------|------|
| API machines (3x) | shared-cpu-2x, 1GB RAM | ~$20/mo |
| Web machine (1x) | shared-cpu-1x, 512MB RAM | ~$4/mo |
| Fly Postgres | 1 dedicated-cpu, 2GB RAM, 20GB disk | ~$30/mo |
| Upstash Redis | Pay-as-you-go ($0.2/100k cmds) | ~$5/mo |
| **Total** | | **~$59/mo** |

### Scale (500+ users)

| Component | Spec | Cost |
|-----------|------|------|
| API machines (5x) | dedicated-cpu-2x, 4GB RAM | ~$150/mo |
| Web machine (2x) | shared-cpu-2x, 1GB RAM | ~$14/mo |
| Fly Postgres (HA) | 2 nodes, dedicated-cpu, 4GB, 50GB disk | ~$100/mo |
| Upstash Redis Pro | | ~$10/mo |
| **Total** | | **~$274/mo** |

---

## Sub-Phases and Timeline

### Sub-Phase 7.1: Deploy to Fly.io (Week 1)

**Goal:** Get the API + Postgres + Redis running on Fly.io.

**Steps:**
1. Install Fly CLI: `curl -L https://fly.io/install.sh | sh`
2. Login: `fly auth login`
3. Create Postgres: `fly postgres create --name vectordb-db --region iad`
4. Create Redis (Upstash): `fly redis create --name vectordb-redis --region iad`
5. Create API app: `fly launch` (generates `fly.toml`)
6. Set secrets: `fly secrets set DB_URL=... REDIS_URL=... API_KEY=...`
7. Deploy: `fly deploy`
8. Attach custom domain + auto-TLS

**Files to create:**
| File | Purpose |
|------|---------|
| `fly.toml` | API app config — build, env, services, health checks, scaling |
| `Dockerfile` (modify) | Multi-stage build for smaller image |
| `.dockerignore` (modify) | Exclude tests, docs, SDKs from image |

**`fly.toml` will look like:**
```toml
app = "vectordb-api"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile"

[env]
  STORAGE_BACKEND = "postgres"
  LOG_FORMAT = "json"
  WORKERS = "2"
  PORT = "8000"
  EMBEDDING_PROVIDER = "sentence-transformers"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 1

  [http_service.concurrency]
    type = "requests"
    hard_limit = 250
    soft_limit = 200

[[http_service.checks]]
  grace_period = "10s"
  interval = "30s"
  method = "GET"
  timeout = "5s"
  path = "/v1/health"
  headers = {"x-api-key" = "your-bootstrap-key"}

[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"
  count = 2
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
| `vectordb/tiers.py` (new) | `TIER_LIMITS` dict |
| `vectordb/services/usage_service.py` (new) | Track per-tenant usage |
| `vectordb/routers/billing.py` (new) | `GET /v1/usage`, `GET /v1/plan` |
| `vectordb/models/db.py` (modify) | Add `tier` to User, `TenantUsage` model |
| `vectordb/auth.py` (modify) | Include `tier` in `ApiKeyInfo` |
| `vectordb/middleware.py` (modify) | Per-tier rate limits instead of global |

**Implementation:**
1. Add `tier` column to `User` (default: `"free"`)
2. Create `TIER_LIMITS` dict
3. Modify rate limiter to use per-tier RPM
4. Add pre-write checks in routers (collection count, vector count at limit?)
5. Add `TenantUsage` table — monthly counters for API calls, vectors, storage
6. Expose `GET /v1/usage` and `GET /v1/plan`
7. Start with manual tier assignment via admin endpoint; add Stripe later

### Sub-Phase 7.3: CI/CD Pipeline (Week 4)

**Goal:** Push to `main` auto-deploys.

Fly.io has native GitHub Actions integration. The pipeline:

```
Push to main → Run tests → Build + Deploy to staging
Tag v*.*.* → Run tests → Build + Deploy to production
```

**File: `.github/workflows/fly-deploy.yml`**
```yaml
name: Deploy to Fly.io
on:
  push:
    branches: [main]
    tags: ['v*']

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

  deploy-staging:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --app vectordb-api-staging
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}

  deploy-production:
    needs: test
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --app vectordb-api
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

**GitHub Secrets needed:**
| Secret | How to get |
|--------|-----------|
| `FLY_API_TOKEN` | `fly tokens create deploy -x 999999h` |

### Sub-Phase 7.4: Backup & DR (Week 5)

**Goal:** Automated backups with tested restore.

**Fly Postgres handles most of this:**
- Automatic daily snapshots (retained 7 days)
- WAL-based point-in-time recovery
- `fly postgres backup list` to see backups
- `fly postgres backup restore` to restore

**For extra safety (off-platform backup):**
- Weekly `pg_dump` to an S3 bucket via GitHub Actions scheduled workflow
- Retained 30 days

**File: `.github/workflows/backup.yml`**
```yaml
name: Weekly Database Backup
on:
  schedule:
    - cron: '0 3 * * 0'  # Sunday 3am UTC
  workflow_dispatch:       # manual trigger

jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - name: Install Fly CLI
        uses: superfly/flyctl-actions/setup-flyctl@master
      - name: Create backup
        run: |
          flyctl ssh console --app vectordb-db -C "pg_dump -Fc -U postgres vectordb" > backup.dump
          aws s3 cp backup.dump s3://vectordb-backups/$(date +%Y-%m-%d).dump
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
```

**Recovery scenarios on Fly:**

| Scenario | What happens | Recovery |
|----------|-------------|---------|
| Machine crash | Fly auto-restarts it in ~5 seconds | Automatic |
| Bad deploy | `fly releases rollback` | One command, <1 min |
| Postgres data loss | `fly postgres backup restore` | 5-15 min |
| Total Fly outage | Restore pg_dump to any Postgres instance | 30 min |

### Sub-Phase 7.5: Tenant Isolation (Week 6)

**Already done:**
- User-scoped collections + API keys (multi-tenancy)
- Rate limiting (global)

**Still needed:**
| What | How | Priority |
|------|-----|----------|
| Per-tier rate limits | Modify `middleware.py` to read `tier` from `ApiKeyInfo` | High |
| Per-tier query timeouts | Set `statement_timeout` per tier on DB connections | Medium |
| Per-tier connection pool | Limit concurrent DB connections per tier | Medium |
| Resource isolation | Fly machines already isolated (each is a microVM) | Done by default |

### Sub-Phase 7.6: Frontend Deploy (Week 6)

Deploy the dashboard (vector-db-web) as a separate Fly app:

```bash
cd vector-db-web
fly launch --name vectordb-web
fly deploy
```

**File: `vector-db-web/fly.toml`**
```toml
app = "vectordb-web"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile"

[env]
  NEXT_PUBLIC_API_URL = "https://vectordb-api.fly.dev"

[http_service]
  internal_port = 3000
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 1

[[vm]]
  size = "shared-cpu-1x"
  memory = "256mb"
```

---

## Files Summary

### New Files

| File | Purpose |
|------|---------|
| `fly.toml` | Fly.io API app config |
| `vectordb/tiers.py` | Tier definitions + limits |
| `vectordb/services/usage_service.py` | Per-tenant usage tracking |
| `vectordb/routers/billing.py` | `GET /v1/usage`, `GET /v1/plan` endpoints |
| `.github/workflows/fly-deploy.yml` | CI/CD: test -> deploy |
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

## Scaling Strategy on Fly.io

### Day 1 (0-50 users): ~$17/mo
```bash
fly scale count 2 --app vectordb-api           # 2 API machines
fly scale vm shared-cpu-1x --memory 512        # 512MB each
```

### Growth (50-500 users): ~$59/mo
```bash
fly scale count 3 --app vectordb-api
fly scale vm shared-cpu-2x --memory 1024
fly postgres update --app vectordb-db          # upgrade Postgres
```

### Scale (500+ users): ~$274/mo
```bash
fly scale count 5 --app vectordb-api
fly scale vm dedicated-cpu-2x --memory 4096
# Add multi-region
fly regions add lhr sin --app vectordb-api     # London + Singapore
```

### When to leave Fly.io for K8s
- You need 50+ machines
- You need custom networking (VPN, VPC peering)
- Enterprise customers require specific cloud certifications
- You need GPUs for embedding (Fly doesn't support GPUs yet)

Until then, Fly.io handles everything.

---

## Quick Start (This Weekend)

```bash
# 1. Install Fly CLI
curl -L https://fly.io/install.sh | sh
fly auth login

# 2. Create Postgres
fly postgres create --name vectordb-db --region iad --vm-size shared-cpu-1x

# 3. Create Redis (Upstash)
fly redis create --name vectordb-redis --region iad --no-eviction

# 4. Launch the API
cd vector-db-mvp
fly launch --name vectordb-api --region iad --no-deploy

# 5. Attach Postgres + set secrets
fly postgres attach vectordb-db --app vectordb-api
fly secrets set \
  STORAGE_BACKEND=postgres \
  EMBEDDING_PROVIDER=sentence-transformers \
  API_KEY=your-secure-bootstrap-key \
  --app vectordb-api

# 6. Deploy
fly deploy

# 7. Check it's running
curl https://vectordb-api.fly.dev/v1/health -H "x-api-key: your-key"

# 8. Scale to 2 machines
fly scale count 2 --app vectordb-api
```

**Total time: ~30 minutes. Total cost: ~$17/month.**
