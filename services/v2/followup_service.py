import json
from datetime import datetime

from core.db import get_db


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def dumps(value):
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def build_followup_questions(*, chapter, context_items=None, image_plans=None):
    title = chapter.get("title") or chapter.get("chapter_title") or "当前章节"
    questions = []
    if not context_items:
        questions.append(
            {
                "question": f"{title} 暂未检索到可引用的企业、产品或历史标书资料，请上传相关知识库材料或确认本章仅输出待补充提示。",
                "reason": "missing_context",
                "action": "upload_knowledge",
                "severity": "warning",
                "status": "pending",
            }
        )
    for plan in image_plans or []:
        if plan.get("status") in {"ready", "selected"}:
            continue
        questions.append(
            {
                "question": f"{title} 需要“{plan.get('caption') or plan.get('imageType')}”，但图片资产库尚未命中可用图片，请上传图片资产或允许后续生成占位示意图。",
                "reason": "missing_image_asset",
                "action": "upload_image_asset",
                "severity": "warning",
                "status": "pending",
                "metadata": {
                    "imageType": plan.get("imageType"),
                    "caption": plan.get("caption"),
                },
            }
        )
    return questions


def save_followup_questions(project_id, chapter_id, questions, *, task_id=None):
    if not questions:
        return []
    conn = get_db()
    saved = []
    try:
        cursor = conn.cursor()
        for question in questions:
            cursor.execute(
                """
                INSERT INTO followup_question
                (tenant_id, project_id, chapter_id, task_id, question_text, reason_code,
                 action_type, severity, status, metadata_json, created_at, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    chapter_id,
                    task_id,
                    question.get("question"),
                    question.get("reason"),
                    question.get("action"),
                    question.get("severity") or "warning",
                    question.get("status") or "pending",
                    dumps(question.get("metadata") or {}),
                    now(),
                    now(),
                ),
            )
            saved.append({**question, "id": cursor.lastrowid})
        conn.commit()
        return saved
    finally:
        conn.close()


def list_chapter_followups(chapter_id):
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT * FROM followup_question
            WHERE chapter_id=?
            ORDER BY FIELD(status, 'pending', 'ignored', 'resolved'), id ASC
            """,
            (chapter_id,),
        ).fetchall()
        return [_format_row(row) for row in rows]
    finally:
        conn.close()


def _loads(value, default):
    if not value:
        return default
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _format_row(row):
    return {
        "id": row["id"],
        "projectId": row.get("project_id"),
        "chapterId": row.get("chapter_id"),
        "taskId": row.get("task_id"),
        "question": row.get("question_text"),
        "reason": row.get("reason_code"),
        "action": row.get("action_type"),
        "severity": row.get("severity"),
        "status": row.get("status"),
        "metadata": _loads(row.get("metadata_json"), {}),
    }
