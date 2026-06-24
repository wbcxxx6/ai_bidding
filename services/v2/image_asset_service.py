import json
from datetime import datetime

from core.db import get_db


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def dumps(value):
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def loads(value, default):
    if not value:
        return default
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def create_image_asset(data):
    title = (data.get("assetTitle") or data.get("asset_title") or data.get("title") or "").strip()
    image_type = (data.get("imageType") or data.get("image_type") or "").strip()
    if not title:
        raise ValueError("assetTitle is required.")
    if not image_type:
        raise ValueError("imageType is required.")

    tags = data.get("tags") or data.get("tagsJson") or []
    searchable_text = data.get("searchableText") or data.get("searchable_text")
    caption = data.get("caption") or ""
    if not searchable_text:
        searchable_text = " ".join([title, caption, " ".join(tags if isinstance(tags, list) else [])]).strip()

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO image_asset
            (tenant_id, company_id, project_id, file_id, asset_title, image_type, source_type,
             caption, searchable_text, tags_json, allowed_for_bid, synthetic, review_status,
             metadata_json, created_by, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("companyId") or data.get("company_id"),
                data.get("projectId") or data.get("project_id"),
                data.get("fileId") or data.get("file_id"),
                title,
                image_type,
                data.get("sourceType") or data.get("source_type") or "enterprise_upload",
                caption,
                searchable_text,
                dumps(tags),
                1 if data.get("allowedForBid", data.get("allowed_for_bid", True)) else 0,
                1 if data.get("synthetic", False) else 0,
                data.get("reviewStatus") or data.get("review_status") or "approved",
                dumps(data.get("metadata") or {}),
                data.get("userId") or data.get("created_by"),
                now(),
                now(),
            ),
        )
        conn.commit()
        return get_image_asset(cursor.lastrowid)
    finally:
        conn.close()


def get_image_asset(asset_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM image_asset WHERE id=? AND deleted_at IS NULL", (asset_id,)).fetchone()
        return format_image_asset(row)
    finally:
        conn.close()


def update_image_asset_metadata(asset_id, metadata, *, review_status=None, allowed_for_bid=None):
    if not asset_id:
        raise ValueError("assetId is required.")
    assignments = ["metadata_json=?", "updated_at=?"]
    params = [dumps(metadata or {}), now()]
    if review_status:
        assignments.append("review_status=?")
        params.append(review_status)
    if allowed_for_bid is not None:
        assignments.append("allowed_for_bid=?")
        params.append(1 if allowed_for_bid else 0)
    params.append(asset_id)
    conn = get_db()
    try:
        conn.execute(
            f"UPDATE image_asset SET {', '.join(assignments)} WHERE id=? AND deleted_at IS NULL",
            tuple(params),
        )
        conn.commit()
        return get_image_asset(asset_id)
    finally:
        conn.close()


def list_image_assets(*, project_id=None, image_type=None, review_status=None, allowed_for_bid=None, limit=50):
    clauses = ["deleted_at IS NULL"]
    params = []
    if project_id:
        clauses.append("(project_id=? OR project_id IS NULL)")
        params.append(project_id)
    if image_type:
        clauses.append("image_type=?")
        params.append(image_type)
    if review_status:
        clauses.append("review_status=?")
        params.append(review_status)
    if allowed_for_bid is not None:
        clauses.append("allowed_for_bid=?")
        params.append(1 if allowed_for_bid else 0)
    params.append(limit)
    conn = get_db()
    try:
        rows = conn.execute(
            f"""
            SELECT * FROM image_asset
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [format_image_asset(row) for row in rows]
    finally:
        conn.close()


def format_image_asset(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "companyId": row.get("company_id"),
        "projectId": row.get("project_id"),
        "fileId": row.get("file_id"),
        "assetTitle": row.get("asset_title"),
        "imageType": row.get("image_type"),
        "sourceType": row.get("source_type"),
        "caption": row.get("caption"),
        "searchableText": row.get("searchable_text"),
        "tags": loads(row.get("tags_json"), []),
        "allowedForBid": bool(row.get("allowed_for_bid")),
        "synthetic": bool(row.get("synthetic")),
        "reviewStatus": row.get("review_status"),
        "metadata": loads(row.get("metadata_json"), {}),
        "createdBy": row.get("created_by"),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }
