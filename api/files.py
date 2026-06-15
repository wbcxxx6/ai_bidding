from io import BytesIO
from urllib.parse import quote

from flask import Blueprint, jsonify, request, send_file

from core.db import get_db
from storage.storage_service import StorageError, storage_service


bp = Blueprint("files", __name__)


def _overall_status(row):
    parse_status = row.get("parse_status")
    vector_status = row.get("vector_status")
    business_status = row.get("business_status")
    task_status = row.get("latest_task_status")
    if parse_status == "failed" or vector_status == "failed" or task_status == "failed":
        return "failed"
    if business_status in {"Generated", "Edited"}:
        return "completed"
    if parse_status == "parsed" and vector_status in {"indexed", "deleted"}:
        return "completed"
    if task_status in {"running", "pending"} or parse_status == "pending" or vector_status == "pending":
        return "processing"
    if business_status in {"Uploaded"}:
        return "uploaded"
    return "unknown"


def _status_label(status):
    return {
        "completed": "已完成",
        "processing": "处理中",
        "uploaded": "已上传",
        "failed": "失败",
        "interrupted": "中断",
        "unknown": "未知",
    }.get(status, status)


def _history_row(row):
    overall_status = _overall_status(row)
    return {
        "fileId": row["id"],
        "projectId": row.get("project_id"),
        "projectName": row.get("project_name"),
        "ownerUserId": row.get("owner_user_id"),
        "category": row.get("file_category"),
        "originalFilename": row.get("original_filename"),
        "fileExt": row.get("file_ext"),
        "mimeType": row.get("mime_type"),
        "fileSize": row.get("file_size"),
        "sha256": row.get("sha256_hash"),
        "storageBucket": row.get("storage_bucket"),
        "parseStatus": row.get("parse_status"),
        "vectorStatus": row.get("vector_status"),
        "businessStatus": row.get("business_status"),
        "latestTaskStatus": row.get("latest_task_status"),
        "overallStatus": overall_status,
        "statusLabel": _status_label(overall_status),
        "versionCount": row.get("version_count") or 0,
        "latestVersionNo": row.get("latest_version_no"),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
        "downloadUrl": f"/api/files/{row['id']}/download",
    }


def _send_blob(row):
    filename = row["original_filename"]
    mime = row.get("mime_type") or "application/octet-stream"
    if filename.endswith(".docx"):
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif filename.endswith(".pdf"):
        mime = "application/pdf"
    elif filename.endswith(".md"):
        mime = "text/markdown"
    return send_file(
        BytesIO(row["content"]),
        mimetype=mime,
        as_attachment=False,
        download_name=filename,
    )


@bp.route("/files/<int:file_id>/download", methods=["GET"])
def download_file(file_id):
    try:
        return _send_blob(storage_service.get_latest(file_id))
    except StorageError as exc:
        return jsonify({"error": str(exc)}), 404


def _file_history_response(user_id=None):
    user_id = user_id or request.args.get("userId", type=int)
    project_id = request.args.get("projectId", type=int)
    category = request.args.get("category")
    status = request.args.get("status")
    limit = min(request.args.get("limit", default=50, type=int), 200)
    offset = request.args.get("offset", default=0, type=int)

    clauses = ["f.deleted_at IS NULL"]
    params = []
    if user_id:
        clauses.append("f.owner_user_id = ?")
        params.append(user_id)
    if project_id:
        clauses.append("f.project_id = ?")
        params.append(project_id)
    if category:
        clauses.append("f.file_category = ?")
        params.append(category)

    where_sql = " AND ".join(clauses)
    conn = get_db()
    try:
        rows = conn.execute(
            f"""
            SELECT
                f.*,
                p.project_name,
                b.status AS business_status,
                gt.status AS latest_task_status,
                COUNT(DISTINCT v.id) AS version_count,
                MAX(v.version_no) AS latest_version_no
            FROM document_files f
            LEFT JOIN bid_projects p ON p.id = f.project_id
            LEFT JOIN bidding b ON b.file_id = f.id OR b.generated_file_id = f.id
            LEFT JOIN generation_tasks gt ON gt.project_id = f.project_id
                AND gt.id = (
                    SELECT gt2.id
                    FROM generation_tasks gt2
                    WHERE gt2.project_id = f.project_id
                    ORDER BY gt2.id DESC
                    LIMIT 1
                )
            LEFT JOIN document_versions v ON v.file_id = f.id
            WHERE {where_sql}
            GROUP BY f.id, p.project_name, b.status, gt.status
            ORDER BY f.created_at DESC, f.id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [limit, offset]),
        ).fetchall()
        items = [_history_row(row) for row in rows]
        if status:
            items = [item for item in items if item["overallStatus"] == status]
        total_row = conn.execute(
            f"SELECT COUNT(*) AS total FROM document_files f WHERE {where_sql}",
            tuple(params),
        ).fetchone()
        return jsonify(
            {
                "items": items,
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "total": total_row["total"] if total_row else len(items),
                },
                "filters": {
                    "userId": user_id,
                    "projectId": project_id,
                    "category": category,
                    "status": status,
                },
            }
        )
    finally:
        conn.close()


@bp.route("/files/history", methods=["GET"])
def file_history():
    return _file_history_response()


@bp.route("/users/<int:user_id>/files/history", methods=["GET"])
def user_file_history(user_id):
    return _file_history_response(user_id=user_id)


@bp.route("/files/<int:file_id>/versions/<int:version_no>/download", methods=["GET"])
def download_file_version(file_id, version_no):
    try:
        return _send_blob(storage_service.get_version(file_id=file_id, version_no=version_no))
    except StorageError as exc:
        return jsonify({"error": str(exc)}), 404


@bp.route("/outputs/<path:filename>", methods=["GET"])
def legacy_output_download(filename):
    row = storage_service.find_latest_by_filename(filename)
    if not row:
        return jsonify({"error": "File not found."}), 404
    return _send_blob(row)
