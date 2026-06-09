from services.retrieval_router import retrieval_router


def build_context(query, *, project_id, chapter_id=None, limit=5):
    pack = retrieval_router.search(query, project_id=project_id, limit=limit)
    items = pack.get("items") or []
    context_text = "\n\n".join(
        f"[CIT-{index + 1:03d}] {item.get('source_title') or '参考资料'}\n{(item.get('content') or '')[:900]}"
        for index, item in enumerate(items)
    )
    return {
        "query": query,
        "chapterId": chapter_id,
        "items": items,
        "contextText": context_text,
        "degraded": pack.get("degraded", False),
        "degradedReason": pack.get("degraded_reason"),
        "fallbackUsed": pack.get("fallback_used", False),
    }
