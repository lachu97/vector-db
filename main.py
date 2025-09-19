# main.py
from fastapi import FastAPI, HTTPException
from typing import List
import numpy as np
import os

from db import init_db, SessionLocal, Vector
from indexer import HNSWIndexer
from schemas import UpsertRequest, BulkUpsertRequest, SearchRequest

# config
DIM = 384
INDEX_PATH = "data/index.bin"
os.makedirs("data", exist_ok=True)

# init DB + index
init_db()
indexer = HNSWIndexer(dim=DIM, index_path=INDEX_PATH, max_elements=10000)
app = FastAPI(title="Vector DB MVP")

@app.on_event("startup")
def startup():
    init_db()
    if os.path.exists(INDEX_PATH):
        # Load saved index from disk
        indexer.load()
    else:
        # Rebuild index from DB if index file not found
        db = SessionLocal()
        try:
            for row in db.query(Vector).all():
                vec = np.frombuffer(row.vector, dtype=np.float32)
                indexer.add_item(vec, row.internal_id)
        finally:
            db.close()


@app.on_event("shutdown")
def shutdown():
    indexer.save()

@app.post("/upsert")
def upsert_vector(item: dict):
    db = SessionLocal()
    try:
        external_id = item["external_id"]
        # normalize vector for cosine space
        vec = np.array(item["vector"], dtype=np.float32)
        vec /= np.linalg.norm(vec) + 1e-10
        metadata = item.get("metadata")

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
            indexer.add_item(vec, idx)
        else:
            row = Vector(external_id=external_id, vector=vec.tolist(), meta=metadata or {})
            db.add(row)
            db.commit()
            db.refresh(row)
            idx = row.internal_id
            indexer.add_item(vec, idx)
            status = "inserted"

        db.commit()
        return {
            "external_id": row.external_id,
            "internal_id": row.internal_id,
            "status": status,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.post("/bulk_upsert")
def bulk_upsert(req: BulkUpsertRequest):
    db = SessionLocal()
    try:
        results = []
        for it in req.items:
            if len(it.vector) != DIM:
                raise HTTPException(status_code=400, detail=f"vector dim must be {DIM}")
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
                indexer.add_item(vec, idx)
                results.append({
                    "external_id": it.external_id,
                    "internal_id": idx,
                    "status": "updated"
                })
            else:
                new = Vector(external_id=it.external_id, meta=it.metadata or {}, vector=vec.tolist())
                db.add(new)
                db.commit()
                db.refresh(new)
                idx = new.internal_id
                indexer.add_item(vec, idx)
                results.append({
                    "external_id": it.external_id,
                    "internal_id": idx,
                    "status": "inserted"
                })
        return {"results": results}
    finally:
        db.close()

@app.post("/search")
def search(req: SearchRequest):
    if len(req.vector) != DIM:
        raise HTTPException(status_code=400, detail=f"vector dimension must be {DIM}")
    q = np.array(req.vector, dtype=np.float32)
    db = SessionLocal()
    try:
        if req.filters:
            # naive filter: load all metadata and filter in Python (simple MVP)
            cand_rows = []
            for row in db.query(Vector).all():
                md = row.meta or {}
                ok = True
                for k, v in req.filters.items():
                    if md.get(k) != v:
                        ok = False
                        break
                if ok:
                    cand_rows.append(row)
            if not cand_rows:
                return {"results": []}
            # brute-force similarity on candidate vectors
            mat = np.vstack([np.frombuffer(r.vector, dtype=np.float32) for r in cand_rows])
            # compute cosine similarity
            qn = q / np.linalg.norm(q)
            matn = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-10)
            scores = matn.dot(qn)
            idxs = np.argsort(-scores)[:req.k]
            out = []
            for i in idxs:
                r = cand_rows[i]
                out.append({"external_id": r.external_id, "score": float(scores[i]), "metadata": r.meta})
            return {"results": out}
        else:
            cur = indexer.get_current_count()
            k = min(req.k, max(1, cur))
            labels, distances = indexer.knn_query(q, k=k)

            # convert to numpy arrays for safe handling
            labels = np.array(labels)
            distances = np.array(distances)

            # ensure 2D
            if labels.ndim == 1:
                labels = labels.reshape(1, -1)
                distances = distances.reshape(1, -1)

            out = []
            for lbl_row, dist_row in zip(labels, distances):
                for lbl, dist in zip(lbl_row, dist_row):
                    db_row = db.query(Vector).filter_by(internal_id=int(lbl)).first()
                    if db_row:
                        score = 1 - float(dist)  # since index is using cosine
                        out.append({"external_id": db_row.external_id, "score": score, "metadata": db_row.meta})
            return {"results": out}
    finally:
        db.close()


@app.get("/")
def root():
    return {
        "message": "Welcome to Vector DB MVP 🚀",
        "endpoints": ["/upsert", "/bulk_upsert", "/search", "/health"]
    }

@app.delete("/delete/{external_id}")
def delete_vector(external_id: str):
    db = SessionLocal()
    try:
        row = db.query(Vector).filter_by(external_id=external_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        # Try removing from index, but don’t crash if missing
        try:
            indexer.mark_deleted(int(row.internal_id))
        except Exception as e:
            print(f"[WARN] Could not mark_deleted({row.internal_id}): {e}")

        db.delete(row)
        db.commit()
        return {
            "status": "deleted",
            "external_id": external_id,
            "internal_id": row.internal_id
        }
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok", "count": indexer.get_current_count()}
