from core.db import get_db


def _word_count(text):
    if not text:
        return 0
    return len("".join(str(text).split()))


def _safe_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _chapter_volume_label(title, chapter_type):
    text = f"{title or ''} {chapter_type or ''}"
    if "报价" in text or "价格" in text:
        return "pricing"
    if "资格" in text or "资质" in text:
        return "qualification"
    if "商务" in text or "合同" in text:
        return "business"
    return "technical"


def list_project_workbench_chapters(project_id):
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT
                c.id,
                c.project_id,
                c.bid_document_id,
                c.chapter_title,
                c.chapter_type,
                c.sort_order,
                c.status,
                c.current_version_id,
                COALESCE(doc.markdown_content, ver.content, '') AS content_text,
                COALESCE(doc.version_no, 0) AS editor_version_no,
                COALESCE(cite.citation_count, 0) AS citation_count,
                COALESCE(img.image_plan_count, 0) AS image_plan_count,
                COALESCE(img.pending_image_plan_count, 0) AS pending_image_plan_count,
                COALESCE(fu.followup_count, 0) AS followup_count,
                COALESCE(fu.pending_followup_count, 0) AS pending_followup_count,
                task.id AS latest_task_id,
                task.status AS latest_task_status,
                task.created_at AS latest_task_created_at,
                task.finished_at AS latest_task_finished_at
            FROM bid_chapters c
            LEFT JOIN (
                SELECT d1.chapter_id, d1.markdown_content, d1.version_no
                FROM chapter_editor_docs d1
                INNER JOIN (
                    SELECT chapter_id, MAX(version_no) AS max_version
                    FROM chapter_editor_docs
                    WHERE status='active'
                    GROUP BY chapter_id
                ) latest_doc
                    ON latest_doc.chapter_id = d1.chapter_id
                   AND latest_doc.max_version = d1.version_no
            ) doc ON doc.chapter_id = c.id
            LEFT JOIN bid_chapter_versions ver ON ver.id = c.current_version_id
            LEFT JOIN (
                SELECT chapter_id, COUNT(*) AS citation_count
                FROM citation_record
                WHERE status='active'
                GROUP BY chapter_id
            ) cite ON cite.chapter_id = c.id
            LEFT JOIN (
                SELECT
                    chapter_id,
                    COUNT(*) AS image_plan_count,
                    SUM(CASE WHEN status NOT IN ('ready', 'selected') THEN 1 ELSE 0 END) AS pending_image_plan_count
                FROM image_plan
                GROUP BY chapter_id
            ) img ON img.chapter_id = c.id
            LEFT JOIN (
                SELECT
                    chapter_id,
                    COUNT(*) AS followup_count,
                    SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending_followup_count
                FROM followup_question
                GROUP BY chapter_id
            ) fu ON fu.chapter_id = c.id
            LEFT JOIN (
                SELECT t1.chapter_id, t1.id, t1.status, t1.created_at, t1.finished_at
                FROM agent_task t1
                INNER JOIN (
                    SELECT chapter_id, MAX(id) AS max_id
                    FROM agent_task
                    WHERE chapter_id IS NOT NULL
                    GROUP BY chapter_id
                ) latest_task
                    ON latest_task.chapter_id = t1.chapter_id
                   AND latest_task.max_id = t1.id
            ) task ON task.chapter_id = c.id
            WHERE c.project_id=?
            ORDER BY c.sort_order ASC, c.id ASC
            """,
            (project_id,),
        ).fetchall()

        items = []
        for row in rows:
            content_text = row.get("content_text") or ""
            word_count = _word_count(content_text)
            items.append(
                {
                    "id": row["id"],
                    "projectId": row.get("project_id"),
                    "bidDocumentId": row.get("bid_document_id"),
                    "title": row.get("chapter_title"),
                    "type": row.get("chapter_type"),
                    "sortOrder": row.get("sort_order"),
                    "status": row.get("status"),
                    "currentVersionId": row.get("current_version_id"),
                    "editorVersionNo": row.get("editor_version_no"),
                    "wordCount": word_count,
                    "hasContent": word_count > 0,
                    "citationCount": _safe_int(row.get("citation_count")),
                    "imagePlanCount": _safe_int(row.get("image_plan_count")),
                    "pendingImagePlanCount": _safe_int(row.get("pending_image_plan_count")),
                    "followupCount": _safe_int(row.get("followup_count")),
                    "pendingFollowupCount": _safe_int(row.get("pending_followup_count")),
                    "latestTaskId": row.get("latest_task_id"),
                    "latestTaskStatus": row.get("latest_task_status"),
                    "latestTaskCreatedAt": row.get("latest_task_created_at"),
                    "latestTaskFinishedAt": row.get("latest_task_finished_at"),
                    "volumeType": _chapter_volume_label(row.get("chapter_title"), row.get("chapter_type")),
                }
            )
        return items
    finally:
        conn.close()


def get_project_workbench_overview(project_id):
    chapters = list_project_workbench_chapters(project_id)
    conn = get_db()
    try:
        project = conn.execute(
            """
            SELECT
                p.id,
                p.project_name,
                p.project_status,
                p.directory_structure,
                b.generated_file_id
            FROM bid_projects p
            LEFT JOIN bidding b ON b.project_id = p.id
            WHERE p.id=?
            ORDER BY b.id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        recent_tasks = conn.execute(
            """
            SELECT id, chapter_id, task_type, status, created_at, finished_at, error_message
            FROM agent_task
            WHERE project_id=?
            ORDER BY id DESC
            LIMIT 8
            """,
            (project_id,),
        ).fetchall()
    finally:
        conn.close()

    generated_count = sum(1 for chapter in chapters if chapter["hasContent"])
    pending_followups = sum(chapter["pendingFollowupCount"] for chapter in chapters)
    pending_images = sum(chapter["pendingImagePlanCount"] for chapter in chapters)
    citations = sum(chapter["citationCount"] for chapter in chapters)
    image_plans = sum(chapter["imagePlanCount"] for chapter in chapters)
    followups = sum(chapter["followupCount"] for chapter in chapters)

    volume_stats = {}
    for chapter in chapters:
        key = chapter["volumeType"]
        bucket = volume_stats.setdefault(
            key,
            {"volumeType": key, "chapterCount": 0, "generatedCount": 0, "pendingFollowupCount": 0},
        )
        bucket["chapterCount"] += 1
        if chapter["hasContent"]:
            bucket["generatedCount"] += 1
        bucket["pendingFollowupCount"] += chapter["pendingFollowupCount"]

    pending_actions = []
    for chapter in chapters:
        if not chapter["hasContent"]:
            pending_actions.append(
                {
                    "kind": "generate_chapter",
                    "chapterId": chapter["id"],
                    "title": chapter["title"],
                    "severity": "info",
                    "message": f"{chapter['title']} 尚未生成正文，可加入项目级顺序生成。",
                }
            )
        if chapter["pendingFollowupCount"] > 0:
            pending_actions.append(
                {
                    "kind": "followup",
                    "chapterId": chapter["id"],
                    "title": chapter["title"],
                    "severity": "warning",
                    "message": f"{chapter['title']} 还有 {chapter['pendingFollowupCount']} 条待补资料/待确认问题。",
                }
            )
        if chapter["pendingImagePlanCount"] > 0:
            pending_actions.append(
                {
                    "kind": "image_asset",
                    "chapterId": chapter["id"],
                    "title": chapter["title"],
                    "severity": "warning",
                    "message": f"{chapter['title']} 还有 {chapter['pendingImagePlanCount']} 个待补图片计划。",
                }
            )

    chapter_status = {
        "total": len(chapters),
        "generated": generated_count,
        "pending": max(len(chapters) - generated_count, 0),
    }
    if chapter_status["total"] > 0:
        chapter_status["progressPercent"] = round((generated_count / chapter_status["total"]) * 100, 1)
    else:
        chapter_status["progressPercent"] = 0

    return {
        "project": {
            "id": (project or {}).get("id"),
            "projectName": (project or {}).get("project_name"),
            "projectStatus": (project or {}).get("project_status"),
            "generatedFileId": (project or {}).get("generated_file_id"),
        },
        "chapterStatus": chapter_status,
        "stats": {
            "citationCount": citations,
            "imagePlanCount": image_plans,
            "followupCount": followups,
            "pendingFollowupCount": pending_followups,
            "pendingImagePlanCount": pending_images,
        },
        "volumes": list(volume_stats.values()),
        "chapters": chapters,
        "pendingActions": pending_actions[:20],
        "recentTasks": [
            {
                "id": row["id"],
                "chapterId": row.get("chapter_id"),
                "taskType": row.get("task_type"),
                "status": row.get("status"),
                "createdAt": row.get("created_at"),
                "finishedAt": row.get("finished_at"),
                "errorMessage": row.get("error_message"),
            }
            for row in recent_tasks
        ],
    }
