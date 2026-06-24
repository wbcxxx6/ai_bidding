import importlib
import sys
import types
import unittest


class TemplateMergeTest(unittest.TestCase):
    def setUp(self):
        class FakeBlueprint:
            def route(self, *args, **kwargs):
                def decorator(fn):
                    return fn

                return decorator

        fake_pymysql = types.SimpleNamespace(
            connect=lambda **kwargs: None,
            cursors=types.SimpleNamespace(DictCursor=object),
            err=types.SimpleNamespace(OperationalError=Exception),
        )
        fake_flask = types.SimpleNamespace(
            Blueprint=lambda *args, **kwargs: FakeBlueprint(),
            jsonify=lambda value=None, *args, **kwargs: value,
            request=types.SimpleNamespace(get_json=lambda *args, **kwargs: {}),
        )
        sys.modules.setdefault("flask", fake_flask)
        sys.modules.setdefault("jwt", types.SimpleNamespace(encode=lambda *args, **kwargs: "token"))
        sys.modules.setdefault("requests", types.SimpleNamespace(get=lambda *args, **kwargs: None))
        sys.modules.setdefault("pymysql", fake_pymysql)
        sys.modules.setdefault("pymysql.cursors", fake_pymysql.cursors)
        sys.modules.setdefault("markdown", types.SimpleNamespace(markdown=lambda value, **kwargs: value))
        sys.modules.setdefault(
            "export.md_to_word",
            types.SimpleNamespace(convert_md_to_word=lambda *args, **kwargs: None),
        )
        sys.modules.setdefault(
            "services.agent_orchestrator",
            types.SimpleNamespace(
                agent_runs=types.SimpleNamespace(),
                build_writer_context=lambda *args, **kwargs: None,
                check_chapter_consistency=lambda *args, **kwargs: None,
                create_chapter_version=lambda *args, **kwargs: None,
                create_compliance_report=lambda *args, **kwargs: None,
                create_evidence_pack=lambda *args, **kwargs: None,
                create_response_matrix_from_analysis=lambda *args, **kwargs: None,
                mark_response_matrix_coverage=lambda *args, **kwargs: None,
                run_fact_keeper_agent=lambda *args, **kwargs: None,
                run_tender_parser_agent=lambda *args, **kwargs: None,
            ),
        )
        sys.modules.setdefault(
            "services.ingestion_service",
            types.SimpleNamespace(
                extract_text_from_bytes=lambda *args, **kwargs: "",
                ingest_document=lambda *args, **kwargs: None,
            ),
        )
        sys.modules.setdefault(
            "services.qwen_client",
            types.SimpleNamespace(
                call_dashscope_api=lambda *args, **kwargs: None,
                generate_bid_section=lambda *args, **kwargs: "",
            ),
        )
        sys.modules.setdefault(
            "storage.storage_service",
            types.SimpleNamespace(
                BlobTooLarge=Exception,
                FileTypeNotAllowed=Exception,
                storage_service=types.SimpleNamespace(),
            ),
        )
        sys.modules.pop("api.bidding", None)
        self.bidding = importlib.import_module("api.bidding")

    def test_locked_template_content_is_not_wrapped_as_generated_chapter(self):
        content = "# 投标函\n\n致：中交天航（宜宾）交通工程建设有限公司\n\n1.我方已经仔细阅读招标文件。"

        merged = self.bidding.merge_sections([("投标函", content, {"type": "locked_template"})])

        self.assertTrue(merged.startswith("<!-- locked_template -->\n# 投标函"))
        self.assertIn("<!-- /locked_template -->", merged)
        self.assertNotIn("## 第1章 投标函", merged)
        self.assertIn("致：中交天航", merged)

    def test_locked_template_content_is_copied_without_auto_title(self):
        content = "1. 投标函\n\n投标函\n\n致：采购人\n\n1.我方已经仔细阅读招标文件。"

        merged = self.bidding.merge_sections([("投标函", content, {"type": "locked_template"})])

        self.assertIn("<!-- locked_template -->\n1. 投标函", merged)
        self.assertNotIn("# 投标函", merged)
        self.assertEqual(merged.count("投标函"), content.count("投标函"))

    def test_enterprise_info_replacement_skips_locked_template_blocks(self):
        content = (
            "<!-- locked_template -->\n"
            "投标函\n\n"
            "致：采购人\n\n"
            "本项目按招标文件原文保留。\n"
            "<!-- /locked_template -->\n\n"
            "### 服务方案\n\n"
            "本项目由投标人负责实施。"
        )

        def fake_get_db():
            class FakeConn:
                def execute(self, sql, params=()):
                    if "FROM project_facts" in sql:
                        class FakeRows(list):
                            def fetchall(self):
                                return self

                        return FakeRows([
                            {"fact_key": "project_name", "fact_value": "智慧平台项目"},
                            {"fact_key": "bidder_name", "fact_value": "示例科技有限公司"},
                        ])

                    class FakeOne:
                        def fetchone(self):
                            return None

                    return FakeOne()

                def close(self):
                    pass

            return FakeConn()

        original_get_db = self.bidding.get_db
        self.bidding.get_db = fake_get_db
        try:
            replaced = self.bidding._fill_enterprise_info(1, content)
        finally:
            self.bidding.get_db = original_get_db

        self.assertIn("本项目按招标文件原文保留", replaced)
        self.assertIn("智慧平台项目由投标人负责实施", replaced)

    def test_template_generation_blockers_reject_toc_only_template(self):
        blockers = self.bidding._template_generation_blockers(
            [
                {
                    "title": "投标函",
                    "type": "locked_template",
                    "templateStatus": "toc_only",
                    "sourceText": "投标函 43",
                }
            ],
            {},
        )

        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0]["title"], "投标函")
        self.assertIn("目录项", blockers[0]["reason"])

    def test_template_generation_blockers_allow_valid_source_template(self):
        blockers = self.bidding._template_generation_blockers(
            [
                {
                    "title": "投标函",
                    "type": "locked_template",
                    "templateStatus": "valid",
                    "sourceText": "投标函\n\n致：采购人\n\n我方已经仔细阅读招标文件，并承诺完全响应招标文件中规定的全部实质性要求。\n\n签字：____",
                }
            ],
            {},
        )

        self.assertEqual(blockers, [])


if __name__ == "__main__":
    unittest.main()
