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
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.closed = False
        self.sql = None

    def execute(self, sql, params=()):
        self.sql = " ".join(sql.split())
        return FakeCursor(self.rows)

    def close(self):
        self.closed = True


class ProjectCenterApiTest(unittest.TestCase):
    def test_project_list_includes_progress_and_latest_task_fields(self):
        from api import bidding

        rows = [
            {
                "id": 7,
                "project_code": "BID-7",
                "project_name": "脱敏投标项目 A",
                "purchaser_name": "采购单位",
                "industry": "政企",
                "region": "华东",
                "project_status": "generating",
                "created_at": "2026-06-23 09:00:00",
                "bidding_id": 18,
                "bidding_filename": "某某招标文件.pdf",
                "bidding_status": "Analyzed",
                "latest_generation_task_id": 31,
                "latest_generation_task_type": "generate_document",
                "latest_generation_task_status": "succeeded",
                "latest_generation_task_updated_at": "2026-06-23 09:10:00",
                "latest_agent_task_id": 42,
                "latest_agent_task_type": "project_generate",
                "latest_agent_task_status": "running",
                "latest_agent_task_updated_at": "2026-06-23 09:15:00",
                "total_chapters": 10,
                "generated_chapters": 4,
                "pending_chapters": 6,
            }
        ]
        fake_conn = FakeConn(rows)
        original_get_db = bidding.get_db
        bidding.get_db = lambda: fake_conn
        app = Flask(__name__)
        try:
            with app.app_context():
                response = bidding.list_projects()
        finally:
            bidding.get_db = original_get_db

        payload = response.get_json()
        item = payload["items"][0]

        self.assertTrue(fake_conn.closed)
        self.assertIn("latest_agent_task", fake_conn.sql)
        self.assertIn("chapter_stats", fake_conn.sql)
        self.assertEqual(item["bidding_filename"], "某某招标文件.pdf")
        self.assertEqual(item["latest_agent_task_status"], "running")
        self.assertEqual(item["latest_generation_task_status"], "succeeded")
        self.assertEqual(item["total_chapters"], 10)
        self.assertEqual(item["generated_chapters"], 4)
        self.assertEqual(item["pending_chapters"], 6)


if __name__ == "__main__":
    unittest.main()
