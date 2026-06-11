import json
from datetime import datetime

from core.db import get_db


IMAGE_RULES = [
    {
        "keywords": ["系统架构", "技术架构", "总体架构", "部署架构", "数据流"],
        "imageType": "architecture_diagram",
        "captionSuffix": "系统架构图",
        "placement": "after_section_intro",
    },
    {
        "keywords": ["实施流程", "工作流程", "服务流程", "管理流程", "进度安排"],
        "imageType": "process_diagram",
        "captionSuffix": "流程图",
        "placement": "after_process_description",
    },
    {
        "keywords": ["组织架构", "项目组织", "人员组织", "管理架构"],
        "imageType": "org_chart",
        "captionSuffix": "组织架构图",
        "placement": "after_org_description",
    },
    {
        "keywords": ["产品", "设备", "平台", "系统功能"],
        "imageType": "product_image",
        "captionSuffix": "产品示意图",
        "placement": "after_product_intro",
    },
]

IMAGE_SOURCE_PRIORITY = {
    "enterprise_upload": "enterprise_image",
    "enterprise_image": "enterprise_image",
    "company_profile": "enterprise_image",
    "product_library": "enterprise_image",
    "history_bid": "history_bid_image",
    "history_bid_image": "history_bid_image",
}

PRIORITY_ORDER = {
    "enterprise_image": 0,
    "history_bid_image": 1,
    "ai_generated_placeholder": 2,
}


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def dumps(value):
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def _chapter_text(chapter):
    return "\n".join(
        str(value or "")
        for value in [
            chapter.get("title") or chapter.get("chapter_title"),
            chapter.get("description"),
            chapter.get("content"),
            chapter.get("type"),
        ]
    )


def _asset_image_type(item):
    return item.get("imageType") or item.get("image_type") or item.get("asset_type")


def _asset_priority(item):
    source = item.get("source_type") or item.get("sourceType") or item.get("doc_type")
    if source == "image_asset":
        source = item.get("asset_source_type") or item.get("origin_source_type") or item.get("source_type")
    return IMAGE_SOURCE_PRIORITY.get(source) or "history_bid_image"


def _match_image_assets(context_items, image_type):
    matches = []
    for item in context_items or []:
        if item.get("sourceType") != "image_asset" and item.get("doc_type") != "image_asset":
            continue
        item_type = _asset_image_type(item)
        if item_type and item_type != image_type:
            continue
        priority = _asset_priority(item)
        matches.append(
            {
                "assetId": item.get("asset_id") or item.get("image_asset_id") or item.get("id"),
                "fileId": item.get("file_id"),
                "title": item.get("asset_title") or item.get("source_title") or item.get("title") or "图片资产",
                "caption": item.get("caption") or item.get("content") or "",
                "imageType": item_type or image_type,
                "sourcePriority": priority,
                "sourceType": item.get("source_type") or item.get("sourceType") or item.get("doc_type"),
                "score": item.get("similarity") or item.get("score") or 0,
            }
        )
    return sorted(
        matches,
        key=lambda item: (PRIORITY_ORDER.get(item["sourcePriority"], 99), -(item.get("score") or 0)),
    )


def plan_chapter_images(chapter, *, context_items=None, industry=None):
    text = _chapter_text(chapter)
    plans = []
    for rule in IMAGE_RULES:
        if not any(keyword in text for keyword in rule["keywords"]):
            continue
        title = chapter.get("title") or chapter.get("chapter_title") or "当前章节"
        matched_assets = _match_image_assets(context_items, rule["imageType"])
        plans.append(
            {
                "chapterId": chapter.get("id"),
                "projectId": chapter.get("projectId") or chapter.get("project_id"),
                "imageType": rule["imageType"],
                "caption": f"{title}{rule['captionSuffix']}",
                "placement": rule["placement"],
                "sourcePriority": ["enterprise_image", "history_bid_image", "ai_generated_placeholder"],
                "query": f"{title} {rule['captionSuffix']}",
                "promptHint": f"围绕{title}生成正式投标文件可用的{rule['captionSuffix']}，风格简洁、专业、便于 Word 排版。",
                "requiredResolution": "1200x800",
                "status": "selected" if matched_assets else "pending_asset",
                "matchedAssets": matched_assets[:3],
                "riskNotes": [],
                "industry": industry,
            }
        )
        break
    return plans


def save_image_plans(project_id, chapter_id, plans, *, task_id=None):
    if not plans:
        return []
    conn = get_db()
    saved = []
    try:
        cursor = conn.cursor()
        for plan in plans:
            cursor.execute(
                """
                INSERT INTO image_plan
                (tenant_id, project_id, chapter_id, task_id, image_type, caption, placement,
                 source_priority_json, query_text, prompt_hint, required_resolution, status,
                 matched_assets_json, risk_notes_json, created_at, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    chapter_id,
                    task_id,
                    plan.get("imageType"),
                    plan.get("caption"),
                    plan.get("placement"),
                    dumps(plan.get("sourcePriority")),
                    plan.get("query"),
                    plan.get("promptHint"),
                    plan.get("requiredResolution"),
                    plan.get("status") or "pending_asset",
                    dumps(plan.get("matchedAssets") or []),
                    dumps(plan.get("riskNotes") or []),
                    now(),
                    now(),
                ),
            )
            saved_plan = {**plan, "id": cursor.lastrowid}
            saved.append(saved_plan)
        conn.commit()
        return saved
    finally:
        conn.close()


def list_chapter_image_plans(chapter_id):
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT * FROM image_plan
            WHERE chapter_id=?
            ORDER BY id ASC
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
        "imageType": row.get("image_type"),
        "caption": row.get("caption"),
        "placement": row.get("placement"),
        "sourcePriority": _loads(row.get("source_priority_json"), []),
        "query": row.get("query_text"),
        "promptHint": row.get("prompt_hint"),
        "requiredResolution": row.get("required_resolution"),
        "status": row.get("status"),
        "matchedAssets": _loads(row.get("matched_assets_json"), []),
        "riskNotes": _loads(row.get("risk_notes_json"), []),
    }
