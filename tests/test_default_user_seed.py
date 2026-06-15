import importlib
import sys
import types
import unittest


class RecordingCursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class RecordingConnection:
    def __init__(self):
        self.cursor_obj = RecordingCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True


class DefaultUserSeedTest(unittest.TestCase):
    def setUp(self):
        fake_pymysql = types.SimpleNamespace(
            connect=lambda **kwargs: None,
            cursors=types.SimpleNamespace(DictCursor=object),
            err=types.SimpleNamespace(OperationalError=Exception),
        )
        sys.modules.setdefault("pymysql", fake_pymysql)
        sys.modules.setdefault("pymysql.cursors", fake_pymysql.cursors)
        sys.modules.pop("core.db", None)
        self.db = importlib.import_module("core.db")

    def test_seed_defaults_creates_default_user_and_role_membership(self):
        conn = RecordingConnection()

        self.db.seed_defaults(conn)

        executed_sql = "\n".join(sql for sql, _ in conn.cursor_obj.calls)
        self.assertIn("INSERT IGNORE INTO users", executed_sql)
        self.assertIn("VALUES (1, 1, 'default-user'", executed_sql)
        self.assertIn("INSERT IGNORE INTO user_roles", executed_sql)
        self.assertTrue(conn.committed)


if __name__ == "__main__":
    unittest.main()
