import json
import logging

from core.db import get_db
from services.model_center.stream import stream_chat_completion
from services.v2.agent_task_service import append_event, get_task, list_events, update_task
from services.v2.chapter_strategy_service import get_or_create_strategy
from services.v2.citation_service import create_citation_records
from services.v2.context_builder import build_context
from services.v2.editor_doc_service import save_editor_doc


LOGGER = logging.getLogger(__name__)


def loads(value):
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _load_chapter(chapter_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM bid_chapters WHERE id=?", (chapter_id,)).fetchone()
        if not row:
            return None
        return row
    finally:
        conn.close()


def _load_project_facts(project_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT fact_label, fact_value, status FROM project_facts WHERE project_id=? ORDER BY id ASC",
            (project_id,),
        ).fetchall()
        return rows
    finally:
        conn.close()


def _outline_description(chapter):
    outline = loads(chapter.get("outline_json")) or {}
    parts = [outline.get("description") or outline.get("content") or ""]
    for section in outline.get("sections") or []:
        parts.append(section.get("title") or "")
        for subsection in section.get("subsections") or []:
            parts.append(subsection.get("title") or "")
            parts.append(subsection.get("describe") or "")
    return "\n".join(part for part in parts if part)


def _build_prompt(*, chapter, strategy, facts, context):
    facts_text = "\n".join(
        f"- {row.get('fact_label')}: {row.get('fact_value')}"
        for row in facts
        if row.get("fact_value")
    ) or "（暂无已确认项目事实）"
    forbidden = "\n".join(f"- {item}" for item in strategy.get("forbiddenRules") or [])
    context_text = context.get("contextText") or "（知识库暂未命中可引用资料。涉及企业事实、资质、人员、金额、日期时请输出待补充提示，不得编造。）"
    description = _outline_description(chapter)
    target_words = strategy.get("targetWords") or 1200
    return f"""你是企业投标文件写作 Agent。请为当前章节生成可直接进入投标文件的正文草稿。

【章节】
{chapter.get('chapter_title')}

【章节说明】
{description or '请根据章节标题、项目事实和参考来源撰写。'}

【分册策略】
- 分册类型：{strategy.get('volumeType')}
- 目标字数：约 {target_words} 字
- 写作风格：{strategy.get('writingStyle')}

【禁止事项】
{forbidden or '- 不得编造企业事实、证书、人员、金额、日期、产品参数和项目案例。'}

【项目事实】
{facts_text}

【参考来源】
{context_text}

【输出要求】
- 使用 Markdown。
- 从二级或三级标题开始组织内容，不要输出封面和目录。
- 可以引用参考来源编号，如 [CIT-001]。
- 如果资料不足，请明确写“待补充”并说明缺口。
- 不要输出解释性前言，不要包裹代码块。
"""


def _emit(task_id, event_type, payload=None, message=None):
    event = append_event(task_id, event_type, payload or {}, message)
    return {"type": event_type, **(payload or {}), "eventId": event["id"], "message": message}


def stream_chapter_generation(task_id):
    task = get_task(task_id)
    if not task:
        yield {"type": "error", "error": "Task not found."}
        return
    if task.get("taskType") != "chapter_generate":
        yield {"type": "error", "error": "Only chapter_generate is supported in P0."}
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
        yield _emit(task_id, "start", {"taskId": task_id, "chapterId": task.get("chapterId")})

        chapter = _load_chapter(task.get("chapterId"))
        if not chapter:
            raise ValueError(f"Chapter not found: {task.get('chapterId')}")

        yield _emit(task_id, "status", {"stage": "strategy", "text": "正在加载章节策略"})
        strategy = get_or_create_strategy(chapter)

        query = f"{chapter.get('chapter_title')}\n{_outline_description(chapter)}"
        yield _emit(task_id, "status", {"stage": "retrieval", "text": "正在检索参考资料"})
        context = build_context(query, project_id=task["projectId"], chapter_id=task.get("chapterId"), limit=5)
        if context.get("degraded"):
            yield _emit(
                task_id,
                "status",
                {"stage": "retrieval", "degraded": True, "text": context.get("degradedReason") or "检索降级，继续生成"},
            )

        citations = create_citation_records(task, context.get("items") or [])
        for citation in citations:
            yield _emit(task_id, "citation", citation)

        facts = _load_project_facts(task["projectId"])
        prompt = _build_prompt(chapter=chapter, strategy=strategy, facts=facts, context=context)

        yield _emit(task_id, "status", {"stage": "writing", "text": "正在流式生成正文"})
        content_parts = []
        for chunk in stream_chat_completion(
            [{"role": "user", "content": prompt}],
            task_type="generate_chapter",
            project_id=task["projectId"],
            timeout=180,
        ):
            content_parts.append(chunk)
            yield _emit(task_id, "token", {"text": chunk})

        content = "".join(content_parts).strip()
        yield _emit(task_id, "status", {"stage": "saving", "text": "正在保存章节正文"})
        saved = save_editor_doc(
            chapter_id=task["chapterId"],
            markdown=content,
            created_by=task.get("createdBy"),
            sync_chapter_version=True,
            change_source="system_generated",
        )
        update_task(
            task_id,
            status="succeeded",
            output_json={"chapterId": task["chapterId"], "editorDocVersion": saved["versionNo"], "citations": citations},
            finished=True,
        )
        yield _emit(task_id, "done", {"chapterId": task["chapterId"], "editorDocVersion": saved["versionNo"]})
    except Exception as exc:
        LOGGER.exception("chapter generation failed task_id=%s", task_id)
        update_task(task_id, status="failed", error_message=str(exc)[:1000], finished=True)
        yield _emit(task_id, "error", {"error": str(exc)[:500]})
