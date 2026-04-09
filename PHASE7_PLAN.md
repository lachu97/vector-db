# Phase 7: Cloud & Managed Service — Implementation Plan

## Part 1: Kubernetes Explained (for a Docker User)

### What Is Kubernetes and Why Do You Need It?

You already know Docker: it packages your app into a container image and `docker compose up` runs everything on one machine. That works fine for local dev and even for a single production server. The problem comes when your managed service needs to:

- **Run multiple copies** of the API behind a load balancer
- **Automatically restart** crashed containers and move workloads to healthy machines
- **Scale up during traffic spikes** and scale down at night to save money
- **Roll out new versions** with zero downtime (one pod at a time, rolling update)
- **Isolate tenants** with resource limits (CPU, memory quotas per tier)
- **Manage secrets** (database passwords, API keys) without baking them into images
- **Persist data** (PostgreSQL volumes) reliably across container restarts

Kubernetes (K8s) is the orchestrator that handles all of this across a cluster of machines. Think of it as **"Docker Compose for production at scale."**

### Key Kubernetes Concepts

| Concept | What It Is | VectorDB Example |
|---------|-----------|-----------------|
| **Pod** | Smallest unit. Usually one container. Like a running Docker container, but managed by K8s. | One running instance of the VectorDB API |
| **Deployment** | Declares "I want N copies of this pod running." K8s keeps that promise. | `vectordb-api` Deployment with `replicas: 3` |
| **Service** | A stable internal DNS name + load balancer in front of pods. | `vectordb-api-service` so other pods reach `http://vectordb-api-service:8000` |
| **Ingress** | Routes external HTTP traffic to Services inside the cluster. Handles TLS/SSL. | `api.yourvectordb.com` -> API Service |
| **Namespace** | A virtual cluster boundary. Groups resources and applies policies. | `vectordb-prod`, `vectordb-staging` |
| **PVC** | Persistent Volume Claim. Disk storage that survives pod restarts. | PostgreSQL data directory |
| **ConfigMap** | Key-value config injected as env vars. Not secret. | `STORAGE_BACKEND=postgres`, `LOG_FORMAT=json` |
| **Secret** | Like ConfigMap but encrypted at rest. For sensitive values. | Database password, Redis password |
| **HPA** | Horizontal Pod Autoscaler. Watches CPU/memory and auto-scales replicas. | "If API pods avg >70% CPU, add more (up to 10)" |
| **Helm Chart** | Package manager for K8s. Bundles all YAML into a reusable template. | `helm install vectordb` deploys everything |

### The Mental Model

```
Internet
   |
   v
[Ingress] -- routes by hostname/path
   |
   +---> [Service: vectordb-api] --> [Pod] [Pod] [Pod]  (FastAPI app)
   |
   +---> [Service: vectordb-web] --> [Pod]               (Next.js dashboard)
   
Internal only (no Ingress):
   [Service: postgresql] --> [Pod + PVC]                  (database)
   [Service: redis]      --> [Pod]                        (cache)
```

---

## Part 2: Sub-Phases and Milestones

### Sub-Phase 7.1: Production-Ready Docker (Weeks 1-2)

**Goal:** Deploy to a single cloud VM with proper config, before touching K8s.

**Why:** You can start serving paid customers on a $20/month VM while building K8s in parallel.

- Multi-stage Dockerfile (build + slim runtime)
- `docker-compose.prod.yml` with PostgreSQL + Redis + API + frontend
- Environment-based tier configuration
- Health checks validated
- Auto-run migrations on startup

### Sub-Phase 7.2: Tier System (Weeks 2-3)

**Goal:** Implement free/pro/scale tier model with enforced limits.

- `tier` column on User model
- `TIER_LIMITS` config dict
- Per-tier rate limiting in middleware
- Pre-write checks (collection count, vector count)
- Usage tracking + `GET /v1/usage` endpoint

### Sub-Phase 7.3: Kubernetes + Helm Chart (Weeks 3-5)

**Goal:** Full K8s deployment installable with one command.

- All K8s manifests written and tested locally (minikube)
- Helm chart with per-environment value overrides
- PostgreSQL via managed DB (or StatefulSet for staging)
- Redis Deployment
- Ingress with TLS
- HPA for API pods

### Sub-Phase 7.4: CI/CD Pipeline (Weeks 5-6)

**Goal:** Push to `main` triggers auto test, build, deploy.

- GitHub Actions: test -> build Docker image -> push to registry
- Staging auto-deploy on merge to `main`
- Production deploy on git tag `v*`
- Rollback via `helm rollback`

### Sub-Phase 7.5: Backup & DR (Weeks 6-7)

**Goal:** Automated backups with tested restore.

- PostgreSQL daily `pg_dump` to object storage
- WAL archiving for point-in-time recovery
- K8s CronJob for automated backups
- DR runbook written and tested

### Sub-Phase 7.6: Tenant Isolation Hardening (Weeks 7-8)

**Goal:** Ensure tenants on different tiers can't impact each other.

- Per-tier rate limits (replacing global limit)
- Per-tier query timeouts (`statement_timeout`)
- K8s NetworkPolicies
- K8s resource limits on pods
- Load testing to verify isolation

---

## Part 3: Files to Create

### Docker
| File | Purpose |
|------|---------|
| `Dockerfile` (modify) | Multi-stage build, slim runtime |
| `Dockerfile.web` (new) | Next.js production build |
| `docker-compose.prod.yml` (new) | Full prod stack: API + Web + Postgres + Redis |

### Kubernetes Manifests
```
k8s/
  base/
    namespace.yaml
    api-deployment.yaml
    api-service.yaml
    web-deployment.yaml
    web-service.yaml
    ingress.yaml
    configmap.yaml
    secrets.yaml
    hpa.yaml
    postgres-statefulset.yaml
    postgres-service.yaml
    postgres-pvc.yaml
    redis-deployment.yaml
    redis-service.yaml
    backup-cronjob.yaml
  overlays/
    staging/kustomization.yaml
    production/kustomization.yaml
```

### Helm Chart
```
helm/vectordb/
  Chart.yaml
  values.yaml
  values-staging.yaml
  values-production.yaml
  templates/
    _helpers.tpl
    api-deployment.yaml
    api-service.yaml
    api-hpa.yaml
    web-deployment.yaml
    web-service.yaml
    ingress.yaml
    configmap.yaml
    secrets.yaml
    postgres-statefulset.yaml
    redis-deployment.yaml
    NOTES.txt
```

### Application Code
| File | Purpose |
|------|---------|
| `vectordb/tiers.py` (new) | `TIER_LIMITS` dict with free/pro/scale limits |
| `vectordb/services/usage_service.py` (new) | Per-tenant usage tracking |
| `vectordb/routers/billing.py` (new) | `GET /v1/usage`, `GET /v1/plan`, Stripe webhook |
| `vectordb/models/db.py` (modify) | Add `tier` to User, add `TenantUsage` model |
| `vectordb/auth.py` (modify) | Include `tier` in `ApiKeyInfo` |
| `vectordb/middleware.py` (modify) | Per-tier rate limits |
| `scripts/backup-postgres.sh` (new) | pg_dump to S3 |
| `scripts/restore-postgres.sh` (new) | Restore from backup |

### CI/CD
| File | Purpose |
|------|---------|
| `.github/workflows/deploy.yml` (new) | Test -> Build -> Push -> Deploy pipeline |

---

## Part 4: Tier System Design

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

### Implementation Approach

1. Add `tier` column to `User` model (default: `"free"`)
2. Create `TIER_LIMITS` dict in `vectordb/tiers.py`
3. Modify `RateLimitMiddleware` to use per-tier RPM
4. Add pre-write checks in routers (collection count, vector count)
5. Add `TenantUsage` table for monthly aggregation
6. Start with manual tier assignment; add Stripe later

---

## Part 5: Tenant Isolation

### Already Done
- User-scoped collections via `user_id` FK
- User-scoped API keys
- Auth middleware resolves key -> user_id
- Global rate limiting

### Still Needed
| Layer | What to Add |
|-------|-------------|
| Rate limiting | Per-tier RPM limits |
| Resource limits | K8s `resources.requests/limits` on pods |
| Network isolation | K8s NetworkPolicies |
| Query timeouts | Per-tier `statement_timeout` in Postgres |
| Noisy neighbor | Per-tier connection pool limits |

---

## Part 6: Backup & DR

### Strategy (using managed Postgres)
| Method | Frequency | Retention |
|--------|-----------|-----------|
| Automated snapshots | Daily | 30 days |
| WAL archiving | Continuous | 7 days |
| `pg_dump` to object storage | Daily (CronJob) | 30 days |

### Recovery Scenarios
| Scenario | Recovery Time | Data Loss |
|----------|--------------|-----------|
| API pod crash | ~10 seconds (K8s auto-restart) | None |
| Postgres pod restart | ~30 seconds (PVC retains data) | None |
| Data corruption | 5-30 minutes (restore from backup) | Up to 24h (daily) or minutes (PITR) |
| Cluster destroyed | 30-60 minutes (re-create + restore) | Same as above |

---

## Part 7: Cloud Provider Recommendation

### DigitalOcean (Recommended for Startups)

| Component | Cost |
|-----------|------|
| K8s cluster (2 nodes, 2 vCPU/4GB each) | $48/mo |
| Managed PostgreSQL (1GB) | $15/mo |
| In-cluster Redis | $0 |
| Spaces (backups, 250GB) | $5/mo |
| **Total** | **~$68/mo** |

**Why DO over AWS/GCP:** Free K8s control plane, simpler UI, lower cost, good docs. Move to AWS/GCP when you need multi-region or compliance certs.

**Pre-revenue alternative:** Single $24/mo Droplet with `docker-compose.prod.yml`. Migrate to K8s when you have 5+ paying customers.

---

## Part 8: Timeline

### Month 1: Foundation (Weeks 1-4)
| Week | Task |
|------|------|
| 1 | Production Docker Compose + multi-stage Dockerfile |
| 2 | Tier model + per-tier rate limiting + usage tracking |
| 3 | K8s manifests + Helm chart (test on minikube) |
| 4 | CI/CD pipeline (test + build + push) |

### Month 2: Production (Weeks 5-8)
| Week | Task |
|------|------|
| 5 | DigitalOcean K8s cluster + managed Postgres + staging deploy |
| 6 | Ingress + TLS + DNS + backup CronJob |
| 7 | Production deploy pipeline + HPA |
| 8 | Tenant isolation hardening + load testing + DR drill |

### Start THIS Weekend
1. Create `docker-compose.prod.yml` (Postgres + Redis + API)
2. Test `STORAGE_BACKEND=postgres` end-to-end
3. Add `tier` to User model + `TIER_LIMITS` dict
4. Add per-tier rate limiting
5. Deploy to a single DigitalOcean Droplet

**You now have a live managed service. Kubernetes comes after, not before.**
