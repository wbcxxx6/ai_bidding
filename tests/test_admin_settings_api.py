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
        if "COUNT(*) AS projects" in normalized:
            return FakeCursor(fetchone_result={"projects": 3})
        if "COUNT(*) AS documents" in normalized:
            return FakeCursor(fetchone_result={"documents": 8})
        if "COUNT(*) AS model_calls" in normalized:
            return FakeCursor(fetchone_result={"model_calls": 21})
        if "FROM model_call_logs" in normalized:
            return FakeCursor(
                fetchall_result=[
                    {
                        "id": 9,
                        "provider_code": "dashscope",
                        "model_name": "qwen-plus",
                        "status": "succeeded",
                        "latency_ms": 1234,
                        "created_at": "2026-06-23 10:00:00",
                        "project_id": 2,
                        "generation_task_id": 5,
                        "error_message": "",
                    }
                ]
            )
        raise AssertionError(f"Unexpected SQL: {normalized}")

    def close(self):
        self.closed = True


class AdminSettingsApiTest(unittest.TestCase):
    def setUp(self):
        from api import settings

        self.settings = settings
        self.fake_conn = FakeConn()
        self.original_get_db = getattr(settings, "get_db", None)
        settings.get_db = lambda: self.fake_conn
        app = Flask(__name__)
        app.register_blueprint(settings.bp, url_prefix="/api/settings")
        self.client = app.test_client()

    def tearDown(self):
        if self.original_get_db is None:
            delattr(self.settings, "get_db")
        else:
            self.settings.get_db = self.original_get_db

    def test_dashboard_stats_returns_admin_counts(self):
        response = self.client.get("/api/settings/dashboard-stats")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"projects": 3, "documents": 8, "modelCalls": 21})
        self.assertTrue(self.fake_conn.closed)

    def test_model_logs_returns_recent_model_calls(self):
        response = self.client.get("/api/settings/model-logs")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["provider_code"], "dashscope")
        self.assertEqual(payload["items"][0]["model_name"], "qwen-plus")
        self.assertEqual(payload["items"][0]["status"], "succeeded")
        self.assertEqual(payload["items"][0]["latency_ms"], 1234)


if __name__ == "__main__":
    unittest.main()
