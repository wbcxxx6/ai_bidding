import importlib
import sys
import types
import unittest


class RecordingRouter:
    def __init__(self):
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return {"ok": True}


class QwenClientRoutingTest(unittest.TestCase):
    def setUp(self):
        self.router = RecordingRouter()
        fake_model_router = types.SimpleNamespace(model_router=self.router)
        sys.modules["services.model_router"] = fake_model_router
        sys.modules.pop("services.qwen_client", None)
        self.qwen_client = importlib.import_module("services.qwen_client")

    def test_dashscope_wrapper_forwards_timeout_and_retries(self):
        messages = [{"role": "user", "content": "design outline"}]

        result = self.qwen_client.call_dashscope_api(
            messages,
            task_type="chapter_design",
            project_id=42,
            timeout=25,
            retries=0,
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(self.router.calls), 1)
        call = self.router.calls[0]
        self.assertEqual(call["messages"], messages)
        self.assertEqual(call["task_type"], "chapter_design")
        self.assertEqual(call["project_id"], 42)
        self.assertEqual(call["timeout"], 25)
        self.assertEqual(call["retries"], 0)
        self.assertEqual(call["response_format"], {"type": "json_object"})


if __name__ == "__main__":
    unittest.main()
