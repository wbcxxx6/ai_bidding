import json
import math
import os
from datetime import datetime

from core.db import get_db
from core.pg import get_pg, pg_available
from services.rag.reranker import rerank


EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")


def embed_texts(texts):
    from storage.vector_store import embed_texts as vector_store_embed_texts

    return vector_store_embed_texts(texts)


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


def vector_literal(vector):
    return "[" + ",".join(f"{float(item):.8f}" for item in vector) + "]"


def source_type_for_doc_type(doc_type):
    mapping = {
        "company_profile": "company_profile",
        "product_library": "product_library",
        "history_bid": "history_bid",
        "image_asset": "image_asset",
        "tender_original": "project",
    }
    return mapping.get(doc_type) or doc_type or "project"


class HybridSearchEngine:
    def index_chunks(self, chunks):
        if not chunks or not pg_available():
            return {"indexed": 0, "backend": "postgres", "skipped": True}

        embeddings = embed_texts([item["text"] for item in chunks])
        with get_pg() as conn:
            with conn.cursor() as cursor:
                for item, embedding in zip(chunks, embeddings):
                    metadata = item.get("metadata") or {}
                    cursor.execute(
                        """
                        INSERT INTO knowledge_chunk
                        (chunk_uid, tenant_id, project_id, knowledge_base_id, knowledge_document_id, file_id,
                         doc_type, source_type, source_title, section_path, page_start, page_end, chunk_index,
                         chunk_text, metadata_json, embedding_model, embedding, status, updated_at)
                        VALUES (%(chunk_uid)s, %(tenant_id)s, %(project_id)s, %(knowledge_base_id)s,
                                %(knowledge_document_id)s, %(file_id)s, %(doc_type)s, %(source_type)s,
                                %(source_title)s, %(section_path)s, %(page_start)s, %(page_end)s,
                                %(chunk_index)s, %(chunk_text)s, %(metadata_json)s, %(embedding_model)s,
                                %(embedding)s::vector, 'indexed', now())
                        ON CONFLICT (chunk_uid) DO UPDATE SET
                            project_id = EXCLUDED.project_id,
                            knowledge_base_id = EXCLUDED.knowledge_base_id,
                            knowledge_document_id = EXCLUDED.knowledge_document_id,
                            file_id = EXCLUDED.file_id,
                            doc_type = EXCLUDED.doc_type,
                            source_type = EXCLUDED.source_type,
                            source_title = EXCLUDED.source_title,
                            section_path = EXCLUDED.section_path,
                            page_start = EXCLUDED.page_start,
                            page_end = EXCLUDED.page_end,
                            chunk_index = EXCLUDED.chunk_index,
                            chunk_text = EXCLUDED.chunk_text,
                            metadata_json = EXCLUDED.metadata_json,
                            embedding_model = EXCLUDED.embedding_model,
                            embedding = EXCLUDED.embedding,
                            status = 'indexed',
                            updated_at = now()
                        """,
                        {
                            "chunk_uid": item["id"],
                            "tenant_id": metadata.get("tenant_id") or 1,
                            "project_id": metadata.get("project_id") or None,
                            "knowledge_base_id": metadata.get("knowledge_base_id") or None,
                            "knowledge_document_id": metadata.get("knowledge_document_id") or None,
                            "file_id": metadata.get("file_id"),
                            "doc_type": metadata.get("doc_type"),
                            "source_type": source_type_for_doc_type(metadata.get("doc_type")),
                            "source_title": metadata.get("source_title"),
                            "section_path": metadata.get("section_path"),
                            "page_start": metadata.get("page_start"),
                            "page_end": metadata.get("page_end"),
                            "chunk_index": metadata.get("chunk_index") or 0,
                            "chunk_text": item["text"],
                            "metadata_json": dumps(metadata),
                            "embedding_model": EMBEDDING_MODEL,
                            "embedding": vector_literal(embedding),
                        },
                    )
            conn.commit()
        return {"indexed": len(chunks), "backend": "postgres", "skipped": False}

    def delete_file(self, file_id):
        if not pg_available():
            return {"deleted": 0, "backend": "postgres", "skipped": True}
        with get_pg() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE knowledge_chunk SET status='deleted', updated_at=now() WHERE file_id=%s AND status <> 'deleted'",
                    (file_id,),
                )
                count = cursor.rowcount
            conn.commit()
        return {"deleted": count, "backend": "postgres", "skipped": False}

    def search(self, query, *, tenant_id=1, project_id=None, knowledge_base_id=None, doc_type=None, limit=5, chapter_id=None):
        degraded = False
        degraded_reason = None
        fallback_used = False
        backend = "postgres_pgvector_fts"
        try:
            keyword_hits = self._keyword_search(
                query,
                tenant_id=tenant_id,
                project_id=project_id,
                knowledge_base_id=knowledge_base_id,
                doc_type=doc_type,
                limit=max(limit * 3, 10),
            )
            vector_hits = self._vector_search(
                query,
                tenant_id=tenant_id,
                project_id=project_id,
                knowledge_base_id=knowledge_base_id,
                doc_type=doc_type,
                limit=max(limit * 3, 10),
            )
            merged = self._merge(keyword_hits, vector_hits)
            ranked = rerank(query, merged, top_n=limit)
        except Exception as exc:
            degraded = True
            degraded_reason = f"postgres_hybrid_failed: {str(exc)[:240]}"
            fallback_used = True
            backend = "mysql_like_fallback"
            keyword_hits = []
            vector_hits = []
            ranked = self._mysql_text_search(
                query,
                tenant_id=tenant_id,
                project_id=project_id,
                knowledge_base_id=knowledge_base_id,
                doc_type=doc_type,
                limit=limit,
            )
            merged = ranked

        source_mix = self._source_mix(ranked)
        score_trace = [self._score_trace(item) for item in ranked]
        retrieval_log_id = self._record_log(
            tenant_id=tenant_id,
            project_id=project_id,
            chapter_id=chapter_id,
            query=query,
            backend=backend,
            keyword_count=len(keyword_hits),
            vector_count=len(vector_hits),
            merged_count=len(merged),
            returned_count=len(ranked),
            source_mix=source_mix,
            score_trace=score_trace,
            degraded=degraded,
            degraded_reason=degraded_reason,
            fallback_used=fallback_used,
            rerank_model=(ranked[0].get("rerankModel") if ranked else None),
        )
        return {
            "items": [self._public_item(item) for item in ranked],
            "degraded": degraded,
            "degraded_reason": degraded_reason,
            "fallback_used": fallback_used,
            "backend": backend,
            "retrieval_log_id": retrieval_log_id,
            "source_mix": source_mix,
            "score_trace": score_trace,
        }

    def _where(self, *, tenant_id, project_id, knowledge_base_id, doc_type):
        clauses = ["tenant_id = %(tenant_id)s", "status = 'indexed'"]
        params = {"tenant_id": tenant_id}
        if project_id:
            clauses.append("project_id = %(project_id)s")
            params["project_id"] = project_id
        if knowledge_base_id:
            clauses.append("knowledge_base_id = %(knowledge_base_id)s")
            params["knowledge_base_id"] = knowledge_base_id
        if doc_type:
            clauses.append("doc_type = %(doc_type)s")
            params["doc_type"] = doc_type
        return " AND ".join(clauses), params

    def _keyword_search(self, query, *, tenant_id, project_id, knowledge_base_id, doc_type, limit):
        where_sql, params = self._where(
            tenant_id=tenant_id,
            project_id=project_id,
            knowledge_base_id=knowledge_base_id,
            doc_type=doc_type,
        )
        params.update({"query": query, "limit": limit})
        with get_pg() as conn:
            rows = conn.execute(
                f"""
                SELECT *, ts_rank_cd(search_vector, websearch_to_tsquery('simple', %(query)s)) AS keyword_score
                FROM knowledge_chunk
                WHERE {where_sql}
                  AND (
                    search_vector @@ websearch_to_tsquery('simple', %(query)s)
                    OR chunk_text ILIKE ('%%' || %(query)s || '%%')
                  )
                ORDER BY keyword_score DESC, updated_at DESC
                LIMIT %(limit)s
                """,
                params,
            ).fetchall()
        return [self._row_to_item(row, channel="keyword", keyword_score=float(row.get("keyword_score") or 0)) for row in rows]

    def _vector_search(self, query, *, tenant_id, project_id, knowledge_base_id, doc_type, limit):
        where_sql, params = self._where(
            tenant_id=tenant_id,
            project_id=project_id,
            knowledge_base_id=knowledge_base_id,
            doc_type=doc_type,
        )
        embedding = vector_literal(embed_texts([query])[0])
        params.update({"embedding": embedding, "limit": limit})
        with get_pg() as conn:
            rows = conn.execute(
                f"""
                SELECT *, (embedding <=> %(embedding)s::vector) AS vector_distance
                FROM knowledge_chunk
                WHERE {where_sql}
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> %(embedding)s::vector
                LIMIT %(limit)s
                """,
                params,
            ).fetchall()
        return [
            self._row_to_item(
                row,
                channel="vector",
                vector_distance=float(row.get("vector_distance") or 1),
                vector_score=max(0.0, 1.0 - float(row.get("vector_distance") or 1)),
            )
            for row in rows
        ]

    def _merge(self, keyword_hits, vector_hits):
        merged = {}
        for item in keyword_hits + vector_hits:
            key = item["chunk_uid"]
            current = merged.get(key)
            if not current:
                merged[key] = item
                continue
            current["channels"] = sorted(set(current.get("channels", []) + item.get("channels", [])))
            current["keywordScore"] = max(float(current.get("keywordScore") or 0), float(item.get("keywordScore") or 0))
            current["vectorScore"] = max(float(current.get("vectorScore") or 0), float(item.get("vectorScore") or 0))
            current["vectorDistance"] = min(
                float(current.get("vectorDistance") if current.get("vectorDistance") is not None else 1),
                float(item.get("vectorDistance") if item.get("vectorDistance") is not None else 1),
            )
        for item in merged.values():
            keyword_score = min(math.log1p(float(item.get("keywordScore") or 0)) / 2.0, 1.0)
            vector_score = float(item.get("vectorScore") or 0)
            channel_bonus = 0.08 if len(item.get("channels") or []) > 1 else 0
            item["hybridScore"] = round(keyword_score * 0.45 + vector_score * 0.45 + channel_bonus, 6)
        return sorted(merged.values(), key=lambda value: value.get("hybridScore") or 0, reverse=True)

    def _mysql_text_search(self, query, *, tenant_id, project_id, knowledge_base_id, doc_type, limit):
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
        like_clauses = []
        for token in ([item for item in query.split() if item][:6] or [query]):
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
        return [
            {
                "chunk_id": row["id"],
                "chunk_uid": row["chunk_uid"],
                "file_id": row["file_id"],
                "knowledge_base_id": row.get("knowledge_base_id"),
                "knowledge_document_id": row.get("knowledge_document_id"),
                "project_id": row.get("project_id"),
                "doc_type": row["doc_type"],
                "sourceType": source_type_for_doc_type(row["doc_type"]),
                "source_title": row.get("doc_title") or row.get("original_filename"),
                "content": row.get("chunk_text") or "",
                "reuse_policy": row.get("reuse_policy"),
                "channels": ["mysql_like"],
                "keywordScore": 0,
                "vectorScore": 0,
                "hybridScore": 0.2,
                "rerankScore": 0.2,
                "rerankModel": "fallback",
                "similarity": 0.2,
                "distance": None,
            }
            for row in rows
        ]

    def _row_to_item(self, row, *, channel, keyword_score=0, vector_score=0, vector_distance=None):
        metadata = row.get("metadata_json") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return {
            "chunk_id": row["id"],
            "chunk_uid": row["chunk_uid"],
            "file_id": row["file_id"],
            "knowledge_base_id": row.get("knowledge_base_id"),
            "knowledge_document_id": row.get("knowledge_document_id"),
            "project_id": row.get("project_id"),
            "doc_type": row["doc_type"],
            "sourceType": row.get("source_type") or source_type_for_doc_type(row["doc_type"]),
            "source_title": row.get("source_title") or metadata.get("source_title") or f"file-{row['file_id']}",
            "content": row.get("chunk_text") or "",
            "metadata": metadata,
            "channels": [channel],
            "keywordScore": keyword_score,
            "vectorScore": vector_score,
            "vectorDistance": vector_distance,
            "similarity": vector_score,
            "distance": vector_distance,
        }

    def _source_mix(self, items):
        result = {}
        for item in items:
            key = item.get("sourceType") or item.get("doc_type") or "unknown"
            result.setdefault(key, {"count": 0, "maxScore": 0, "channels": set()})
            result[key]["count"] += 1
            result[key]["maxScore"] = max(result[key]["maxScore"], float(item.get("rerankScore") or item.get("hybridScore") or 0))
            result[key]["channels"].update(item.get("channels") or [])
        return {
            key: {**value, "channels": sorted(value["channels"])}
            for key, value in result.items()
        }

    def _score_trace(self, item):
        return {
            "chunkUid": item.get("chunk_uid"),
            "sourceTitle": item.get("source_title"),
            "sourceType": item.get("sourceType"),
            "docType": item.get("doc_type"),
            "channels": item.get("channels") or [],
            "keywordScore": item.get("keywordScore") or 0,
            "vectorScore": item.get("vectorScore") or 0,
            "vectorDistance": item.get("vectorDistance"),
            "hybridScore": item.get("hybridScore") or 0,
            "rerankScore": item.get("rerankScore") or 0,
            "rerankModel": item.get("rerankModel"),
        }

    def _public_item(self, item):
        return {
            "chunk_id": item.get("chunk_id"),
            "chunk_uid": item.get("chunk_uid"),
            "file_id": item.get("file_id"),
            "knowledge_base_id": item.get("knowledge_base_id"),
            "knowledge_document_id": item.get("knowledge_document_id"),
            "project_id": item.get("project_id"),
            "doc_type": item.get("doc_type"),
            "sourceType": item.get("sourceType"),
            "source_title": item.get("source_title"),
            "content": item.get("content") or "",
            "similarity": item.get("vectorScore") or item.get("similarity") or 0,
            "distance": item.get("vectorDistance"),
            "score": item.get("rerankScore") or item.get("hybridScore") or 0,
            "explain": self._score_trace(item),
            "metadata": item.get("metadata") or {},
        }

    def _record_log(
        self,
        *,
        tenant_id,
        project_id,
        chapter_id,
        query,
        backend,
        keyword_count,
        vector_count,
        merged_count,
        returned_count,
        source_mix,
        score_trace,
        degraded,
        degraded_reason,
        fallback_used,
        rerank_model,
    ):
        if pg_available():
            try:
                with get_pg() as conn:
                    row = conn.execute(
                        """
                        INSERT INTO rag_retrieval_log
                        (tenant_id, project_id, chapter_id, query_text, backend, keyword_count,
                         vector_count, merged_count, returned_count, rerank_model, source_mix_json,
                         score_trace_json, degraded, degraded_reason, fallback_used)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            tenant_id,
                            project_id,
                            chapter_id,
                            query,
                            backend,
                            keyword_count,
                            vector_count,
                            merged_count,
                            returned_count,
                            rerank_model,
                            dumps(source_mix),
                            dumps(score_trace),
                            degraded,
                            degraded_reason,
                            fallback_used,
                        ),
                    ).fetchone()
                    conn.commit()
                    return row["id"] if row else None
            except Exception:
                return None
        return None


hybrid_search = HybridSearchEngine()
