import json
from datetime import datetime

from core.db import get_db
from services.retrieval_router import retrieval_router


BUSINESS_DOMAIN_POLICIES = [
    {
        "sourceType": "project",
        "docType": None,
        "quota": 2,
        "label": "项目资料",
    },
    {
        "sourceType": "company_profile",
        "docType": "company_profile",
        "quota": 2,
        "label": "企业资信",
    },
    {
        "sourceType": "product_library",
        "docType": "product_library",
        "quota": 2,
        "label": "产品资料",
    },
    {
        "sourceType": "history_bid",
        "docType": "history_bid",
        "quota": 2,
        "label": "历史标书",
    },
    {
        "sourceType": "image_asset",
        "docType": "image_asset",
        "quota": 2,
        "label": "图片资产",
    },
]


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def dumps(value):
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def _record_retrieval_log(*, project_id, chapter_id, query, items, source_mix, degraded, degraded_reason, fallback_used):
    conn = None
    try:
        conn = get_db()
        conn.execute(
            """
            INSERT INTO retrieval_log
            (tenant_id, project_id, chapter_id, query_text, source_mix_json, result_count,
             top_results_json, degraded, degraded_reason, fallback_used, created_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                chapter_id,
                query,
                dumps(source_mix),
                len(items),
                dumps(items[:10]),
                1 if degraded else 0,
                degraded_reason,
                1 if fallback_used else 0,
                now(),
            ),
        )
        conn.commit()
    except Exception:
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def _dedupe_items(items):
    seen = set()
    result = []
    for item in items:
        key = item.get("chunk_uid") or item.get("chunk_id") or (item.get("source_title"), item.get("content"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _loads(value, default):
    if not value:
        return default
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _query_tokens(query):
    tokens = [item.strip() for item in (query or "").replace("\n", " ").split() if item.strip()]
    return tokens[:6] or [query]


def _search_image_assets(query, *, project_id=None, limit=2):
    conn = None
    try:
        clauses = [
            "deleted_at IS NULL",
            "allowed_for_bid=1",
            "review_status IN ('approved', 'ready', 'selected')",
        ]
        params = []
        if project_id:
            clauses.append("(project_id=? OR project_id IS NULL)")
            params.append(project_id)
        like_clauses = []
        for token in _query_tokens(query):
            like_clauses.extend(["asset_title LIKE ?", "caption LIKE ?", "searchable_text LIKE ?"])
            params.extend([f"%{token}%", f"%{token}%", f"%{token}%"])
        clauses.append("(" + " OR ".join(like_clauses) + ")")
        params.append(limit)
        conn = get_db()
        rows = conn.execute(
            f"""
            SELECT id, project_id, file_id, asset_title, image_type, source_type, caption,
                   searchable_text, tags_json, allowed_for_bid, synthetic, review_status, metadata_json
            FROM image_asset
            WHERE {' AND '.join(clauses)}
            ORDER BY project_id IS NULL ASC, updated_at DESC, id DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        results = []
        for row in rows:
            results.append(
                {
                    "asset_id": row.get("id"),
                    "file_id": row.get("file_id"),
                    "doc_type": "image_asset",
                    "sourceType": "image_asset",
                    "source_title": row.get("asset_title"),
                    "content": row.get("caption") or row.get("searchable_text") or "",
                    "caption": row.get("caption"),
                    "asset_title": row.get("asset_title"),
                    "image_type": row.get("image_type"),
                    "source_type": row.get("source_type"),
                    "tags": _loads(row.get("tags_json"), []),
                    "allowed_for_bid": bool(row.get("allowed_for_bid")),
                    "synthetic": bool(row.get("synthetic")),
                    "review_status": row.get("review_status"),
                    "metadata": _loads(row.get("metadata_json"), {}),
                    "similarity": 0.66,
                    "distance": 0.34,
                }
            )
        return results
    except Exception:
        return []
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def build_context(query, *, project_id, chapter_id=None, limit=5):
    items = []
    degraded = False
    fallback_used = False
    degraded_reasons = []
    source_mix = {}
    for policy in BUSINESS_DOMAIN_POLICIES:
        pack = retrieval_router.search(
            query,
            project_id=project_id if policy["sourceType"] == "project" else None,
            doc_type=policy["docType"],
            limit=policy["quota"],
        )
        domain_items = pack.get("items") or []
        if policy["sourceType"] == "image_asset":
            domain_items = domain_items + _search_image_assets(query, project_id=project_id, limit=policy["quota"])
        source_mix[policy["sourceType"]] = {
            "label": policy["label"],
            "count": len(domain_items),
            "degraded": pack.get("degraded", False),
            "fallbackUsed": pack.get("fallback_used", False),
            "backend": pack.get("backend"),
            "retrievalLogId": pack.get("retrieval_log_id"),
        }
        for item in domain_items:
            item["sourceType"] = policy["sourceType"]
            item["sourceLabel"] = policy["label"]
        items.extend(domain_items)
        degraded = degraded or pack.get("degraded", False)
        fallback_used = fallback_used or pack.get("fallback_used", False)
        if pack.get("degraded_reason"):
            degraded_reasons.append(pack["degraded_reason"])

    items = sorted(_dedupe_items(items), key=lambda item: item.get("similarity", 0), reverse=True)[:limit]
    for index, item in enumerate(items, start=1):
        item["citationKey"] = f"CIT-{index:03d}"

    context_text = "\n\n".join(
        f"[{item['citationKey']}] {item.get('sourceLabel') or item.get('doc_type') or '参考资料'}｜{item.get('source_title') or '参考资料'}\n{(item.get('content') or '')[:900]}"
        for index, item in enumerate(items)
    )
    degraded_reason = "; ".join(dict.fromkeys(degraded_reasons)) or None
    _record_retrieval_log(
        project_id=project_id,
        chapter_id=chapter_id,
        query=query,
        items=items,
        source_mix=source_mix,
        degraded=degraded,
        degraded_reason=degraded_reason,
        fallback_used=fallback_used,
    )
    return {
        "query": query,
        "chapterId": chapter_id,
        "items": items,
        "contextText": context_text,
        "sourceMix": source_mix,
        "scoreTrace": [item.get("explain") for item in items if item.get("explain")],
        "degraded": degraded,
        "degradedReason": degraded_reason,
        "fallbackUsed": fallback_used,
    }
