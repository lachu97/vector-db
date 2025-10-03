# 🚀 Vector DB For AI Applications(a MVP Product)

A lightweight **vector database service** built with **FastAPI**, **SQLite**, and **HNSWlib**.  
It provides endpoints for storing, searching, and managing vector embeddings with optional metadata and filters.  

This is a **minimal product** for experimentation, prototyping, and small-scale vector search use cases.

---

## ✨ Features

- Store vectors with metadata (`/upsert`, `/bulk_upsert`)
- Delete vectors by `external_id` (`/delete/{external_id}`)
- Approximate nearest neighbor search with **HNSWlib**
- Cosine similarity support
- Simple filtering on metadata
- REST API powered by **FastAPI**
- SQLite backend for persistence
- Dockerized for easy deployment
- Dockerized with Gunicorn + Uvicorn for production
- Healthcheck endpoint for container orchestration

---

## 🛠️ Tech Stack

- [FastAPI](https://fastapi.tiangolo.com/) - API framework
- [SQLAlchemy](https://www.sqlalchemy.org/) - ORM for SQLite
- [HNSWlib](https://github.com/nmslib/hnswlib) - ANN index
- [NumPy](https://numpy.org/) - math & vector operations
- [Docker](https://www.docker.com/) - containerization

---

## ⚡ Getting Started (Local)

### 1. Clone repo
```bash
git clone https://github.com/yourname/vector-db-mvp.git
cd vector-db-mvp
```
### 2. Create virtual environment
```bash 
python3 -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
```
### 3. Install Dependencies
```bash 
pip install -r requirements.txt
```
### 4. Run server
```bash 
uvicorn main:app --reload
```

## 🐳 Running with Docker

### 1. Build image

```bash 
docker build -t vector-db-mvp 
```

### 2. Run container

```bash 
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -e API_KEY=test-key \
  --name vectordb_app \
  vector-db-mvp

```

### 3. Check logs

```bash 
docker logs -f vector-db
```

### Docker Compose 
```bash 
docker compose up -d
```
### 📡 API Endpoints

| Method   | Endpoint          | Description                                              |
| -------- | ----------------- | -------------------------------------------------------- |
| `POST`   | `/v1/upsert`      | Insert or update a single vector                         |
| `POST`   | `/v1/bulk_upsert` | Insert or update multiple vectors                        |
| `POST`   | `/v1/search`      | Search nearest neighbors (with optional metadata filter) |
| `POST`   | `/v1/similarity`  | Cosine similarity between two vectors                    |
| `POST`   | `/v1/recommend`   | Recommend similar vectors (skip self)                    |
| `DELETE` | `/v1/delete/{id}` | Delete vector by external_id                             |
| `GET`    | `/v1/health`      | Health check + count of indexed items                    |
| `GET`    | `/`               | Welcome message + docs link                              |



### Example: Upsert

```bash 
POST /v1/upsert
{
  "external_id": "doc1",
  "vector": [0.12, 0.98, ...], 
  "metadata": { "category": "news" }
}


```

### Example: Search

```bash 
POST /v1/search
{
  "vector": [0.11, 0.95, ...],
  "k": 3,
  "filters": { "category": "news" }
}


```

### Health Check 
```bash
curl -H "x-api-key: test-key" http://localhost:8000/v1/health
```

### 🔒 API Key

```bash 
x-api-key: <API_KEY>
```
- Configurable via environment variable API_KEY
- Default (development) is test-key
### 🚀 Roadmap
- 1.Authentication & API keys
- 2.Pagination for search results
- 3.Support for other distance metrics
- 4.Better filter engine
- 5.Cloud deployment templates (AWS/GCP/Azure)

### ❤️ EnterPrise API

For Enterprise APIs and support, write a mail to stellarworks03@gmail.com

### ❤️ Contributing

PRs welcome! Fork and submit improvements.

### 📜 License

MIT License © 2025

---
