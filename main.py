# main.py
import os
import traceback
import logging
from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import JSONResponse

from db import init_db, SessionLocal, Vector
from indexer import HNSWIndexer
from schemas import BulkUpsertRequest, SearchRequest

# ------------------------------------------------------------------
# Config (from environment)
# ------------------------------------------------------------------
DIM = int(os.getenv("VECTOR_DIM", 384))
INDEX_PATH = os.getenv("INDEX_PATH", "data/index.bin")
MAX_ELEMENTS = int(os.getenv("MAX_ELEMENTS", 10000))
EF_CONSTRUCTION = int(os.getenv("EF_CONSTRUCTION", 200))
M = int(os.getenv("M", 16))
EF_QUERY = int(os.getenv("EF_QUERY", 50))
API_KEY = str(os.environ.get("API_KEY", "test-key"))  # default for dev

os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)

# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# FastAPI app
# ------------------------------------------------------------------
app = FastAPI(title="Vector DB MVP", version="1.0.0")
api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

# ------------------------------------------------------------------
# Utils
# ------------------------------------------------------------------
def verify_api_key(api_key: Optional[str] = Depends(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key

def success_response(data):
    return {"status": "success", "data": data, "error": None}

def error_response(code, message):
    return {"status": "error", "data": None, "error": {"code": code, "message": message}}

def safe_add_to_index(vector: np.ndarray, internal_id: int):
    """Safely add a vector to HNSW index, resizing if necessary."""
    try:
        indexer.add_item(vector, internal_id)
    except RuntimeError as e:
        logger.warning(f"Index full or error: {e}")
        current_max = indexer.index.get_max_elements()
        indexer.index.resize_index(current_max * 2)
        indexer.add_item(vector, internal_id)

# ------------------------------------------------------------------
# DB + Index init
# ------------------------------------------------------------------
init_db()
indexer = HNSWIndexer(dim=DIM, index_path=INDEX_PATH, max_elements=MAX_ELEMENTS)

@app.on_event("startup")
def startup():
    try:
        init_db()
        if os.path.exists(INDEX_PATH):
            indexer.load()
            logger.info(f"Loaded index from {INDEX_PATH}")
        else:
            db = SessionLocal()
            try:
                for row in db.query(Vector).all():
                    vec = np.array(row.vector, dtype=np.float32)
                    safe_add_to_index(vec, row.internal_id)
                logger.info("Index built from DB")
            finally:
                db.close()
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        traceback.print_exc()

@app.on_event("shutdown")
def shutdown():
    try:
        indexer.save()
        logger.info("Index saved successfully on shutdown")
    except Exception as e:
        logger.error(f"Failed to save index: {e}")

# ------------------------------------------------------------------
# Global Exception Handler
# ------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(status_code=500, content=error_response(500, str(exc)))

# ------------------------------------------------------------------
# API v1 Endpoints
# ------------------------------------------------------------------
@app.post("/v1/upsert")
def upsert_vector(item: dict, api_key: str = Depends(verify_api_key)):
    db = SessionLocal()
    try:
        external_id = item["external_id"]
        vec = np.array(item["vector"], dtype=np.float32)
        vec /= np.linalg.norm(vec) + 1e-10
        metadata = item.get("metadata", {})

        row = db.query(Vector).filter_by(external_id=external_id).first()
        if row:
            row.vector = vec.tolist()
            row.meta = metadata or row.meta
            status = "updated"
            idx = row.internal_id
            try:
                indexer.mark_deleted(idx)
            except Exception:
                pass
            safe_add_to_index(vec, idx)
        else:
            row = Vector(external_id=external_id, vector=vec.tolist(), meta=metadata)
            db.add(row)
            db.commit()
            db.refresh(row)
            idx = row.internal_id
            safe_add_to_index(vec, idx)
            status = "inserted"

        db.commit()
        return success_response({
            "external_id": row.external_id,
            "internal_id": row.internal_id,
            "status": status
        })
    finally:
        db.close()

@app.post("/v1/bulk_upsert")
def bulk_upsert(req: BulkUpsertRequest, api_key: str = Depends(verify_api_key)):
    db = SessionLocal()
    try:
        results = []
        for it in req.items:
            if len(it.vector) != DIM:
                return error_response(400, f"Vector dimension must be {DIM}")
            vec = np.array(it.vector, dtype=np.float32)
            vec /= np.linalg.norm(vec) + 1e-10

            existing = db.query(Vector).filter_by(external_id=it.external_id).first()
            if existing:
                existing.vector = vec.tolist()
                existing.meta = it.metadata or existing.meta
                db.commit()
                idx = existing.internal_id
                try:
                    indexer.mark_deleted(idx)
                except Exception:
                    pass
                safe_add_to_index(vec, idx)
                results.append({"external_id": it.external_id, "internal_id": idx, "status": "updated"})
            else:
                new = Vector(external_id=it.external_id, vector=vec.tolist(), meta=it.metadata or {})
                db.add(new)
                db.commit()
                db.refresh(new)
                idx = new.internal_id
                safe_add_to_index(vec, idx)
                results.append({"external_id": it.external_id, "internal_id": idx, "status": "inserted"})
        return success_response({"results": results})
    finally:
        db.close()

@app.post("/v1/search")
def search(req: SearchRequest, api_key: str = Depends(verify_api_key)):
    if len(req.vector) != DIM:
        return error_response(400, f"Vector dimension must be {DIM}")
    q = np.array(req.vector, dtype=np.float32)
    db = SessionLocal()
    try:
        if req.filters:
            # naive filter
            cand_rows = [r for r in db.query(Vector).all()
                         if all((r.meta or {}).get(k) == v for k, v in req.filters.items())]
            if not cand_rows:
                return success_response({"results": []})

            mat = np.vstack([np.array(r.vector, dtype=np.float32) for r in cand_rows])
            qn = q / np.linalg.norm(q)
            matn = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-10)
            scores = matn.dot(qn)
            idxs = np.argsort(-scores)[:req.k]
            out = [
                {"external_id": cand_rows[i].external_id, "score": float(scores[i]), "metadata": cand_rows[i].meta}
                for i in idxs
            ]
            return success_response({"results": out})
        else:
            cur = indexer.get_current_count()
            k_safe = min(req.k, max(1, cur))
            labels, distances = indexer.knn_query(q, k=k_safe)
            out = []
            for lbl, dist in zip(labels, distances):
                db_row = db.query(Vector).filter_by(internal_id=int(lbl)).first()
                if db_row:
                    out.append({"external_id": db_row.external_id, "score": float(1 - dist), "metadata": db_row.meta})
            return success_response({"results": out})
    finally:
        db.close()

@app.delete("/v1/delete/{external_id}")
def delete_vector(external_id: str, api_key: str = Depends(verify_api_key)):
    db = SessionLocal()
    try:
        row = db.query(Vector).filter_by(external_id=external_id).first()
        if not row:
            return error_response(404, "Not found")
        try:
            indexer.mark_deleted(int(row.internal_id))
        except Exception as e:
            logger.warning(f"Could not mark_deleted({row.internal_id}): {e}")
        db.delete(row)
        db.commit()
        return success_response({"status": "deleted", "external_id": external_id, "internal_id": row.internal_id})
    finally:
        db.close()

# ------------------------------------------------------------------
# Recommendation
# ------------------------------------------------------------------
@app.post("/v1/recommend/{external_id}")
def recommend(external_id: str, k: int = 5, ef: int = EF_QUERY, api_key: str = Depends(verify_api_key)):
    db = SessionLocal()
    try:
        row = db.query(Vector).filter_by(external_id=external_id).first()
        if not row:
            return error_response(404, f"{external_id} not found")

        vec = np.array(row.vector, dtype=np.float32)
        vec /= np.linalg.norm(vec) + 1e-10

        total = indexer.get_current_count()
        k_safe = min(k, max(1, total - 1))
        if k_safe < 1:
            return success_response({"results": []})

        try:
            indexer.index.set_ef(ef)
        except Exception:
            pass

        labels, distances = indexer.knn_query(vec, k=k_safe + 1)
        out = []
        for lbl, dist in zip(labels, distances):
            if lbl == row.internal_id:
                continue
            db_row = db.query(Vector).filter_by(internal_id=int(lbl)).first()
            if db_row:
                out.append({"external_id": db_row.external_id, "score": float(1 - dist), "metadata": db_row.meta})
            if len(out) >= k_safe:
                break

        return success_response({"results": out})
    finally:
        db.close()

# ------------------------------------------------------------------
# Similarity
# ------------------------------------------------------------------
@app.post("/v1/similarity")
def similarity(id1: str, id2: str, api_key: str = Depends(verify_api_key)):
    db = SessionLocal()
    try:
        v1 = db.query(Vector).filter_by(external_id=id1).first()
        v2 = db.query(Vector).filter_by(external_id=id2).first()
        if not v1 or not v2:
            return error_response(404, "One or both IDs not found")

        vec1 = np.array(v1.vector, dtype=np.float32)
        vec2 = np.array(v2.vector, dtype=np.float32)
        vec1 /= np.linalg.norm(vec1) + 1e-10
        vec2 /= np.linalg.norm(vec2) + 1e-10

        score = float(np.dot(vec1, vec2))
        return success_response({"score": score})
    finally:
        db.close()

# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------
@app.get("/v1/health")
def health(api_key: str = Depends(verify_api_key)):
    return success_response({
        "status": "ok",
        "vector_count": indexer.get_current_count(),
        "index_path": INDEX_PATH
    })

# ------------------------------------------------------------------
# Root
# ------------------------------------------------------------------
@app.get("/")
def root():
    return {
        "message": "Welcome to Vector DB MVP 🚀",
        "docs": "/docs",
        "endpoints": [
            "/v1/upsert", "/v1/bulk_upsert", "/v1/search",
            "/v1/delete/{id}", "/v1/health", "/v1/recommend/{id}", "/v1/similarity"
        ]
    }
