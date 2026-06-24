class RetrievalRouter:
    def search(self, query, *, tenant_id=1, project_id=None, knowledge_base_id=None, doc_type=None, limit=5):
        from services.rag.hybrid_search import hybrid_search

        return hybrid_search.search(
            query,
            tenant_id=tenant_id,
            project_id=project_id,
            knowledge_base_id=knowledge_base_id,
            doc_type=doc_type,
            limit=limit,
        )

    def build_context(self, query, *, project_id=None, limit=6):
        hits = []
        degraded = False
        reasons = []
        specs = []
        if project_id:
            specs.append({"project_id": project_id})
        specs.extend(
            [
                {"doc_type": "history_bid"},
                {"doc_type": "legal_policy"},
                {"doc_type": "recent_tender"},
            ]
        )
        for spec in specs:
            pack = self.search(query, project_id=spec.get("project_id"), doc_type=spec.get("doc_type"), limit=limit)
            hits.extend(pack["items"])
            degraded = degraded or pack["degraded"]
            if pack.get("degraded_reason"):
                reasons.append(pack["degraded_reason"])
        hits = sorted(hits, key=lambda item: item.get("similarity", 0), reverse=True)[:limit]
        return {
            "query": query,
            "results": hits,
            "context_text": "\n\n".join(
                f"[{index + 1}] {item['source_title']} ({item['doc_type']}):\n{item['content']}"
                for index, item in enumerate(hits)
            ),
            "degraded": degraded,
            "degraded_reason": "; ".join(dict.fromkeys(reasons)) or None,
            "fallback_used": degraded,
        }


retrieval_router = RetrievalRouter()
