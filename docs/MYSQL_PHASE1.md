# MySQL Phase 1 Notes

This project now uses MySQL as the primary relational database for the PRD phase 1 data foundation.

## Default Connection

The application reads these environment variables:

```ini
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DATABASE=bidding
```

The database and tables are created automatically when `main.py` starts.

## Docker MySQL

```powershell
docker run -d --name mysql -p 3306:3306 -e MYSQL_ROOT_PASSWORD=123456 -v mysql-data:/var/lib/mysql mysql:8
```

## Phase 1 Tables

The startup initializer creates the core PRD phase 1 tables:

- tenant/company/user role foundation: `tenants`, `companies`, `users`, `roles`, `user_roles`
- project persistence: `bid_projects`, `project_members`, `project_facts`
- document metadata and RAG traceability: `document_files`, `document_versions`, `document_chunks`, `knowledge_bases`, `knowledge_documents`
- generated bid persistence: `bid_documents`, `bid_document_versions`, `bid_chapters`, `bid_chapter_versions`
- AI task traceability: `generation_tasks`, `agent_runs`, `model_call_logs`
- compatibility tables: `bidding`, `model_settings`

The existing API paths are intentionally preserved while the storage layer has moved from SQLite to MySQL.

## Phase 2 Vector And Knowledge Base

The second phase adds a VectorStore abstraction and enterprise knowledge-base APIs.

Default development mode keeps Chroma:

```ini
VECTOR_STORE=chroma
VECTOR_COLLECTION=document_embeddings
EMBEDDING_MODEL=text-embedding-v3
```

Milvus can be enabled after deploying Milvus 2.x:

```ini
VECTOR_STORE=milvus
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
EMBEDDING_DIM=1024
```

For the local Docker installation in `E:\milvus`, the compose file exposes:

- Milvus gRPC: `127.0.0.1:19530`
- Milvus HTTP/metrics: `127.0.0.1:9091`
- MinIO: `127.0.0.1:9000`

Run a connection check after installing `pymilvus`:

```powershell
.\.venv\Scripts\python.exe check_milvus.py
```

Knowledge-base APIs:

- `POST /api/knowledge-bases`
- `GET /api/knowledge-bases`
- `POST /api/knowledge-bases/{kb_id}/documents`
- `POST /api/documents/{document_id}/ingest`
- `GET /api/documents/{document_id}/chunks`
- `DELETE /api/documents/{document_id}`
- `POST /api/knowledge/search`
