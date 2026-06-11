import json
from datetime import datetime

from flask import Blueprint, jsonify, request

from core.db import get_db
from services.v2.citation_service import list_chapter_citations
from services.v2.editor_doc_service import get_editor_doc, save_editor_doc
from services.v2.followup_service import list_chapter_followups
from services.v2.image_plan_service import list_chapter_image_plans
from services.v2.workbench_service import get_project_workbench_overview


bp = Blueprint("v2_chapters", __name__, url_prefix="/chapters")


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


def _chapter_description(chapter):
    parts = [chapter.get("content") or chapter.get("description") or ""]
    for section in chapter.get("sections") or []:
        parts.append(section.get("title") or "")
        for subsection in section.get("subsections") or []:
            parts.append(subsection.get("title") or "")
            parts.append(subsection.get("describe") or "")
    return "\n".join(part for part in parts if part)


def _normalise_outline(raw):
    outline = loads(raw) if isinstance(raw, str) else raw
    if not outline:
        return []
    if isinstance(outline, dict):
        return outline.get("chapters") or []
    if isinstance(outline, list):
        return outline
    return []


def _materialize_project_chapters(project_id):
    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM bid_chapters WHERE project_id=? LIMIT 1", (project_id,)).fetchone()
        if existing:
            return
        project = conn.execute("SELECT * FROM bid_projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        chapters = _normalise_outline(project.get("directory_structure"))
        if not chapters:
            return
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO bid_documents
            (tenant_id, project_id, document_title, status, created_by, created_at, updated_at)
            VALUES (1, ?, ?, 'draft', NULL, ?, ?)
            """,
            (project_id, f"{project.get('project_name') or '投标文件'} - V2 工作台", now(), now()),
        )
        bid_document_id = cursor.lastrowid
        for index, chapter in enumerate(chapters):
            cursor.execute(
                """
                INSERT INTO bid_chapters
                (tenant_id, bid_document_id, project_id, chapter_title, chapter_type, sort_order,
                 outline_json, status, created_at, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, 'planned', ?, ?)
                """,
                (
                    bid_document_id,
                    project_id,
                    chapter.get("title") or f"章节 {index + 1}",
                    chapter.get("type") or "normal",
                    index,
                    dumps({**chapter, "description": _chapter_description(chapter)}),
                    now(),
                    now(),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _format_chapter(row):
    outline = loads(row.get("outline_json")) or {}
    return {
        "id": row["id"],
        "projectId": row.get("project_id"),
        "bidDocumentId": row.get("bid_document_id"),
        "parentChapterId": row.get("parent_chapter_id"),
        "title": row.get("chapter_title"),
        "type": row.get("chapter_type"),
        "sortOrder": row.get("sort_order"),
        "status": row.get("status"),
        "currentVersionId": row.get("current_version_id"),
        "outline": outline,
        "description": outline.get("description") or _chapter_description(outline),
    }


@bp.route("", methods=["GET"])
def list_chapters():
    project_id = request.args.get("projectId") or request.args.get("project_id")
    if not project_id:
        return jsonify({"error": "projectId is required."}), 400
    try:
        _materialize_project_chapters(int(project_id))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT * FROM bid_chapters
            WHERE project_id=?
            ORDER BY sort_order ASC, id ASC
            """,
            (int(project_id),),
        ).fetchall()
        return jsonify({"items": [_format_chapter(row) for row in rows]})
    finally:
        conn.close()


@bp.route("/workbench", methods=["GET"])
def workbench_overview():
    project_id = request.args.get("projectId") or request.args.get("project_id")
    if not project_id:
        return jsonify({"error": "projectId is required."}), 400
    try:
        _materialize_project_chapters(int(project_id))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(get_project_workbench_overview(int(project_id)))


@bp.route("/<int:chapter_id>/editor-doc", methods=["GET"])
def read_editor_doc(chapter_id):
    return jsonify(get_editor_doc(chapter_id))


@bp.route("/<int:chapter_id>/editor-doc", methods=["PUT"])
def write_editor_doc(chapter_id):
    data = request.get_json(silent=True) or {}
    markdown = data.get("markdown")
    if markdown is None:
        return jsonify({"error": "markdown is required."}), 400
    saved = save_editor_doc(
        chapter_id=chapter_id,
        markdown=markdown,
        tiptap_json=data.get("tiptapJson") or data.get("tiptap_json"),
        created_by=data.get("userId") or data.get("user_id"),
        sync_chapter_version=True,
    )
    return jsonify(saved)


@bp.route("/<int:chapter_id>/citations", methods=["GET"])
def chapter_citations(chapter_id):
    return jsonify({"items": list_chapter_citations(chapter_id)})


@bp.route("/<int:chapter_id>/image-plans", methods=["GET"])
def chapter_image_plans(chapter_id):
    return jsonify({"items": list_chapter_image_plans(chapter_id)})


@bp.route("/<int:chapter_id>/followups", methods=["GET"])
def chapter_followups(chapter_id):
    return jsonify({"items": list_chapter_followups(chapter_id)})
