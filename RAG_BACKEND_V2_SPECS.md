# TASK: Implement RAG Layer (Document Upload + Query)

---

# 1. WHAT (FUNCTIONAL REQUIREMENTS)

You must implement TWO new capabilities:

## 1.1 Document Upload
Allow users to upload a document and automatically:
- extract text
- split into chunks
- generate embeddings
- store in existing vector DB

## 1.2 Query Retrieval
Allow users to send a query and:
- convert to embedding
- retrieve relevant chunks
- return ranked results

---

# 2. WHY (CONSTRAINTS + INTENT)

This feature exists to:
- hide vector complexity from users
- align backend with RAG-based product positioning
- reuse existing vector DB infrastructure

IMPORTANT:
- DO NOT build a new system
- DO NOT duplicate search/index logic
- ONLY orchestrate existing components

---

# 3. HOW (IMPLEMENTATION PLAN)

Follow EXACTLY.

---

# 3.1 CREATE NEW ROUTERS

## File: vectordb/routers/documents.py

Add endpoint:

POST /v1/documents/upload

### Steps:
1. Accept multipart/form-data
2. Validate:
   - file exists
   - file extension == .txt
   - collection_name provided

3. Read file → string

4. Call DocumentService.process_document()

5. Return response

---

## File: vectordb/routers/query.py

Add endpoint:

POST /v1/query

### Steps:
1. Validate input
2. Call QueryService.run_query()
3. Return results

---

# 3.2 CREATE SERVICES

## File: vectordb/services/document_service.py

### Function:
process_document(file_text: str, collection_name: str) -> dict

### Steps (STRICT ORDER):

1. Generate document_id (UUID)

2. Chunk text
   - chunk_size = 500
   - overlap = 50

3. For each chunk:
   - generate embedding
   - build metadata:
     {
       "document_id": doc_id,
       "chunk_index": i,
       "text": chunk
     }

4. Call EXISTING upsert logic:
   - DO NOT write new DB logic
   - Use current vector service

5. Return:
   {
     "document_id": doc_id,
     "chunks_created": N
   }

---

## File: vectordb/services/query_service.py

### Function:
run_query(query: str, collection_name: str, top_k: int)

### Steps:

1. Generate embedding for query

2. Call EXISTING search function

3. Extract results:
   - text from metadata
   - score
   - metadata

4. Return formatted response

---

## File: vectordb/services/embedding_service.py

### Function:
embed_text(text: str) -> List[float]

### RULES:

- MUST be isolated (no direct API calls in routers)
- MUST be swappable later

### TEMP IMPLEMENTATION:

Option A:
- external API (OpenAI / etc.)

Option B:
- dummy embedding (for testing)

---

# 3.3 CHUNKING LOGIC (MANDATORY)

Implement EXACT logic:

```python
def chunk_text(text):
    chunk_size = 500
    overlap = 50
    step = chunk_size - overlap

    chunks = []
    for i in range(0, len(text), step):
        chunk = text[i:i + chunk_size]
        if chunk:
            chunks.append(chunk)

    return chunks