import json
import sys
import types
import unittest

sys.modules.setdefault("requests", types.SimpleNamespace(post=lambda *args, **kwargs: None))
fake_pymysql = types.SimpleNamespace(
    connect=lambda **kwargs: None,
    cursors=types.SimpleNamespace(DictCursor=object),
    err=types.SimpleNamespace(OperationalError=Exception),
)
sys.modules.setdefault("pymysql", fake_pymysql)
sys.modules.setdefault("pymysql.cursors", fake_pymysql.cursors)

from services.model_center.stream import _iter_openai_sse


class FakeStreamResponse:
    def __init__(self, lines):
        self.lines = lines

    def iter_lines(self, decode_unicode=False):
        for line in self.lines:
            if decode_unicode:
                yield line.decode("latin-1")
            else:
                yield line


class ModelStreamEncodingTest(unittest.TestCase):
    def test_openai_sse_stream_decodes_utf8_tokens(self):
        payload = {
            "choices": [
                {
                    "delta": {
                        "content": "第一章 响应文件格式",
                    }
                }
            ]
        }
        line = f"data: {json.dumps(payload, ensure_ascii=False)}".encode("utf-8")

        chunks = list(_iter_openai_sse(FakeStreamResponse([line])))

        self.assertEqual(chunks, ["第一章 响应文件格式"])


if __name__ == "__main__":
    unittest.main()
