import logging

from core.db import get_db
from storage.vector_store import get_vector_store


LOGGER = logging.getLogger(__name__)


class RetrievalRouter:
    def search(self, query, *, tenant_id=1, project_id=None, knowledge_base_id=None, doc_type=None, limit=5):
        degraded = False
        degraded_reason = None
        try:
            vector_hits = self._vector_search(
                query,
                tenant_id=tenant_id,
                project_id=project_id,
                knowledge_base_id=knowledge_base_id,
                doc_type=doc_type,
                limit=limit,
            )
            if vector_hits:
                return {"items": vector_hits, "degraded": False, "degraded_reason": None, "fallback_used": False}
        except Exception as exc:
            degraded = True
            degraded_reason = f"vector_retrieval_failed: {str(exc)[:240]}"
            LOGGER.warning(
                "retrieval degraded fallback_used=true project_id=%s doc_type=%s reason=%s",
                project_id,
                doc_type,
                degraded_reason,
            )

        try:
            text_hits = self._mysql_text_search(
                query,
                tenant_id=tenant_id,
                project_id=project_id,
                knowledge_base_id=knowledge_base_id,
                doc_type=doc_type,
                limit=limit,
            )
            return {
                "items": text_hits,
                "degraded": degraded or bool(text_hits),
                "degraded_reason": degraded_reason or ("vector_empty_mysql_text_fallback" if text_hits else None),
                "fallback_used": True if text_hits or degraded else False,
            }
        except Exception as exc:
            reason = f"mysql_text_retrieval_failed: {str(exc)[:240]}"
            LOGGER.exception("retrieval mysql fallback failed degraded=true reason=%s", reason)
            return {"items": [], "degraded": True, "degraded_reason": degraded_reason or reason, "fallback_used": True}

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

    def _vector_search(self, query, *, tenant_id=1, project_id=None, knowledge_base_id=None, doc_type=None, limit=5):
        filters = {"tenant_id": tenant_id}
        if project_id:
            filters["project_id"] = str(project_id)
        if knowledge_base_id:
            filters["knowledge_base_id"] = str(knowledge_base_id)
        if doc_type:
            filters["doc_type"] = doc_type
        vector_hits = get_vector_store().query(query, filters=filters, limit=limit)
        return self._hydrate_vector_hits(vector_hits)

    def _hydrate_vector_hits(self, vector_hits):
        if not vector_hits:
            return []
        ids = [hit["id"] for hit in vector_hits]
        placeholders = ",".join(["?"] * len(ids))
        conn = get_db()
        try:
            rows = conn.execute(
                f"""
                SELECT c.*, f.original_filename, k.doc_title, k.reuse_policy
                FROM document_chunks c
                JOIN document_files f ON f.id = c.file_id
                LEFT JOIN knowledge_documents k ON k.id = c.knowledge_document_id
                WHERE c.chunk_uid IN ({placeholders}) AND c.status = 'indexed'
                """,
                tuple(ids),
            ).fetchall()
        finally:
            conn.close()
        by_id = {row["chunk_uid"]: row for row in rows}
        results = []
        for hit in vector_hits:
            row = by_id.get(hit["id"])
            if not row:
                continue
            results.append(self._format_row(row, similarity=hit["similarity"], distance=hit["distance"]))
        return results

    def _mysql_text_search(self, query, *, tenant_id=1, project_id=None, knowledge_base_id=None, doc_type=None, limit=5):
        clauses = ["c.tenant_id = ?", "c.status = 'indexed'"]
        params = [tenant_id]
        if project_id:
            clauses.append("c.project_id = ?")
            params.append(project_id)
        if knowledge_base_id:
            clauses.append("c.knowledge_base_id = ?")
            params.append(knowledge_base_id)
        if doc_type:
            clauses.append("c.doc_type = ?")
            params.append(doc_type)
        tokens = [item for item in query.split() if item][:6] or [query]
        like_clauses = []
        for token in tokens:
            like_clauses.append("c.chunk_text LIKE ?")
            params.append(f"%{token}%")
        clauses.append("(" + " OR ".join(like_clauses) + ")")
        conn = get_db()
        try:
            rows = conn.execute(
                f"""
                SELECT c.*, f.original_filename, k.doc_title, k.reuse_policy
                FROM document_chunks c
                JOIN document_files f ON f.id = c.file_id
                LEFT JOIN knowledge_documents k ON k.id = c.knowledge_document_id
                WHERE {' AND '.join(clauses)}
                ORDER BY c.updated_at DESC
                LIMIT ?
                """,
                tuple(params + [limit]),
            ).fetchall()
        finally:
            conn.close()
        return [self._format_row(row, similarity=0.35, distance=None) for row in rows]

    def _format_row(self, row, *, similarity, distance):
        return {
            "chunk_id": row["id"],
            "chunk_uid": row["chunk_uid"],
            "file_id": row["file_id"],
            "knowledge_base_id": row.get("knowledge_base_id"),
            "knowledge_document_id": row.get("knowledge_document_id"),
            "project_id": row.get("project_id"),
            "doc_type": row["doc_type"],
            "content": row.get("chunk_text") or "",
            "source_title": row.get("doc_title") or row.get("original_filename"),
            "reuse_policy": row.get("reuse_policy"),
            "similarity": similarity,
            "distance": distance,
        }


retrieval_router = RetrievalRouter()
