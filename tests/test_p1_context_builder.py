import sys
import types
import unittest

fake_pymysql = types.SimpleNamespace(
    connect=lambda **kwargs: None,
    cursors=types.SimpleNamespace(DictCursor=object),
    err=types.SimpleNamespace(OperationalError=Exception),
)
sys.modules.setdefault("pymysql", fake_pymysql)
sys.modules.setdefault("pymysql.cursors", fake_pymysql.cursors)


class FakeRetrievalRouter:
    def __init__(self):
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        doc_type = kwargs.get("doc_type") or "project"
        return {
            "items": [
                {
                    "chunk_id": len(self.calls),
                    "chunk_uid": f"chunk-{len(self.calls)}",
                    "file_id": 10 + len(self.calls),
                    "doc_type": doc_type,
                    "content": f"{doc_type} content for {query}",
                    "source_title": f"{doc_type} source",
                    "similarity": 0.7,
                    "distance": 0.3,
                }
            ],
            "degraded": False,
            "degraded_reason": None,
            "fallback_used": False,
        }


class FakeHybridSearch:
    def __init__(self, router):
        self.router = router

    def search(self, query, **kwargs):
        return self.router.search(query, **kwargs)


class FakeImageAssetConn:
    def __init__(self):
        self.closed = False

    def execute(self, sql, params=None):
        return types.SimpleNamespace(
            fetchall=lambda: [
                {
                    "id": 71,
                    "project_id": 9,
                    "file_id": 19,
                    "asset_title": "企业系统架构图",
                    "image_type": "architecture_diagram",
                    "source_type": "enterprise_upload",
                    "caption": "系统架构设计图",
                    "searchable_text": "系统架构 技术标",
                    "tags_json": '["技术标"]',
                    "allowed_for_bid": 1,
                    "synthetic": 0,
                    "review_status": "approved",
                    "metadata_json": "{}",
                }
            ]
        )

    def close(self):
        self.closed = True


class P1ContextBuilderTest(unittest.TestCase):
    def setUp(self):
        self.fake_router = FakeRetrievalRouter()
        sys.modules["services.retrieval_router"] = types.SimpleNamespace(retrieval_router=self.fake_router)
        sys.modules["services.rag.hybrid_search"] = types.SimpleNamespace(hybrid_search=FakeHybridSearch(self.fake_router))
        sys.modules.pop("services.v2.context_builder", None)

    def test_build_context_searches_business_domains_and_assigns_citation_keys(self):
        from services.v2.context_builder import build_context

        context = build_context("技术方案", project_id=9, chapter_id=3, limit=6)

        doc_types = [call.get("doc_type") for call in self.fake_router.calls]
        self.assertIn("company_profile", doc_types)
        self.assertIn("product_library", doc_types)
        self.assertIn("history_bid", doc_types)
        self.assertIn("image_asset", doc_types)
        self.assertEqual(context["items"][0]["citationKey"], "CIT-001")
        self.assertIn("[CIT-001]", context["contextText"])
        self.assertIn("sourceMix", context)

    def test_build_context_adds_image_asset_table_hits(self):
        from services.v2 import context_builder

        original_get_db = context_builder.get_db
        context_builder.get_db = lambda: FakeImageAssetConn()
        try:
            context = context_builder.build_context("系统架构", project_id=9, chapter_id=3, limit=10)
        finally:
            context_builder.get_db = original_get_db

        image_items = [item for item in context["items"] if item.get("asset_id") == 71]
        self.assertEqual(len(image_items), 1)
        self.assertEqual(image_items[0]["image_type"], "architecture_diagram")
        self.assertGreaterEqual(context["sourceMix"]["image_asset"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
