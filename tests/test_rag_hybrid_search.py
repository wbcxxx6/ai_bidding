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
sys.modules.setdefault("psycopg", None)


class HybridSearchUnitTest(unittest.TestCase):
    def test_merge_combines_keyword_and_vector_scores(self):
        from services.rag.hybrid_search import HybridSearchEngine

        engine = HybridSearchEngine()
        merged = engine._merge(
            [
                {
                    "chunk_uid": "a",
                    "channels": ["keyword"],
                    "keywordScore": 0.9,
                    "vectorScore": 0,
                    "vectorDistance": None,
                }
            ],
            [
                {
                    "chunk_uid": "a",
                    "channels": ["vector"],
                    "keywordScore": 0,
                    "vectorScore": 0.8,
                    "vectorDistance": 0.2,
                },
                {
                    "chunk_uid": "b",
                    "channels": ["vector"],
                    "keywordScore": 0,
                    "vectorScore": 0.5,
                    "vectorDistance": 0.5,
                },
            ],
        )

        self.assertEqual(merged[0]["chunk_uid"], "a")
        self.assertEqual(merged[0]["channels"], ["keyword", "vector"])
        self.assertGreater(merged[0]["hybridScore"], merged[1]["hybridScore"])

    def test_public_item_contains_explainable_score(self):
        from services.rag.hybrid_search import HybridSearchEngine

        engine = HybridSearchEngine()
        item = engine._public_item(
            {
                "chunk_id": 1,
                "chunk_uid": "chunk-1",
                "file_id": 2,
                "doc_type": "history_bid",
                "sourceType": "history_bid",
                "source_title": "历史标书",
                "content": "正文",
                "channels": ["keyword", "vector"],
                "keywordScore": 0.5,
                "vectorScore": 0.7,
                "vectorDistance": 0.3,
                "hybridScore": 0.6,
                "rerankScore": 0.8,
                "rerankModel": "lexical",
            }
        )

        self.assertEqual(item["score"], 0.8)
        self.assertEqual(item["explain"]["channels"], ["keyword", "vector"])
        self.assertEqual(item["explain"]["rerankModel"], "lexical")


if __name__ == "__main__":
    unittest.main()
