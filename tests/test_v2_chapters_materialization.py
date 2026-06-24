import json
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
    def __init__(self, conn, fetchone_result=None, fetchall_result=None):
        self.conn = conn
        self._fetchone_result = fetchone_result
        self._fetchall_result = fetchall_result or []
        self.lastrowid = None

    def execute(self, sql, params=()):
        return self.conn.execute(sql, params, cursor=self)

    def fetchone(self):
        return self._fetchone_result

    def fetchall(self):
        return self._fetchall_result


class FakeConn:
    def __init__(self):
        self.created_documents = []
        self.created_chapters = []
        self.committed = False
        self.closed = False
        self.next_id = 100

    def cursor(self):
        return FakeCursor(self)

    def execute(self, sql, params=(), cursor=None):
        normalized = " ".join(sql.split())
        if "SELECT * FROM bid_projects WHERE id=?" in normalized:
            return FakeCursor(
                self,
                fetchone_result={
                    "id": 5,
                    "project_name": "测试项目",
                    "directory_structure": json.dumps(
                        {
                            "chapters": [
                                {"title": "1. 投标函", "type": "locked_template", "sourceText": "投标函正文"},
                                {"title": "2. 法定代表人身份证明", "type": "locked_template", "sourceText": "身份证明正文"},
                            ]
                        },
                        ensure_ascii=False,
                    ),
                },
            )
        if "FROM bid_documents" in normalized and "ORDER BY id DESC" in normalized:
            return FakeCursor(self, fetchone_result={"id": 9})
        if "SELECT * FROM bid_chapters" in normalized:
            return FakeCursor(
                self,
                fetchall_result=[
                    {
                        "id": 21,
                        "project_id": 5,
                        "bid_document_id": 9,
                        "chapter_title": "2. 甲方如错误通知到货地点、接货人的，应承担乙方因此所受到的实际损失。",
                        "chapter_type": "locked_outline",
                        "sort_order": 0,
                        "outline_json": "{}",
                        "current_version_id": None,
                        "status": "planned",
                    },
                    {
                        "id": 22,
                        "project_id": 5,
                        "bid_document_id": 9,
                        "chapter_title": "3. /",
                        "chapter_type": "locked_outline",
                        "sort_order": 1,
                        "outline_json": "{}",
                        "current_version_id": None,
                        "status": "planned",
                    },
                ],
            )
        if "AS protected_count" in normalized:
            return FakeCursor(self, fetchone_result={"protected_count": 0})
        if normalized.startswith("INSERT INTO bid_documents"):
            self.next_id += 1
            target = cursor or FakeCursor(self)
            target.lastrowid = self.next_id
            self.created_documents.append({"id": self.next_id, "params": params})
            return target
        if normalized.startswith("INSERT INTO bid_chapters"):
            self.next_id += 1
            target = cursor or FakeCursor(self)
            target.lastrowid = self.next_id
            self.created_chapters.append({"id": self.next_id, "params": params})
            return target
        raise AssertionError(f"Unexpected SQL: {normalized}")

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class V2ChapterMaterializationTest(unittest.TestCase):
    def test_recreates_latest_empty_chapter_document_when_outline_changed(self):
        from api.v2 import chapters

        fake_conn = FakeConn()
        original_get_db = chapters.get_db
        chapters.get_db = lambda: fake_conn
        try:
            chapters._materialize_project_chapters(5)
        finally:
            chapters.get_db = original_get_db

        self.assertTrue(fake_conn.committed)
        self.assertEqual(len(fake_conn.created_documents), 1)
        inserted_titles = [item["params"][2] for item in fake_conn.created_chapters]
        self.assertEqual(inserted_titles, ["1. 投标函", "2. 法定代表人身份证明"])


if __name__ == "__main__":
    unittest.main()
