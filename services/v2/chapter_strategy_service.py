import json
from datetime import datetime

from core.db import get_db


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


def infer_volume_type(title, chapter_type=None):
    text = f"{title or ''} {chapter_type or ''}"
    if any(word in text for word in ["报价", "价格", "分项报价"]):
        return "pricing"
    if any(word in text for word in ["资格", "资质", "证书", "人员", "业绩"]):
        return "qualification"
    if any(word in text for word in ["商务", "合同", "承诺", "偏离"]):
        return "commercial"
    if any(word in text for word in ["附件", "附录"]):
        return "appendix"
    return "technical"


def _policy_for_volume(volume_type):
    policies = {
        "pricing": {
            "target_words": 900,
            "style": "报价说明应克制、准确，只解释报价逻辑和风险边界。",
            "forbidden": ["不得编造金额、单价、税率、工程量", "未确认报价资料时不得输出具体数字"],
            "rag": {"sourceTypes": ["tender_original", "project_supporting"], "requireEvidence": True},
        },
        "qualification": {
            "target_words": 1200,
            "style": "资格文件强调事实、证据和附件索引。",
            "forbidden": ["不得编造资质证书、人员姓名、证书编号、业绩合同"],
            "rag": {"sourceTypes": ["enterprise", "history_bid", "tender_original"], "requireEvidence": True},
        },
        "commercial": {
            "target_words": 1600,
            "style": "商务响应强调条款响应、承诺边界和企业服务能力。",
            "forbidden": ["不得编造保证金账号、保函编号、签章日期、合同金额"],
            "rag": {"sourceTypes": ["enterprise", "history_bid", "tender_original"], "requireEvidence": True},
        },
        "appendix": {
            "target_words": 700,
            "style": "附件章节以清单、来源、用途和待补充状态为主。",
            "forbidden": ["不得伪造附件或证明材料"],
            "rag": {"sourceTypes": ["enterprise", "project_supporting", "tender_original"], "requireEvidence": True},
        },
        "technical": {
            "target_words": 2200,
            "style": "技术章节强调方案、流程、措施、质量和风险控制。",
            "forbidden": ["不得编造企业专有产品参数、项目案例、证书或人员信息"],
            "rag": {"sourceTypes": ["history_bid", "product", "tender_original"], "requireEvidence": False},
        },
    }
    return policies.get(volume_type, policies["technical"])


def _format_strategy(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "projectId": row.get("project_id"),
        "chapterId": row.get("chapter_id"),
        "volumeType": row.get("volume_type"),
        "targetWords": row.get("target_words"),
        "writingStyle": row.get("writing_style"),
        "forbiddenRules": json.loads(row["forbidden_rules_json"]) if row.get("forbidden_rules_json") else [],
        "ragPolicy": json.loads(row["rag_policy_json"]) if row.get("rag_policy_json") else {},
    }


def get_or_create_strategy(chapter):
    chapter_id = chapter["id"]
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM chapter_strategy WHERE chapter_id=? AND status='active'", (chapter_id,)).fetchone()
        if row:
            return _format_strategy(row)
        volume_type = infer_volume_type(chapter.get("chapter_title"), chapter.get("chapter_type"))
        policy = _policy_for_volume(volume_type)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chapter_strategy
            (tenant_id, project_id, chapter_id, volume_type, target_words, writing_style,
             forbidden_rules_json, rag_policy_json, status, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                chapter["project_id"],
                chapter_id,
                volume_type,
                policy["target_words"],
                policy["style"],
                dumps(policy["forbidden"]),
                dumps(policy["rag"]),
                now(),
                now(),
            ),
        )
        conn.commit()
        return _format_strategy(conn.execute("SELECT * FROM chapter_strategy WHERE id=?", (cursor.lastrowid,)).fetchone())
    finally:
        conn.close()
