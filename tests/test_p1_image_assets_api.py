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
    lastrowid = 11

    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))


class FakeConn:
    def __init__(self):
        self.executed = []
        self.committed = False
        self.closed = False
        self.asset = {
            "id": 11,
            "company_id": None,
            "project_id": 3,
            "file_id": 21,
            "asset_title": "企业系统架构图",
            "image_type": "architecture_diagram",
            "source_type": "enterprise_upload",
            "caption": "系统架构设计图",
            "searchable_text": "企业系统架构图 系统架构设计图 技术标",
            "tags_json": '["技术标"]',
            "allowed_for_bid": 1,
            "synthetic": 0,
            "review_status": "approved",
            "metadata_json": "{}",
            "created_by": 1,
            "created_at": "2026-06-10 00:00:00",
            "updated_at": "2026-06-10 00:00:00",
        }

    def cursor(self):
        return FakeCursor(self)

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if "WHERE id=?" in sql:
            return types.SimpleNamespace(fetchone=lambda: self.asset)
        return types.SimpleNamespace(fetchall=lambda: [self.asset])

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class P1ImageAssetsApiTest(unittest.TestCase):
    def setUp(self):
        self.conn = FakeConn()
        import services.v2.image_asset_service as service

        self.service = service
        self.original_get_db = service.get_db
        service.get_db = lambda: self.conn

    def tearDown(self):
        self.service.get_db = self.original_get_db

    def test_create_image_asset_defaults_search_text_and_returns_item(self):
        asset = self.service.create_image_asset(
            {
                "projectId": 3,
                "fileId": 21,
                "assetTitle": "企业系统架构图",
                "imageType": "architecture_diagram",
                "caption": "系统架构设计图",
                "tags": ["技术标"],
                "userId": 1,
            }
        )

        self.assertEqual(asset["id"], 11)
        self.assertEqual(asset["assetTitle"], "企业系统架构图")
        self.assertTrue(self.conn.committed)
        insert_params = self.conn.executed[0][1]
        self.assertIn("企业系统架构图", insert_params[7])
        self.assertIn("技术标", insert_params[7])

    def test_list_image_assets_filters_project_and_type(self):
        items = self.service.list_image_assets(project_id=3, image_type="architecture_diagram", allowed_for_bid=True)

        self.assertEqual(items[0]["imageType"], "architecture_diagram")
        query, params = self.conn.executed[0]
        self.assertIn("image_type=?", query)
        self.assertEqual(params[0], 3)
        self.assertEqual(params[1], "architecture_diagram")
        self.assertEqual(params[2], 1)


if __name__ == "__main__":
    unittest.main()
