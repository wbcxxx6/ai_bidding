import importlib
import os
import sys
import types
import unittest


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self.payload


class WanImageServiceTest(unittest.TestCase):
    def setUp(self):
        self.old_key = os.environ.get("DASHSCOPE_API_KEY")
        self.old_model = os.environ.get("WAN_IMAGE_MODEL")
        os.environ["DASHSCOPE_API_KEY"] = "sk-test"
        os.environ.pop("WAN_IMAGE_MODEL", None)
        sys.modules.setdefault(
            "requests",
            types.SimpleNamespace(post=lambda *args, **kwargs: None, get=lambda *args, **kwargs: None),
        )
        sys.modules.pop("services.v2.wan_image_service", None)
        self.service = importlib.import_module("services.v2.wan_image_service")

    def tearDown(self):
        if self.old_key is None:
            os.environ.pop("DASHSCOPE_API_KEY", None)
        else:
            os.environ["DASHSCOPE_API_KEY"] = self.old_key
        if self.old_model is None:
            os.environ.pop("WAN_IMAGE_MODEL", None)
        else:
            os.environ["WAN_IMAGE_MODEL"] = self.old_model

    def test_build_prompt_extracts_fan_specs_from_section_text(self):
        prompt_data = self.service.build_section_image_prompt(
            "本节配置散热风扇，规格为120mm、24V DC、转速3000RPM，要求低噪声和金属防护网。",
            chapter_title="设备配置",
        )

        self.assertEqual(prompt_data["imageType"], "product_image")
        self.assertIn("散热风扇", prompt_data["prompt"])
        self.assertIn("120mm", prompt_data["prompt"])
        self.assertIn("24V", prompt_data["specs"])
        self.assertIn("3000RPM", prompt_data["specs"])

    def test_create_generation_task_uses_dashscope_async_protocol(self):
        calls = []

        def fake_post(url, headers=None, json=None, timeout=None):
            calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
            return FakeResponse({"output": {"task_id": "task-123", "task_status": "PENDING"}, "request_id": "req-1"})

        self.service.requests.post = fake_post

        result = self.service.create_wan_image_task(
            prompt="正式产品图，散热风扇，120mm，24V",
            model="wan2.7-t2i",
            size="1024*1024",
        )

        self.assertEqual(result["taskId"], "task-123")
        self.assertEqual(calls[0]["url"], "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis")
        self.assertEqual(calls[0]["headers"]["X-DashScope-Async"], "enable")
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer sk-test")
        self.assertEqual(calls[0]["json"]["model"], "wan2.7-t2i")
        self.assertEqual(calls[0]["json"]["parameters"]["size"], "1024*1024")

    def test_forbidden_document_image_types_are_rejected(self):
        with self.assertRaises(ValueError):
            self.service.build_section_image_prompt("请生成营业执照、身份证和资质证书扫描件。")


if __name__ == "__main__":
    unittest.main()
