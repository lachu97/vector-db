# Fix Collection Name Uniqueness Scope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix collection names so they are unique per-user, not globally — User A and User B can both own a collection named `products` without conflict.

**Architecture:** Three-layer fix: (1) change the DB unique constraint from `UNIQUE(name)` to `UNIQUE(user_id, name)`, (2) scope the existence check in `create_collection` by `user_id`, (3) special-case `user_id=None` (bootstrap superadmin) with an app-level NULL check since SQLite treats `NULL != NULL` in unique constraints. Remove the "Known Bug" section from CLAUDE.md once fixed.

**Tech Stack:** SQLAlchemy (ORM model), Alembic (migration), SQLite, pytest

---

## File Map

| Action | File | What changes |
|--------|------|-------------|
| Modify | `vectordb/models/db.py:72-83` | Remove `unique=True` from `name` column; add `UniqueConstraint("user_id", "name")` to `__table_args__` |
| Create | `migrations/versions/<hash>_scope_collection_name_uniqueness_per_user.py` | Drop global unique index on `name`; add composite unique on `(user_id, name)` |
| Modify | `vectordb/backends/sqlite_hnsw.py:197-214` | Scope existence check in `create_collection` by `user_id` |
| Modify | `tests/test_collections.py` | Add cross-user same-name test; keep existing duplicate test |
| Modify | `CLAUDE.md` | Remove "Known Bug" section — bug is fixed |

---

## Task 1: Update DB model

**Files:**
- Modify: `vectordb/models/db.py:72-83`

- [ ] **Step 1: Update the Collection class**

Find the `Collection` class (starts at line 72). Change:

```python
# BEFORE
class Collection(Base):
    __tablename__ = "collections"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    dim = Column(Integer, nullable=False)
    distance_metric = Column(String, nullable=False, default="cosine")
    description = Column(Text, nullable=True)
    user_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    extraction_model = Column(String, nullable=True)
    extraction_api_keys = Column(Text, nullable=True)

    vectors = relationship("Vector", back_populates="collection", cascade="all, delete-orphan")
```

To:

```python
# AFTER
class Collection(Base):
    __tablename__ = "collections"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)   # unique=True removed — now (user_id, name) is unique
    dim = Column(Integer, nullable=False)
    distance_metric = Column(String, nullable=False, default="cosine")
    description = Column(Text, nullable=True)
    user_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    extraction_model = Column(String, nullable=True)
    extraction_api_keys = Column(Text, nullable=True)

    vectors = relationship("Vector", back_populates="collection", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_collection"),
    )
```

Also verify `UniqueConstraint` is in the imports at the top of `db.py` — it should already be there. If not, add it to the SQLAlchemy import line.

- [ ] **Step 2: Verify UniqueConstraint is imported**

```bash
grep "UniqueConstraint" vectordb/models/db.py
```

Expected: at least one line showing `UniqueConstraint` imported and one showing it used.

- [ ] **Step 3: Commit model change only (not migration yet)**

```bash
git add vectordb/models/db.py
git commit -m "fix(db): scope collection name uniqueness to (user_id, name) instead of global name"
```

---

## Task 2: Alembic migration

**Files:**
- Create: `migrations/versions/<hash>_scope_collection_name_uniqueness_per_user.py`

- [ ] **Step 1: Generate migration**

```bash
alembic revision --autogenerate -m "scope_collection_name_uniqueness_per_user"
```

Expected: new file created in `migrations/versions/`.

- [ ] **Step 2: Inspect the generated migration**

Open the generated file. Verify it contains:
- A `batch_alter_table('collections')` block that drops the old unique constraint on `name` and creates `uq_user_collection` on `(user_id, name)`

If autogenerate missed it (SQLite detection is inconsistent), manually write the upgrade/downgrade:

```python
def upgrade() -> None:
    with op.batch_alter_table('collections', schema=None) as batch_op:
        batch_op.drop_index('ix_collections_name')           # drops the old unique index
        batch_op.create_index('ix_collections_name', ['name'], unique=False)  # recreate non-unique
        batch_op.create_unique_constraint('uq_user_collection', ['user_id', 'name'])


def downgrade() -> None:
    with op.batch_alter_table('collections', schema=None) as batch_op:
        batch_op.drop_constraint('uq_user_collection', type_='unique')
        batch_op.drop_index('ix_collections_name')
        batch_op.create_index('ix_collections_name', ['name'], unique=True)
```

- [ ] **Step 3: Apply migration**

```bash
alembic upgrade head
```

Expected: no errors; migration log shows the revision running.

- [ ] **Step 4: Verify constraint in DB (CRITICAL — SQLite batch_alter can silently fail)**

```bash
python -c "
import sqlite3
conn = sqlite3.connect('vectors.db')
# Check indexes on collections
indexes = list(conn.execute(\"PRAGMA index_list('collections')\"))
print('Indexes:', indexes)
for idx in indexes:
    info = list(conn.execute(f\"PRAGMA index_info('{idx[1]}')\"))
    print(f'  {idx[1]} (unique={idx[2]}): {info}')
"
```

Expected output: `ix_collections_name` should show `unique=0`. A new index for `uq_user_collection` should show `unique=1` with columns `user_id` and `name`.

If `uq_user_collection` is missing, apply it manually:

```bash
python -c "
import sqlite3, shutil
conn = sqlite3.connect('vectors.db')
# SQLite can't drop/add constraints directly — need to recreate table
# This is why we use batch_alter_table in Alembic. If it failed, re-run migration.
print('Run: alembic downgrade -1 && alembic upgrade head')
"
```

- [ ] **Step 5: Commit migration**

```bash
git add migrations/
git commit -m "fix(migration): replace global UNIQUE(name) with UNIQUE(user_id, name) on collections"
```

---

## Task 3: Fix create_collection existence check in backend

**Files:**
- Modify: `vectordb/backends/sqlite_hnsw.py:197-214`

- [ ] **Step 1: Write failing test**

Add to `tests/test_collections.py` — append after `test_create_collection_duplicate`:

```python
def test_two_users_can_create_same_collection_name(client):
    """Different users can own collections with the same name."""
    # Register two distinct users
    r1 = client.post("/v1/auth/register", json={"email": "user_col_a@test.com", "password": "password123"})
    r2 = client.post("/v1/auth/register", json={"email": "user_col_b@test.com", "password": "password123"})
    key_a = r1.json()["data"]["api_key"]["key"]
    key_b = r2.json()["data"]["api_key"]["key"]

    # Both create a collection named "shared-name"
    resp_a = client.post(
        "/v1/collections",
        json={"name": "shared-name", "dim": 4},
        headers={"x-api-key": key_a},
    )
    assert resp_a.json()["status"] == "success", f"User A failed: {resp_a.json()}"

    resp_b = client.post(
        "/v1/collections",
        json={"name": "shared-name", "dim": 4},
        headers={"x-api-key": key_b},
    )
    assert resp_b.json()["status"] == "success", f"User B got conflict: {resp_b.json()}"

    # User A does NOT see User B's collection
    list_a = client.get("/v1/collections", headers={"x-api-key": key_a})
    names_a = [c["name"] for c in list_a.json()["data"]["collections"]]
    assert names_a.count("shared-name") == 1  # only their own


def test_same_user_cannot_create_duplicate_collection_name(client):
    """Same user cannot own two collections with the same name."""
    r = client.post("/v1/auth/register", json={"email": "user_dup@test.com", "password": "password123"})
    key = r.json()["data"]["api_key"]["key"]

    client.post("/v1/collections", json={"name": "my-col", "dim": 4}, headers={"x-api-key": key})
    resp = client.post("/v1/collections", json={"name": "my-col", "dim": 4}, headers={"x-api-key": key})
    assert resp.json()["error"]["code"] == 409
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_collections.py::test_two_users_can_create_same_collection_name tests/test_collections.py::test_same_user_cannot_create_duplicate_collection_name -v
```

Expected: both FAIL — `test_two_users_can_create_same_collection_name` gets 409 on User B's create.

- [ ] **Step 3: Fix create_collection in sqlite_hnsw.py**

Find `create_collection` (~line 197). Replace the existence check:

```python
async def create_collection(
    self, name: str, dim: int, distance_metric: str,
    description: Optional[str] = None, user_id: Optional[int] = None,
) -> Dict[str, Any]:
    async with self._session_factory() as session:
        # Scope duplicate check to the same user.
        # user_id=None (bootstrap) uses IS NULL to avoid SQLite NULL != NULL trap.
        if user_id is not None:
            stmt = select(_Collection).where(
                _Collection.name == name,
                _Collection.user_id == user_id,
            )
        else:
            stmt = select(_Collection).where(
                _Collection.name == name,
                _Collection.user_id.is_(None),
            )
        existing = await session.execute(stmt)
        if existing.scalar_one_or_none():
            raise CollectionAlreadyExistsError(name)

        col = _Collection(
            name=name, dim=dim, distance_metric=distance_metric,
            description=description, user_id=user_id,
        )
        session.add(col)
        await session.commit()
        await session.refresh(col)
        self._index_manager.get_or_create(col.name, col.dim, col.distance_metric)
        self._col_cache.invalidate(name)
        return _col_to_dict(col, 0)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_collections.py::test_two_users_can_create_same_collection_name tests/test_collections.py::test_same_user_cannot_create_duplicate_collection_name -v
```

Expected: both PASS.

- [ ] **Step 5: Run full collection test suite**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_collections.py -v
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add vectordb/backends/sqlite_hnsw.py tests/test_collections.py
git commit -m "fix(backend): scope collection name duplicate check to user_id; two users can own same-named collections"
```

---

## Task 4: Full suite + remove bug doc from CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run full test suite**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/ -q --ignore=tests/test_phase6_cli.py --ignore=tests/test_phase6_python_sdk.py --ignore=tests/test_phase5.py 2>&1 | tail -5
```

Expected: same pass count as before + 2 new tests, 1 pre-existing failure (`test_root`).

- [ ] **Step 2: Remove "Known Bug" section from CLAUDE.md**

Find and remove this entire block from `CLAUDE.md`:

```markdown
## Known Bug: Collection Names Are Globally Unique but Visibility Is Per-User

**Problem:** Collection names are enforced as globally unique in the database, but `GET /v1/collections` only returns collections scoped to the authenticated user (`user_id`). This means:
- User A creates collection `products` → succeeds
- User B tries to create collection `products` → gets "already exists" error
- User B calls `GET /v1/collections` → does NOT see `products` (it belongs to User A)

The user sees "already exists" for a collection that doesn't appear in their list. Confusing UX.

**Fix options:**
1. **Scope collection names per user** (recommended) — make the unique constraint `(user_id, name)` instead of just `(name)`. Different users can have collections with the same name.
2. **Show a better error message** — e.g., "A collection with this name already exists (owned by another user). Please choose a different name."
3. **Namespace collection names** — internally prefix with `user_{id}_` but display without prefix.

**Where to fix:** Collection creation logic (likely in the storage backend's create_collection method) and the SQLite/PostgreSQL unique constraint on the collections table.

---
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: remove Known Bug section — collection name per-user uniqueness is fixed"
```
