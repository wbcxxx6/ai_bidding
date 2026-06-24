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
sys.modules.setdefault(
    "export.md_to_word",
    types.SimpleNamespace(convert_md_to_word=lambda *args, **kwargs: "/tmp/mock.docx"),
)
sys.modules.setdefault(
    "storage.storage_service",
    types.SimpleNamespace(
        storage_service=types.SimpleNamespace(
            create_file=lambda **kwargs: types.SimpleNamespace(file_id=91, storage_key="mysql://document_files/91/versions/1")
        )
    ),
)
sys.modules.setdefault(
    "services.v2.chapter_generation_service",
    types.SimpleNamespace(run_chapter_generation=lambda task_id: iter([])),
)
sys.modules.setdefault(
    "services.v2.agent_task_service",
    types.SimpleNamespace(
        append_event=lambda *args, **kwargs: {"id": 1},
        create_task=lambda **kwargs: {"id": 501, "projectId": kwargs.get("project_id"), "taskType": kwargs.get("task_type")},
        get_task=lambda task_id: {"id": task_id, "projectId": 9, "taskType": "project_export", "status": "queued", "createdBy": 1, "input": {}},
        list_events=lambda task_id: [],
        update_task=lambda *args, **kwargs: None,
    ),
)
sys.modules.setdefault(
    "services.agent_orchestrator",
    types.SimpleNamespace(word_count=lambda text: len(text or "")),
)


class ProjectGenerationServiceTest(unittest.TestCase):
    def test_merge_sections_keeps_content_order(self):
        from services.v2.project_generation_service import _merge_sections

        merged = _merge_sections(
            [
                {"chapter_title": "第一章", "current_content": "## 第一章\n\n正文A"},
                {"chapter_title": "第二章", "current_content": "正文B"},
            ]
        )

        self.assertIn("## 第一章", merged)
        self.assertIn("## 第2章 第二章", merged)
        self.assertIn("正文B", merged)


if __name__ == "__main__":
    unittest.main()
