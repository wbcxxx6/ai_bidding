import json
from datetime import datetime

from core.db import get_db
from services.agent_orchestrator import create_chapter_version


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def dumps(value):
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def loads(value):
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def get_editor_doc(chapter_id):
    conn = get_db()
    try:
        row = conn.execute(
            """
            SELECT * FROM chapter_editor_docs
            WHERE chapter_id=? AND status='active'
            ORDER BY version_no DESC LIMIT 1
            """,
            (chapter_id,),
        ).fetchone()
        if row:
            return {
                "chapterId": chapter_id,
                "projectId": row.get("project_id"),
                "markdown": row.get("markdown_content") or "",
                "tiptapJson": loads(row.get("tiptap_json")),
                "versionNo": row.get("version_no"),
            }
        version = conn.execute(
            """
            SELECT c.project_id, v.content
            FROM bid_chapters c
            LEFT JOIN bid_chapter_versions v ON v.id = c.current_version_id
            WHERE c.id=?
            """,
            (chapter_id,),
        ).fetchone()
        return {
            "chapterId": chapter_id,
            "projectId": (version or {}).get("project_id"),
            "markdown": (version or {}).get("content") or "",
            "tiptapJson": None,
            "versionNo": 0,
        }
    finally:
        conn.close()


def save_editor_doc(*, chapter_id, markdown, tiptap_json=None, created_by=None, sync_chapter_version=False, change_source="editor_save"):
    conn = get_db()
    try:
        chapter = conn.execute("SELECT id, project_id FROM bid_chapters WHERE id=?", (chapter_id,)).fetchone()
        if not chapter:
            raise ValueError(f"Chapter not found: {chapter_id}")
        row = conn.execute(
            "SELECT COALESCE(MAX(version_no), 0) AS max_version FROM chapter_editor_docs WHERE chapter_id=?",
            (chapter_id,),
        ).fetchone()
        version_no = int((row or {}).get("max_version") or 0) + 1
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chapter_editor_docs
            (tenant_id, project_id, chapter_id, version_no, markdown_content, tiptap_json, status,
             created_by, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (chapter["project_id"], chapter_id, version_no, markdown, dumps(tiptap_json), created_by, now(), now()),
        )
        conn.commit()
        doc_id = cursor.lastrowid
    finally:
        conn.close()

    chapter_version = None
    if sync_chapter_version:
        chapter_version = create_chapter_version(
            chapter_id=chapter_id,
            content=markdown,
            change_source=change_source,
        )
    return {
        "id": doc_id,
        "chapterId": chapter_id,
        "versionNo": version_no,
        "markdown": markdown,
        "chapterVersion": chapter_version,
    }
