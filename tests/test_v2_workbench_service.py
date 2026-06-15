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


class FakeCursor:
    def __init__(self, fetchall_result=None, fetchone_result=None):
        self._fetchall_result = fetchall_result or []
        self._fetchone_result = fetchone_result

    def fetchall(self):
        return self._fetchall_result

    def fetchone(self):
        return self._fetchone_result


class FakeConn:
    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        if "FROM bid_chapters c" in normalized:
            return FakeCursor(
                fetchall_result=[
                    {
                        "id": 11,
                        "project_id": 5,
                        "bid_document_id": 3,
                        "chapter_title": "技术方案与系统架构",
                        "chapter_type": "normal",
                        "sort_order": 1,
                        "status": "planned",
                        "current_version_id": 8,
                        "content_text": "这是技术方案内容",
                        "editor_version_no": 2,
                        "citation_count": 3,
                        "image_plan_count": 1,
                        "pending_image_plan_count": 1,
                        "followup_count": 2,
                        "pending_followup_count": 1,
                        "latest_task_id": 101,
                        "latest_task_status": "succeeded",
                        "latest_task_created_at": "2026-06-11 09:00:00",
                        "latest_task_finished_at": "2026-06-11 09:02:00",
                    },
                    {
                        "id": 12,
                        "project_id": 5,
                        "bid_document_id": 3,
                        "chapter_title": "商务条款响应",
                        "chapter_type": "normal",
                        "sort_order": 2,
                        "status": "planned",
                        "current_version_id": None,
                        "content_text": "",
                        "editor_version_no": 0,
                        "citation_count": 0,
                        "image_plan_count": 0,
                        "pending_image_plan_count": 0,
                        "followup_count": 1,
                        "pending_followup_count": 1,
                        "latest_task_id": 102,
                        "latest_task_status": "queued",
                        "latest_task_created_at": "2026-06-11 09:05:00",
                        "latest_task_finished_at": None,
                    },
                ]
            )
        if "FROM bid_projects" in normalized:
            return FakeCursor(
                fetchone_result={
                    "id": 5,
                    "project_name": "智慧园区平台项目",
                    "project_status": "generating",
                    "generated_file_id": 88,
                    "directory_structure": None,
                }
            )
        if "FROM agent_task" in normalized:
            return FakeCursor(
                fetchall_result=[
                    {
                        "id": 102,
                        "chapter_id": 12,
                        "task_type": "chapter_generate",
                        "status": "queued",
                        "created_at": "2026-06-11 09:05:00",
                        "finished_at": None,
                        "error_message": None,
                    }
                ]
            )
        raise AssertionError(f"Unexpected SQL: {normalized}")

    def close(self):
        pass


class V2WorkbenchServiceTest(unittest.TestCase):
    def test_workbench_overview_aggregates_project_progress(self):
        from services.v2 import workbench_service

        original_get_db = workbench_service.get_db
        workbench_service.get_db = lambda: FakeConn()
        try:
            result = workbench_service.get_project_workbench_overview(5)
        finally:
            workbench_service.get_db = original_get_db

        self.assertEqual(result["project"]["projectName"], "智慧园区平台项目")
        self.assertEqual(result["chapterStatus"]["total"], 2)
        self.assertEqual(result["chapterStatus"]["generated"], 1)
        self.assertEqual(result["stats"]["citationCount"], 3)
        self.assertEqual(result["stats"]["pendingFollowupCount"], 2)
        self.assertEqual(result["stats"]["pendingImagePlanCount"], 1)
        self.assertEqual(result["chapters"][0]["volumeType"], "technical")
        self.assertEqual(result["chapters"][1]["volumeType"], "business")
        self.assertEqual(result["volumes"][0]["chapterCount"], 1)
        self.assertGreaterEqual(len(result["pendingActions"]), 3)
        self.assertTrue(any(item["kind"] == "generate_chapter" for item in result["pendingActions"]))


if __name__ == "__main__":
    unittest.main()
