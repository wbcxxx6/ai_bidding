import sys
import types
import unittest

from flask import Flask


fake_pymysql = types.SimpleNamespace(
    connect=lambda **kwargs: None,
    cursors=types.SimpleNamespace(DictCursor=object),
    err=types.SimpleNamespace(OperationalError=Exception),
)
sys.modules.setdefault("pymysql", fake_pymysql)
sys.modules.setdefault("pymysql.cursors", fake_pymysql.cursors)


class FakeCursor:
    def __init__(self, fetchone_result=None, fetchall_result=None):
        self._fetchone_result = fetchone_result
        self._fetchall_result = fetchall_result or []

    def fetchone(self):
        return self._fetchone_result

    def fetchall(self):
        return self._fetchall_result


class FakeConn:
    def __init__(self):
        self.closed = False
        self.queries = []

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.queries.append((normalized, params))
        if "FROM knowledge_bases kb" in normalized and "WHERE kb.id = ?" in normalized:
            return FakeCursor(
                fetchone_result={
                    "id": 3,
                    "kbName": "企业资信库",
                    "kbType": "company_profile",
                    "description": "企业资料",
                    "visibilityScope": "tenant",
                    "status": "active",
                    "createdAt": "2026-06-23 09:00:00",
                    "updatedAt": "2026-06-23 09:10:00",
                    "documentCount": 2,
                    "chunkCount": 9,
                    "parsedCount": 1,
                    "vectorizedCount": 1,
                    "failedCount": 1,
                }
            )
        if "FROM knowledge_bases kb" in normalized and "GROUP BY kb.id" in normalized:
            return FakeCursor(
                fetchall_result=[
                    {
                        "id": 3,
                        "kbName": "企业资信库",
                        "kbType": "company_profile",
                        "description": "企业资料",
                        "visibilityScope": "tenant",
                        "status": "active",
                        "createdAt": "2026-06-23 09:00:00",
                        "updatedAt": "2026-06-23 09:10:00",
                        "documentCount": 2,
                        "chunkCount": 9,
                        "parsedCount": 1,
                        "vectorizedCount": 1,
                        "failedCount": 1,
                    }
                ]
            )
        if "FROM knowledge_documents kd" in normalized:
            return FakeCursor(
                fetchall_result=[
                    {
                        "knowledgeDocumentId": 11,
                        "documentId": 21,
                        "docTitle": "资信报告.docx",
                        "docType": "company_profile",
                        "reusePolicy": "rewrite_required",
                        "reviewStatus": "approved",
                        "originalFilename": "资信报告.docx",
                        "fileSize": 4096,
                        "parseStatus": "parsed",
                        "vectorStatus": "indexed",
                        "chunkCount": 7,
                        "embeddingModel": "text-embedding-v3",
                        "vectorCollection": "document_embeddings",
                        "createdAt": "2026-06-23 09:01:00",
                        "updatedAt": "2026-06-23 09:02:00",
                    },
                    {
                        "knowledgeDocumentId": 12,
                        "documentId": 22,
                        "docTitle": "产品手册.pdf",
                        "docType": "product_library",
                        "reusePolicy": "direct",
                        "reviewStatus": "pending",
                        "originalFilename": "产品手册.pdf",
                        "fileSize": 2048,
                        "parseStatus": "failed",
                        "vectorStatus": "failed",
                        "chunkCount": 2,
                        "embeddingModel": "text-embedding-v3",
                        "vectorCollection": "document_embeddings",
                        "createdAt": "2026-06-23 09:03:00",
                        "updatedAt": "2026-06-23 09:04:00",
                    },
                ]
            )
        raise AssertionError(f"Unexpected SQL: {normalized}")

    def close(self):
        self.closed = True


class KnowledgeApiTest(unittest.TestCase):
    def setUp(self):
        from api import knowledge

        self.knowledge = knowledge
        self.fake_conn = FakeConn()
        self.original_get_db = knowledge.get_db
        knowledge.get_db = lambda: self.fake_conn
        app = Flask(__name__)
        app.register_blueprint(knowledge.bp, url_prefix="/api")
        self.client = app.test_client()

    def tearDown(self):
        self.knowledge.get_db = self.original_get_db

    def test_list_knowledge_bases_includes_processing_progress(self):
        response = self.client.get("/api/knowledge-bases")

        self.assertEqual(response.status_code, 200)
        item = response.get_json()["items"][0]
        self.assertEqual(item["documentCount"], 2)
        self.assertEqual(item["chunkCount"], 9)
        self.assertEqual(item["processSummary"]["parseStatus"], "partial")
        self.assertEqual(item["processSummary"]["vectorStatus"], "partial")
        self.assertEqual(item["processSummary"]["failedCount"], 1)
        self.assertTrue(self.fake_conn.closed)

    def test_knowledge_base_detail_returns_documents_with_pipeline_state(self):
        response = self.client.get("/api/knowledge-bases/3")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["kb"]["kbName"], "企业资信库")
        self.assertEqual(payload["summary"]["documentCount"], 2)
        self.assertEqual(payload["summary"]["vectorStatus"], "partial")
        self.assertEqual(len(payload["documents"]), 2)
        self.assertEqual(payload["documents"][0]["pipelineSteps"][0], {"key": "uploaded", "label": "已上传", "status": "success"})
        self.assertEqual(payload["documents"][0]["pipelineSteps"][1], {"key": "parsed", "label": "文本解析", "status": "success"})
        self.assertEqual(payload["documents"][0]["pipelineSteps"][2], {"key": "vectorized", "label": "向量化", "status": "success"})
        self.assertEqual(payload["documents"][1]["pipelineSteps"][1]["status"], "error")
        self.assertEqual(payload["documents"][1]["pipelineSteps"][2]["status"], "error")


if __name__ == "__main__":
    unittest.main()
