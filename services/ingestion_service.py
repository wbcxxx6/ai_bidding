import hashlib
import json
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

import mammoth
import PyPDF2

from core.db import get_db
from services.retrieval_router import retrieval_router
from storage.storage_service import storage_service
from storage.vector_store import EMBEDDING_MODEL, VECTOR_COLLECTION, get_vector_store


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def extract_text(file_path):
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = ""
        with open(path, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text += (page.extract_text() or "") + "\n"
        return text
    if suffix in {".doc", ".docx"}:
        with open(path, "rb") as file:
            return mammoth.extract_raw_text(file).value
    encodings = ["utf-8", "utf-8-sig", "gb18030", "gbk", "latin-1"]
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="latin-1", errors="ignore")


def extract_text_from_bytes(filename, content_bytes):
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".pdf":
        text = ""
        reader = PyPDF2.PdfReader(BytesIO(content_bytes))
        for page in reader.pages:
            text += (page.extract_text() or "") + "\n"
        return text
    if suffix in {".doc", ".docx"}:
        return mammoth.extract_raw_text(BytesIO(content_bytes)).value
    for encoding in ["utf-8", "utf-8-sig", "gb18030", "gbk", "latin-1"]:
        try:
            return content_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content_bytes.decode("latin-1", errors="ignore")


def split_text(text, max_length=1200, overlap=150):
    normalized = re.sub(r"\n{3,}", "\n\n", text or "").strip()
    if not normalized:
        return []
    chunks = []
    start = 0
    while start < len(normalized):
        end = min(start + max_length, len(normalized))
        if end < len(normalized):
            boundary = max(
                normalized.rfind("\n\n", start, end),
                normalized.rfind("\u3002", start, end),
            )
            if boundary > start + max_length // 2:
                end = boundary + 1
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(0, end - overlap)
    return chunks


def build_chunk_id(file_id, index, text):
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()
    return f"chunk_{file_id}_{index}_{digest}"


def ingest_document(
    *,
    file_id,
    storage_key=None,
    doc_type,
    tenant_id=1,
    project_id=None,
    knowledge_base_id=None,
    knowledge_document_id=None,
):
    blob = storage_service.get_latest(file_id)
    text = blob.get("content_text") or extract_text_from_bytes(blob["original_filename"], blob["content"])
    chunk_texts = split_text(text)
    chunks = []
    for index, chunk_text in enumerate(chunk_texts):
        chunk_id = build_chunk_id(file_id, index, chunk_text)
        metadata = {
            "tenant_id": tenant_id,
            "project_id": project_id or "",
            "knowledge_base_id": knowledge_base_id or "",
            "knowledge_document_id": knowledge_document_id or "",
            "file_id": file_id,
            "doc_type": doc_type,
            "chunk_index": index,
        }
        chunks.append({"id": chunk_id, "text": chunk_text, "metadata": metadata})

    get_vector_store().upsert_chunks(chunks)
    conn = get_db()
    try:
        cursor = conn.cursor()
        for item in chunks:
            cursor.execute(
                """
                INSERT INTO document_chunks
                (chunk_uid, tenant_id, knowledge_base_id, knowledge_document_id, file_id, project_id,
                 doc_type, chunk_index, chunk_text, token_count, embedding_model, vector_collection,
                 vector_id, metadata_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, 'indexed', ?, ?)
                ON DUPLICATE KEY UPDATE
                    chunk_text = VALUES(chunk_text),
                    metadata_json = VALUES(metadata_json),
                    status = 'indexed',
                    updated_at = VALUES(updated_at)
                """,
                (
                    item["id"],
                    tenant_id,
                    knowledge_base_id,
                    knowledge_document_id,
                    file_id,
                    project_id,
                    doc_type,
                    item["metadata"]["chunk_index"],
                    item["text"],
                    EMBEDDING_MODEL,
                    VECTOR_COLLECTION,
                    item["id"],
                    json.dumps(item["metadata"], ensure_ascii=False),
                    now(),
                    now(),
                ),
            )
        cursor.execute("UPDATE document_files SET parse_status='parsed', vector_status='indexed', updated_at=? WHERE id=?", (now(), file_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"status": "success", "file_id": file_id, "total_chunks": len(chunks), "chunks": chunks}


def delete_document_vectors(document_id):
    conn = get_db()
    try:
        rows = conn.execute("SELECT chunk_uid FROM document_chunks WHERE file_id = ?", (document_id,)).fetchall()
        ids = [row["chunk_uid"] for row in rows]
        get_vector_store().delete(ids)
        conn.execute("UPDATE document_chunks SET status='deleted', updated_at=? WHERE file_id=?", (now(), document_id))
        conn.execute("UPDATE document_files SET vector_status='deleted', updated_at=? WHERE id=?", (now(), document_id))
        conn.commit()
        return {"deleted": len(ids)}
    finally:
        conn.close()


def search_documents(query, *, tenant_id=1, project_id=None, knowledge_base_id=None, doc_type=None, limit=5):
    return retrieval_router.search(
        query,
        tenant_id=tenant_id,
        project_id=project_id,
        knowledge_base_id=knowledge_base_id,
        doc_type=doc_type,
        limit=limit,
    )["items"]


def build_retrieval_context(query, *, project_id=None, limit=6):
    return retrieval_router.build_context(query, project_id=project_id, limit=limit)
