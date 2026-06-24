import sys
import types
import unittest

from flask import Flask
from storage.storage_service import StorageError


fake_pymysql = types.SimpleNamespace(
    connect=lambda **kwargs: None,
    cursors=types.SimpleNamespace(DictCursor=object),
    err=types.SimpleNamespace(OperationalError=Exception),
)
sys.modules.setdefault("pymysql", fake_pymysql)
sys.modules.setdefault("pymysql.cursors", fake_pymysql.cursors)


class FakeCursor:
    def __init__(self, fetchone_result=None):
        self._fetchone_result = fetchone_result

    def fetchone(self):
        return self._fetchone_result


class FakeConn:
    def __init__(self, rows_by_marker):
        self.rows_by_marker = rows_by_marker
        self.closed = False
        self.queries = []

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.queries.append((normalized, params))
        if "FROM bidding" in normalized:
            return FakeCursor(self.rows_by_marker.get("bidding"))
        if "FROM generation_tasks" in normalized:
            return FakeCursor(self.rows_by_marker.get("generation_task"))
        if "FROM agent_task" in normalized:
            return FakeCursor(self.rows_by_marker.get("agent_task"))
        if "FROM document_files" in normalized and "WHERE id=?" in normalized:
            expected_id = params[0] if params else None
            row = self.rows_by_marker.get("preferred_file")
            return FakeCursor(row if row and row.get("id") == expected_id else None)
        if "FROM document_files" in normalized:
            return FakeCursor(self.rows_by_marker.get("latest_docx_file"))
        return FakeCursor(None)

    def close(self):
        self.closed = True


class OnlyOfficeEditorConfigTest(unittest.TestCase):
    def setUp(self):
        from api import bidding

        self.bidding = bidding
        self.original_get_db = bidding.get_db
        self.original_storage = bidding.storage_service
        app = Flask(__name__)
        self.app_context = app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.bidding.get_db = self.original_get_db
        self.bidding.storage_service = self.original_storage
        self.app_context.pop()

    def test_editor_config_uses_latest_successful_task_when_bidding_file_id_is_missing(self):
        fake_conn = FakeConn(
            {
                "bidding": {
                    "id": 11,
                    "original_filename": "招标文件.pdf",
                    "document_key": "doc-11",
                    "generated_file_id": None,
                },
                "generation_task": {
                    "output_json": '{"wordFileId": 88, "fileUrl": "/api/files/88/download"}',
                },
                "preferred_file": {"id": 88},
            }
        )
        self.bidding.get_db = lambda: fake_conn

        class FakeStorage:
            file_id = None

            def get_latest(self, file_id):
                self.file_id = file_id
                return {"id": file_id, "original_filename": "投标文档.docx"}

        fake_storage = FakeStorage()
        self.bidding.storage_service = fake_storage

        response = self.bidding.get_editor_config(5)
        payload = response.get_json()

        self.assertEqual(fake_storage.file_id, 88)
        self.assertEqual(payload["generatedFileId"], 88)
        self.assertIn("/api/files/88/download", payload["config"]["document"]["url"])
        self.assertTrue(fake_conn.closed)

    def test_editor_config_ignores_markdown_preferred_file_and_uses_latest_docx(self):
        fake_conn = FakeConn(
            {
                "bidding": {
                    "id": 11,
                    "original_filename": "招标文件.pdf",
                    "document_key": "doc-11",
                    "generated_file_id": 77,
                },
                "preferred_file": None,
                "latest_docx_file": {"id": 88},
            }
        )
        self.bidding.get_db = lambda: fake_conn

        class FakeStorage:
            file_id = None

            def get_latest(self, file_id):
                self.file_id = file_id
                return {"id": file_id, "original_filename": "投标文档.docx"}

        fake_storage = FakeStorage()
        self.bidding.storage_service = fake_storage

        response = self.bidding.get_editor_config(5)
        payload = response.get_json()

        self.assertEqual(fake_storage.file_id, 88)
        self.assertEqual(payload["generatedFileId"], 88)
        self.assertIn("/api/files/88/download", payload["config"]["document"]["url"])

    def test_editor_config_returns_clear_error_when_generated_blob_is_missing(self):
        fake_conn = FakeConn(
            {
                "bidding": {
                    "id": 11,
                    "original_filename": "招标文件.pdf",
                    "document_key": "doc-11",
                    "generated_file_id": 88,
                },
                "preferred_file": {"id": 88},
            }
        )
        self.bidding.get_db = lambda: fake_conn

        class FakeStorage:
            def get_latest(self, file_id):
                raise self_error

        self_error = StorageError("File blob not found.")
        self.bidding.storage_service = FakeStorage()

        response = self.bidding.get_editor_config(5)
        payload = response.get_json()

        self.assertIsNone(payload["config"])
        self.assertEqual(payload["generatedFileId"], 88)
        self.assertIn("Generated document file is missing", payload["error"])


if __name__ == "__main__":
    unittest.main()
