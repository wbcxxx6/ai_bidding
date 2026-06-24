import json
from datetime import datetime

from core.db import get_db


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def dumps(value):
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def _format(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "projectId": row.get("project_id"),
        "chapterId": row.get("chapter_id"),
        "taskId": row.get("task_id"),
        "citationKey": row.get("citation_key"),
        "sourceType": row.get("source_type"),
        "sourceFileId": row.get("source_file_id"),
        "chunkId": row.get("chunk_id"),
        "chunkUid": row.get("chunk_uid"),
        "sourceTitle": row.get("source_title"),
        "quoteText": row.get("quote_text"),
        "usageType": row.get("usage_type"),
        "metadata": json.loads(row["metadata_json"]) if row.get("metadata_json") else {},
    }


def create_citation_records(task, context_items):
    records = []
    if not context_items:
        return records
    conn = get_db()
    try:
        cursor = conn.cursor()
        for index, item in enumerate(context_items, start=1):
            citation_key = f"CIT-{index:03d}"
            metadata = {
                "similarity": item.get("similarity"),
                "distance": item.get("distance"),
                "reusePolicy": item.get("reuse_policy"),
                "knowledgeBaseId": item.get("knowledge_base_id"),
                "knowledgeDocumentId": item.get("knowledge_document_id"),
            }
            cursor.execute(
                """
                INSERT INTO citation_record
                (tenant_id, project_id, chapter_id, task_id, citation_key, source_type, source_file_id,
                 chunk_id, chunk_uid, source_title, quote_text, usage_type, metadata_json, status, created_at, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'prompt_evidence', ?, 'active', ?, ?)
                """,
                (
                    task["projectId"],
                    task.get("chapterId"),
                    task["id"],
                    citation_key,
                    item.get("doc_type") or "knowledge_chunk",
                    item.get("file_id"),
                    item.get("chunk_id"),
                    item.get("chunk_uid"),
                    item.get("source_title"),
                    (item.get("content") or "")[:1200],
                    dumps(metadata),
                    now(),
                    now(),
                ),
            )
            records.append(
                {
                    "citationKey": citation_key,
                    "sourceTitle": item.get("source_title"),
                    "sourceType": item.get("doc_type") or "knowledge_chunk",
                    "quoteText": (item.get("content") or "")[:1200],
                    "metadata": metadata,
                }
            )
        conn.commit()
        return records
    finally:
        conn.close()


def list_chapter_citations(chapter_id):
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT * FROM citation_record
            WHERE chapter_id=? AND status='active'
            ORDER BY id ASC
            """,
            (chapter_id,),
        ).fetchall()
        return [_format(row) for row in rows]
    finally:
        conn.close()
