import json
from datetime import datetime

from core.db import get_db


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


def _format_task(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "tenantId": row.get("tenant_id"),
        "projectId": row.get("project_id"),
        "bidDocumentId": row.get("bid_document_id"),
        "chapterId": row.get("chapter_id"),
        "parentTaskId": row.get("parent_task_id"),
        "taskType": row.get("task_type"),
        "status": row.get("status"),
        "input": loads(row.get("input_json")),
        "output": loads(row.get("output_json")),
        "errorMessage": row.get("error_message"),
        "startedAt": row.get("started_at"),
        "finishedAt": row.get("finished_at"),
        "createdBy": row.get("created_by"),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }


def _format_event(row):
    if not row:
        return None
    payload = loads(row.get("payload_json")) or {}
    return {
        "id": row["id"],
        "taskId": row.get("task_id"),
        "projectId": row.get("project_id"),
        "chapterId": row.get("chapter_id"),
        "type": row.get("event_type"),
        "eventIndex": row.get("event_index"),
        "payload": payload,
        "message": row.get("message"),
        "createdAt": row.get("created_at"),
    }


def create_task(*, project_id, task_type, chapter_id=None, bid_document_id=None, input_json=None, created_by=None):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agent_task
            (tenant_id, project_id, bid_document_id, chapter_id, task_type, status, input_json,
             created_by, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)
            """,
            (project_id, bid_document_id, chapter_id, task_type, dumps(input_json), created_by, now(), now()),
        )
        task_id = cursor.lastrowid
        conn.commit()
        return get_task(task_id)
    finally:
        conn.close()


def get_task(task_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM agent_task WHERE id=?", (task_id,)).fetchone()
        return _format_task(row)
    finally:
        conn.close()


def update_task(task_id, *, status=None, output_json=None, error_message=None, started=False, finished=False):
    fields = ["updated_at=?"]
    params = [now()]
    if status is not None:
        fields.append("status=?")
        params.append(status)
    if output_json is not None:
        fields.append("output_json=?")
        params.append(dumps(output_json))
    if error_message is not None:
        fields.append("error_message=?")
        params.append(error_message)
    if started:
        fields.append("started_at=?")
        params.append(now())
    if finished:
        fields.append("finished_at=?")
        params.append(now())
    params.append(task_id)
    conn = get_db()
    try:
        conn.execute(f"UPDATE agent_task SET {', '.join(fields)} WHERE id=?", tuple(params))
        conn.commit()
        return get_task(task_id)
    finally:
        conn.close()


def append_event(task_id, event_type, payload=None, message=None):
    task = get_task(task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")
    conn = get_db()
    try:
        cursor = conn.cursor()
        row = conn.execute(
            "SELECT COALESCE(MAX(event_index), 0) AS max_index FROM agent_task_event WHERE task_id=?",
            (task_id,),
        ).fetchone()
        event_index = int((row or {}).get("max_index") or 0) + 1
        cursor.execute(
            """
            INSERT INTO agent_task_event
            (tenant_id, task_id, project_id, chapter_id, event_type, event_index, payload_json, message, created_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                task["projectId"],
                task.get("chapterId"),
                event_type,
                event_index,
                dumps(payload or {}),
                message,
                now(),
            ),
        )
        conn.commit()
        return _format_event(conn.execute("SELECT * FROM agent_task_event WHERE id=?", (cursor.lastrowid,)).fetchone())
    finally:
        conn.close()


def list_events(task_id, *, after_id=None, limit=200):
    clauses = ["task_id=?"]
    params = [task_id]
    if after_id:
        clauses.append("id>?")
        params.append(after_id)
    params.append(limit)
    conn = get_db()
    try:
        rows = conn.execute(
            f"""
            SELECT * FROM agent_task_event
            WHERE {' AND '.join(clauses)}
            ORDER BY event_index ASC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [_format_event(row) for row in rows]
    finally:
        conn.close()
