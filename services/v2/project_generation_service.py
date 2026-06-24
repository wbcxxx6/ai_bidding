import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from core.db import get_db
from export.md_to_word import convert_md_to_word
from services.agent_orchestrator import word_count
from services.v2.agent_task_service import append_event, create_task, get_task, list_events, update_task
from services.v2.chapter_generation_service import run_chapter_generation
from storage.storage_service import storage_service


LOGGER = logging.getLogger(__name__)


def now():
    from datetime import datetime

    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


def loads(value):
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _emit(task_id, event_type, payload=None, message=None):
    event = append_event(task_id, event_type, payload or {}, message)
    return {"type": event_type, **(payload or {}), "eventId": event["id"], "message": message}


def _load_project(project_id):
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM bid_projects WHERE id=?", (project_id,)).fetchone()
    finally:
        conn.close()


def _load_latest_bidding(project_id):
    conn = get_db()
    try:
        return conn.execute(
            """
            SELECT * FROM bidding
            WHERE project_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
    finally:
        conn.close()


def _load_chapters(project_id):
    conn = get_db()
    try:
        doc = conn.execute(
            """
            SELECT id
            FROM bid_documents
            WHERE project_id=? AND deleted_at IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        bid_document_id = (doc or {}).get("id")
        if not bid_document_id:
            return []
        return conn.execute(
            """
            SELECT c.*, v.content AS current_content
            FROM bid_chapters c
            LEFT JOIN bid_chapter_versions v ON v.id = c.current_version_id
            WHERE c.project_id=? AND c.bid_document_id=?
            ORDER BY c.sort_order ASC, c.id ASC
            """,
            (project_id, bid_document_id),
        ).fetchall()
    finally:
        conn.close()


def _merge_sections(chapters):
    parts = []
    for index, chapter in enumerate(chapters, start=1):
        title = chapter.get("chapter_title") or f"章节 {index}"
        content = (chapter.get("current_content") or "").strip()
        if not content:
            content = f"## {title}\n\n待补充。"
        if content.startswith("#"):
            parts.append(f"{content}\n")
        else:
            parts.append(f"## 第{index}章 {title}\n\n{content}\n")
    return "\n".join(parts).strip()


def _load_project_facts(project_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT fact_key, fact_value FROM project_facts WHERE project_id=? ORDER BY id ASC",
            (project_id,),
        ).fetchall()
        return {row["fact_key"]: row.get("fact_value") for row in rows}
    finally:
        conn.close()


def _load_cover_data(project_id):
    project = _load_project(project_id)
    try:
        analysis_data = loads((project or {}).get("analysis_data")) or {}
    except Exception:
        analysis_data = {}
    bid_document_format = analysis_data.get("bid_document_format") or {}
    return bid_document_format.get("cover_page")


def _store_document_version(*, bid_document_id, file_id, markdown_storage_key=None, created_by=None, change_summary=None):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(version_no), 0) AS max_version FROM bid_document_versions WHERE bid_document_id=?",
            (bid_document_id,),
        ).fetchone()
        version_no = int((row or {}).get("max_version") or 0) + 1
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO bid_document_versions
            (tenant_id, bid_document_id, version_no, file_id, markdown_storage_key, change_summary, created_by, created_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?)
            """,
            (bid_document_id, version_no, file_id, markdown_storage_key, change_summary, created_by, now()),
        )
        version_id = cursor.lastrowid
        conn.execute(
            "UPDATE bid_documents SET current_version_id=?, status='generated', updated_at=? WHERE id=?",
            (version_id, now(), bid_document_id),
        )
        conn.commit()
        return {"id": version_id, "versionNo": version_no}
    finally:
        conn.close()


def _mark_project_exported(project_id, *, generated_file_id=None):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE bid_projects SET project_status='completed', updated_at=? WHERE id=?",
            (now(), project_id),
        )
        bidding = conn.execute(
            "SELECT id FROM bidding WHERE project_id=? ORDER BY id DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        if bidding:
            conn.execute(
                """
                UPDATE bidding
                SET status=?, generated_file_id=?, bid_document=?, document_key=COALESCE(document_key, ?)
                WHERE id=?
                """,
                (
                    "Generated",
                    generated_file_id,
                    f"/api/files/{generated_file_id}/download" if generated_file_id else None,
                    f"gen-{project_id}",
                    bidding["id"],
                ),
            )
        conn.commit()
    finally:
        conn.close()


def create_project_task(*, project_id, created_by=None, include_existing=False):
    return create_task(
        project_id=project_id,
        task_type="project_generate",
        input_json={"includeExisting": bool(include_existing)},
        created_by=created_by,
    )


def create_export_task(*, project_id, created_by=None):
    return create_task(
        project_id=project_id,
        task_type="project_export",
        input_json={},
        created_by=created_by,
    )


def _start_child_task(task_id):
    update_task(task_id, status="running", started=True)


def run_project_export(task_id):
    task = get_task(task_id)
    if not task:
        yield {"type": "error", "error": "Task not found."}
        return
    if task.get("taskType") != "project_export":
        yield {"type": "error", "error": "Only project_export is supported here."}
        return
    if task.get("status") in ("succeeded", "failed", "cancelled"):
        for event in list_events(task_id):
            payload = event.get("payload") or {}
            yield {"type": event.get("type"), **payload, "eventId": event.get("id"), "message": event.get("message")}
        return
    if task.get("status") == "running":
        yield {"type": "error", "error": "Task is already running."}
        return

    try:
        update_task(task_id, status="running", started=True)
        yield _emit(task_id, "start", {"taskId": task_id, "projectId": task["projectId"]})

        chapters = _load_chapters(task["projectId"])
        if not chapters:
            raise ValueError("项目尚未生成章节，请先完成目录设计。")

        empty_chapters = [chapter for chapter in chapters if not (chapter.get("current_content") or "").strip()]
        if empty_chapters:
            raise ValueError(f"仍有 {len(empty_chapters)} 个章节未生成正文，暂不能导出。")

        yield _emit(task_id, "status", {"stage": "merge", "text": "正在合并项目章节"})
        markdown_content = _merge_sections(chapters)
        project = _load_project(task["projectId"]) or {}
        project_name = project.get("project_name") or f"project-{task['projectId']}"

        markdown_stored = storage_service.create_file(
            content_bytes=markdown_content.encode("utf-8"),
            original_filename=f"{project_name}_bid_document.md",
            file_category="generated_markdown",
            owner_user_id=task.get("createdBy"),
            project_id=task["projectId"],
            content_text=markdown_content,
            content_encoding="utf-8",
            change_source="project_export",
            allow_generated_ext=True,
        )
        yield _emit(task_id, "artifact", {"kind": "markdown", "fileId": markdown_stored.file_id})

        try:
            with TemporaryDirectory() as tmpdir:
                markdown_file = Path(tmpdir) / f"{project_name}_bid_document.md"
                markdown_file.write_text(markdown_content, encoding="utf-8")
                docx_path = Path(
                    convert_md_to_word(
                        markdown_file,
                        cover_data=_load_cover_data(task["projectId"]),
                        facts=_load_project_facts(task["projectId"]),
                    )
                )
                docx_bytes = docx_path.read_bytes()
        except Exception as exc:
            LOGGER.warning("project export docx build failed task_id=%s error=%s", task_id, str(exc)[:200])
            raise ValueError("Word 文档转换失败，已保留 Markdown 草稿，但不能进入 OnlyOffice。请检查导出模板或转换依赖后重试。") from exc

        word_stored = storage_service.create_file(
            content_bytes=docx_bytes,
            original_filename=f"{project_name}_bid_document.docx",
            file_category="generated_bid",
            owner_user_id=task.get("createdBy"),
            project_id=task["projectId"],
            change_source="project_export",
            allow_generated_ext=True,
        )
        final_file_id = word_stored.file_id
        file_url = f"/api/files/{word_stored.file_id}/download"
        yield _emit(task_id, "artifact", {"kind": "docx", "fileId": word_stored.file_id})

        bid_document_id = chapters[0].get("bid_document_id")
        doc_version = None
        if bid_document_id:
            doc_version = _store_document_version(
                bid_document_id=bid_document_id,
                file_id=final_file_id,
                markdown_storage_key=markdown_stored.storage_key,
                created_by=task.get("createdBy"),
                change_summary="项目级工作台导出",
            )

        _mark_project_exported(task["projectId"], generated_file_id=final_file_id)
        output = {
            "projectId": task["projectId"],
            "bidDocumentId": bid_document_id,
            "wordFileId": final_file_id,
            "fileUrl": file_url,
            "markdownFileId": markdown_stored.file_id,
            "documentVersion": doc_version,
            "wordCount": word_count(markdown_content),
        }
        update_task(task_id, status="succeeded", output_json=output, finished=True)
        yield _emit(task_id, "done", output)
    except Exception as exc:
        LOGGER.exception("project export failed task_id=%s", task_id)
        update_task(task_id, status="failed", error_message=str(exc)[:1000], finished=True)
        yield _emit(task_id, "error", {"error": str(exc)[:500]})


def stream_project_generation(task_id):
    task = get_task(task_id)
    if not task:
        yield {"type": "error", "error": "Task not found."}
        return
    if task.get("taskType") != "project_generate":
        yield {"type": "error", "error": "Only project_generate is supported here."}
        return
    if task.get("status") in ("succeeded", "failed", "cancelled"):
        for event in list_events(task_id):
            payload = event.get("payload") or {}
            yield {"type": event.get("type"), **payload, "eventId": event.get("id"), "message": event.get("message")}
        return
    if task.get("status") == "running":
        yield {"type": "error", "error": "Task is already running."}
        return

    try:
        update_task(task_id, status="running", started=True)
        input_payload = task.get("input") or {}
        include_existing = bool(input_payload.get("includeExisting"))
        project = _load_project(task["projectId"])
        if not project:
            raise ValueError("Project not found.")
        chapters = _load_chapters(task["projectId"])
        if not chapters:
            raise ValueError("当前项目还没有章节，请先完成目录设计。")

        conn = get_db()
        try:
            conn.execute(
                "UPDATE bid_projects SET project_status='generating', updated_at=? WHERE id=?",
                (now(), task["projectId"]),
            )
            conn.commit()
        finally:
            conn.close()

        total = len(chapters)
        yielded_any = False
        yield _emit(task_id, "start", {"taskId": task_id, "projectId": task["projectId"], "totalChapters": total})

        completed = 0
        child_task_ids = []
        for index, chapter in enumerate(chapters, start=1):
            title = chapter.get("chapter_title") or f"章节 {index}"
            has_content = bool((chapter.get("current_content") or "").strip())
            should_skip = has_content and not include_existing
            if should_skip:
                completed += 1
                yield _emit(
                    task_id,
                    "chapter_skipped",
                    {
                        "chapterId": chapter["id"],
                        "title": title,
                        "current": index,
                        "total": total,
                    },
                )
                continue

            yield _emit(
                task_id,
                "status",
                {
                    "stage": "chapter_queue",
                    "chapterId": chapter["id"],
                    "title": title,
                    "current": index,
                    "total": total,
                    "text": f"正在生成第 {index}/{total} 章：{title}",
                },
            )
            child_task = create_task(
                project_id=task["projectId"],
                chapter_id=chapter["id"],
                task_type="chapter_generate",
                input_json={"parentTaskId": task_id, "source": "project_generate"},
                created_by=task.get("createdBy"),
            )
            child_task_ids.append(child_task["id"])
            _start_child_task(child_task["id"])
            for child_event in run_chapter_generation(child_task["id"]):
                event_type = child_event.get("type")
                wrapped = {
                    "chapterId": chapter["id"],
                    "title": title,
                    "childTaskId": child_task["id"],
                    "current": index,
                    "total": total,
                }
                if event_type == "token":
                    wrapped["text"] = child_event.get("text")
                    yielded_any = True
                    yield _emit(task_id, "chapter_token", wrapped)
                    continue
                if event_type == "error":
                    wrapped["error"] = child_event.get("error")
                    yield _emit(task_id, "chapter_error", wrapped)
                    raise ValueError(f"{title} 生成失败：{child_event.get('error')}")
                if event_type == "done":
                    completed += 1
                    wrapped["editorDocVersion"] = child_event.get("editorDocVersion")
                    yield _emit(task_id, "chapter_done", wrapped)
                    continue
                if event_type in {"citation", "image_plan", "followup"}:
                    wrapped[event_type] = child_event
                    yield _emit(task_id, f"chapter_{event_type}", wrapped)
                    continue
                if child_event.get("text"):
                    wrapped["text"] = child_event.get("text")
                if child_event.get("stage"):
                    wrapped["stage"] = child_event.get("stage")
                yield _emit(task_id, f"chapter_{event_type}", wrapped)

        yield _emit(
            task_id,
            "status",
            {
                "stage": "project_export",
                "text": "章节已完成，正在导出整本文件",
                "completedChapters": completed,
                "totalChapters": total,
            },
        )
        export_task = create_export_task(project_id=task["projectId"], created_by=task.get("createdBy"))
        for export_event in run_project_export(export_task["id"]):
            if export_event.get("type") == "error":
                yield _emit(task_id, "export_error", {"error": export_event.get("error"), "exportTaskId": export_task["id"]})
                raise ValueError(export_event.get("error") or "项目导出失败")
            payload = {key: value for key, value in export_event.items() if key != "type"}
            payload["exportTaskId"] = export_task["id"]
            yield _emit(task_id, f"export_{export_event.get('type')}", payload)

        output = {
            "projectId": task["projectId"],
            "completedChapters": completed,
            "totalChapters": total,
            "childTaskIds": child_task_ids,
            "exportTaskId": export_task["id"],
            "streamedTokens": yielded_any,
        }
        update_task(task_id, status="succeeded", output_json=output, finished=True)
        yield _emit(task_id, "done", output)
    except Exception as exc:
        LOGGER.exception("project generation failed task_id=%s", task_id)
        update_task(task_id, status="failed", error_message=str(exc)[:1000], finished=True)
        yield _emit(task_id, "error", {"error": str(exc)[:500]})
