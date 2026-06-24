from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from openai import AuthenticationError

from core.db import get_db
from services.ingestion_service import delete_document_vectors, ingest_document
from services.retrieval_router import retrieval_router
from storage.storage_service import BlobTooLarge, FileTypeNotAllowed, StorageError, storage_service


bp = Blueprint("knowledge", __name__)


def _now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _as_int(value):
    return int(value or 0)


def _pipeline_status(total, done, failed=0):
    total = _as_int(total)
    done = _as_int(done)
    failed = _as_int(failed)
    if failed:
        return "failed" if failed >= total and total else "partial"
    if total == 0:
        return "empty"
    if done >= total:
        return "success"
    if done > 0:
        return "partial"
    return "pending"


def _process_summary(row):
    document_count = _as_int(row.get("documentCount"))
    failed_count = _as_int(row.get("failedCount"))
    parsed_count = _as_int(row.get("parsedCount"))
    vectorized_count = _as_int(row.get("vectorizedCount"))
    return {
        "documentCount": document_count,
        "chunkCount": _as_int(row.get("chunkCount")),
        "parsedCount": parsed_count,
        "vectorizedCount": vectorized_count,
        "failedCount": failed_count,
        "parseStatus": _pipeline_status(document_count, parsed_count, failed_count),
        "vectorStatus": _pipeline_status(document_count, vectorized_count, failed_count),
    }


def _with_summary(row):
    item = dict(row)
    summary = _process_summary(item)
    item.update(
        {
            "documentCount": summary["documentCount"],
            "chunkCount": summary["chunkCount"],
            "parsedCount": summary["parsedCount"],
            "vectorizedCount": summary["vectorizedCount"],
            "failedCount": summary["failedCount"],
            "processSummary": summary,
        }
    )
    return item


def _step_status(value, success_values):
    if value in success_values:
        return "success"
    if value == "failed":
        return "error"
    if value in {"parsing", "indexing", "processing"}:
        return "process"
    return "wait"


def _document_pipeline(row):
    parse_status = row.get("parseStatus")
    vector_status = row.get("vectorStatus")
    return [
        {"key": "uploaded", "label": "已上传", "status": "success"},
        {"key": "parsed", "label": "文本解析", "status": _step_status(parse_status, {"parsed"})},
        {"key": "vectorized", "label": "向量化", "status": _step_status(vector_status, {"indexed"})},
        {
            "key": "stored",
            "label": "入库可检索",
            "status": "success" if vector_status == "indexed" and _as_int(row.get("chunkCount")) > 0 else _step_status(vector_status, {"indexed"}),
        },
    ]


def _knowledge_base_select(where_clause, order_clause=""):
    return f"""
            SELECT kb.id, kb.kb_name AS kbName, kb.kb_type AS kbType, kb.description,
                   kb.visibility_scope AS visibilityScope, kb.status,
                   kb.created_at AS createdAt, kb.updated_at AS updatedAt,
                   COUNT(DISTINCT kd.id) AS documentCount,
                   COUNT(dc.id) AS chunkCount,
                   COUNT(DISTINCT CASE WHEN df.parse_status = 'parsed' THEN kd.id END) AS parsedCount,
                   COUNT(DISTINCT CASE WHEN df.vector_status = 'indexed' THEN kd.id END) AS vectorizedCount,
                   COUNT(DISTINCT CASE WHEN df.parse_status = 'failed' OR df.vector_status = 'failed' THEN kd.id END) AS failedCount
            FROM knowledge_bases kb
            LEFT JOIN knowledge_documents kd
              ON kd.knowledge_base_id = kb.id AND kd.deleted_at IS NULL
            LEFT JOIN document_files df
              ON df.id = kd.file_id
            LEFT JOIN document_chunks dc
              ON dc.knowledge_document_id = kd.id AND dc.status <> 'deleted'
            {where_clause}
            GROUP BY kb.id, kb.kb_name, kb.kb_type, kb.description, kb.visibility_scope,
                     kb.status, kb.created_at, kb.updated_at
            {order_clause}
            """


@bp.route("/knowledge-bases", methods=["POST"])
def create_knowledge_base():
    data = request.get_json(silent=True) or {}
    kb_name = data.get("kbName") or data.get("kb_name")
    if not kb_name:
        return jsonify({"error": "kbName is required."}), 400
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO knowledge_bases
            (tenant_id, company_id, kb_name, kb_type, description, visibility_scope, status, created_by, created_at, updated_at)
            VALUES (1, 1, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                kb_name,
                data.get("kbType") or data.get("kb_type") or "enterprise",
                data.get("description"),
                data.get("visibilityScope") or data.get("visibility_scope") or "tenant",
                data.get("userId"),
                _now(),
                _now(),
            ),
        )
        kb_id = cursor.lastrowid
        conn.commit()
        return jsonify({"id": kb_id, "kbName": kb_name}), 201
    finally:
        conn.close()


@bp.route("/knowledge-bases", methods=["GET"])
def list_knowledge_bases():
    conn = get_db()
    try:
        rows = conn.execute(
            _knowledge_base_select(
                "WHERE kb.tenant_id = 1 AND kb.deleted_at IS NULL",
                "ORDER BY kb.id DESC",
            )
        ).fetchall()
        return jsonify({"items": [_with_summary(row) for row in rows]})
    finally:
        conn.close()


@bp.route("/knowledge-bases/<int:kb_id>", methods=["GET"])
def get_knowledge_base(kb_id):
    conn = get_db()
    try:
        row = conn.execute(
            _knowledge_base_select("WHERE kb.id = ? AND kb.tenant_id = 1 AND kb.deleted_at IS NULL"),
            (kb_id,),
        ).fetchone()
        if not row:
            return jsonify({"error": "Knowledge base not found."}), 404
        kb = _with_summary(row)
        documents = conn.execute(
            """
            SELECT kd.id AS knowledgeDocumentId, kd.file_id AS documentId, kd.doc_title AS docTitle,
                   kd.doc_type AS docType, kd.reuse_policy AS reusePolicy, kd.review_status AS reviewStatus,
                   df.original_filename AS originalFilename, df.file_size AS fileSize,
                   df.parse_status AS parseStatus, df.vector_status AS vectorStatus,
                   COUNT(dc.id) AS chunkCount,
                   MAX(dc.embedding_model) AS embeddingModel,
                   MAX(dc.vector_collection) AS vectorCollection,
                   kd.created_at AS createdAt, kd.updated_at AS updatedAt
            FROM knowledge_documents kd
            LEFT JOIN document_files df ON df.id = kd.file_id
            LEFT JOIN document_chunks dc ON dc.knowledge_document_id = kd.id AND dc.status <> 'deleted'
            WHERE kd.knowledge_base_id = ? AND kd.tenant_id = 1 AND kd.deleted_at IS NULL
            GROUP BY kd.id, kd.file_id, kd.doc_title, kd.doc_type, kd.reuse_policy, kd.review_status,
                     df.original_filename, df.file_size, df.parse_status, df.vector_status,
                     kd.created_at, kd.updated_at
            ORDER BY kd.id DESC
            """,
            (kb_id,),
        ).fetchall()
        return jsonify(
            {
                "kb": {key: value for key, value in kb.items() if key != "processSummary"},
                "summary": kb["processSummary"],
                "documents": [{**dict(row), "chunkCount": _as_int(row.get("chunkCount")), "pipelineSteps": _document_pipeline(row)} for row in documents],
            }
        )
    finally:
        conn.close()


@bp.route("/knowledge-bases/<int:kb_id>/documents", methods=["POST"])
def upload_knowledge_document(kb_id):
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400
    file = request.files["file"]
    user_id = int(request.form.get("userId") or 1)
    doc_type = request.form.get("docType") or "history_bid"
    if not file.filename:
        return jsonify({"error": "No file selected."}), 400

    content_bytes = file.read()

    conn = get_db()
    try:
        cursor = conn.cursor()
        stored = storage_service.create_file(
            content_bytes=content_bytes,
            original_filename=file.filename,
            file_category="enterprise_history_bid" if doc_type == "history_bid" else "knowledge_document",
            owner_user_id=user_id,
            change_source="upload",
        )
        cursor.execute(
            """
            INSERT INTO knowledge_documents
            (tenant_id, knowledge_base_id, file_id, doc_title, doc_type, industry, tags_json,
             source_project_name, source_customer_name, bid_result, reuse_policy, review_status,
             created_at, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                kb_id,
                stored.file_id,
                request.form.get("docTitle") or file.filename,
                doc_type,
                request.form.get("industry"),
                request.form.get("tagsJson"),
                request.form.get("sourceProjectName"),
                request.form.get("sourceCustomerName"),
                request.form.get("bidResult"),
                request.form.get("reusePolicy") or "rewrite_required",
                request.form.get("reviewStatus") or "approved",
                _now(),
                _now(),
            ),
        )
        knowledge_document_id = cursor.lastrowid
        conn.commit()
    except FileTypeNotAllowed as exc:
        return jsonify({"error": str(exc)}), 400
    except BlobTooLarge as exc:
        return jsonify({"error": str(exc)}), 413
    finally:
        conn.close()

    try:
        result = ingest_document(
            file_id=stored.file_id,
            doc_type=doc_type,
            knowledge_base_id=kb_id,
            knowledge_document_id=knowledge_document_id,
        )
    except AuthenticationError:
        conn = get_db()
        try:
            conn.execute("UPDATE document_files SET vector_status='failed', updated_at=? WHERE id=?", (_now(), stored.file_id))
            conn.commit()
        finally:
            conn.close()
        return jsonify({"error": "Embedding API key is invalid or missing.", "documentId": stored.file_id}), 502
    return jsonify({"documentId": stored.file_id, "knowledgeDocumentId": knowledge_document_id, "ingest": result}), 201


@bp.route("/projects/<int:project_id>/documents", methods=["POST"])
def upload_project_document(project_id):
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected."}), 400

    user_id = int(request.form.get("userId") or 1)
    doc_type = request.form.get("docType") or "tender_original"
    content_bytes = file.read()

    conn = get_db()
    try:
        project = conn.execute("SELECT id FROM bid_projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": "Project not found."}), 404
        stored = storage_service.create_file(
            content_bytes=content_bytes,
            original_filename=file.filename,
            file_category=doc_type,
            owner_user_id=user_id,
            project_id=project_id,
            change_source="upload",
        )
    except FileTypeNotAllowed as exc:
        return jsonify({"error": str(exc)}), 400
    except BlobTooLarge as exc:
        return jsonify({"error": str(exc)}), 413
    finally:
        conn.close()

    try:
        result = ingest_document(file_id=stored.file_id, doc_type=doc_type, project_id=project_id)
    except AuthenticationError:
        conn = get_db()
        try:
            conn.execute("UPDATE document_files SET vector_status='failed', updated_at=? WHERE id=?", (_now(), stored.file_id))
            conn.commit()
        finally:
            conn.close()
        return jsonify({"error": "Embedding API key is invalid or missing.", "documentId": stored.file_id}), 502
    return jsonify({"documentId": stored.file_id, "ingest": result}), 201


@bp.route("/documents/<int:document_id>/ingest", methods=["POST"])
def ingest_existing_document(document_id):
    row = None
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM document_files WHERE id = ?", (document_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "Document not found."}), 404
    result = ingest_document(
        file_id=row["id"],
        doc_type=row["file_category"],
        project_id=row.get("project_id"),
    )
    return jsonify(result)


@bp.route("/documents/<int:document_id>/chunks", methods=["GET"])
def list_document_chunks(document_id):
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT id, chunk_uid AS chunkUid, doc_type AS docType, chunk_index AS chunkIndex,
                   LEFT(chunk_text, 500) AS preview, status, created_at AS createdAt
            FROM document_chunks
            WHERE file_id = ?
            ORDER BY chunk_index
            """,
            (document_id,),
        ).fetchall()
        return jsonify({"items": rows})
    finally:
        conn.close()


@bp.route("/documents/<int:document_id>", methods=["DELETE"])
def delete_document(document_id):
    result = delete_document_vectors(document_id)
    return jsonify({"message": "Document vectors deleted.", **result})


@bp.route("/knowledge/search", methods=["POST"])
def search_knowledge():
    data = request.get_json(silent=True) or {}
    query = data.get("query")
    if not query:
        return jsonify({"error": "query is required."}), 400
    try:
        pack = retrieval_router.search(
            query,
            project_id=data.get("projectId"),
            knowledge_base_id=data.get("knowledgeBaseId"),
            doc_type=data.get("docType"),
            limit=int(data.get("limit") or 5),
        )
        return jsonify({
            "items": pack["items"],
            "degraded": pack["degraded"],
            "degradedReason": pack["degraded_reason"],
            "fallbackUsed": pack["fallback_used"],
            "backend": pack.get("backend"),
            "retrievalLogId": pack.get("retrieval_log_id"),
            "sourceMix": pack.get("source_mix"),
            "scoreTrace": pack.get("score_trace"),
        })
    except AuthenticationError:
        return jsonify({"error": "Embedding API key is invalid or missing."}), 502
