import unittest

from services.outline_builder import build_outline


FORMAT_PLAN = {
    "detected": True,
    "source": "tender_text",
    "confidence": 0.86,
    "formatSections": [{"heading": "第六章 响应文件格式"}],
    "chapters": [
        {
            "title": "一、投标函",
            "type": "locked_template",
            "lockTitle": True,
            "lockOrder": True,
            "sourceText": "一、投标函\n致：采购人",
            "sourceHeading": "第六章 响应文件格式",
        },
        {
            "title": "二、技术响应文件",
            "type": "locked_outline",
            "lockTitle": True,
            "lockOrder": True,
            "sourceText": "二、技术响应文件\n逐条响应技术要求。",
            "sourceHeading": "第六章 响应文件格式",
        },
    ],
    "questions": [],
}

TOC_ONLY_FORMAT_PLAN = {
    "detected": True,
    "source": "tender_text",
    "confidence": 0.5,
    "formatSections": [{"heading": "第六章 响应文件格式"}],
    "chapters": [
        {
            "title": "投标函",
            "type": "locked_template",
            "templateStatus": "toc_only",
            "lockTitle": True,
            "lockOrder": True,
            "sourceText": "投标函 43",
            "sourceHeading": "第六章 响应文件格式",
        }
    ],
    "questions": [],
}


class OutlineBuilderTest(unittest.TestCase):
    def test_builds_outline_from_format_plan_without_generic_chapters(self):
        outline = build_outline(FORMAT_PLAN, None, {"bidding_summary": "数字化平台建设"})

        self.assertEqual(outline["source"], "tender_format_first")
        self.assertFalse(outline["needsReview"])
        self.assertEqual([chapter["title"] for chapter in outline["chapters"]], ["一、投标函", "二、技术响应文件"])
        self.assertTrue(outline["chapters"][0]["lockTitle"])
        self.assertEqual(outline["chapters"][0]["type"], "locked_template")
        self.assertEqual(outline["chapters"][0]["sections"], [])
        self.assertEqual(outline["chapters"][1]["type"], "locked_outline")
        self.assertGreaterEqual(len(outline["chapters"][1]["sections"]), 1)

    def test_ai_written_chapters_have_rich_three_level_outline(self):
        outline = build_outline(FORMAT_PLAN, None, {"bidding_summary": "数字化平台建设"})
        generated_chapter = outline["chapters"][1]

        self.assertEqual(generated_chapter["type"], "locked_outline")
        self.assertGreaterEqual(generated_chapter["min_subsection_words"], 1500)
        self.assertGreaterEqual(len(generated_chapter["sections"]), 3)
        for section in generated_chapter["sections"]:
            self.assertGreaterEqual(len(section["subsections"]), 3)
            for subsection in section["subsections"]:
                self.assertGreaterEqual(subsection["min_words"], 1500)

    def test_detected_tender_format_takes_priority_over_auto_format_requirements(self):
        format_requirements = {
            "required_chapters": [
                {"title": "投标函", "description": "43", "is_mandatory": True},
                {"title": "法定代表人身份证明", "description": "44", "is_mandatory": True},
            ]
        }

        outline = build_outline(FORMAT_PLAN, format_requirements, {})

        self.assertEqual(outline["source"], "tender_format_first")
        self.assertEqual([chapter["title"] for chapter in outline["chapters"]], ["一、投标函", "二、技术响应文件"])
        self.assertEqual(outline["chapters"][0]["sourceText"], "一、投标函\n致：采购人")

    def test_user_confirmed_format_requirements_are_used_when_no_tender_format_is_detected(self):
        format_requirements = {
            "required_chapters": [
                {"title": "响应性文件目录", "description": "用户确认后的目录", "is_mandatory": True},
                {"title": "技术服务方案", "description": "用户确认后的技术章节", "is_mandatory": True},
            ]
        }

        outline = build_outline({"detected": False, "chapters": []}, format_requirements, {})

        self.assertEqual(outline["source"], "user_confirmed_format")
        self.assertEqual([chapter["title"] for chapter in outline["chapters"]], ["响应性文件目录", "技术服务方案"])
        self.assertTrue(all(chapter["lockTitle"] for chapter in outline["chapters"]))

    def test_manual_review_required_when_no_format_is_detected(self):
        outline = build_outline({"detected": False, "chapters": [], "questions": ["未识别到格式"]}, None, {})

        self.assertEqual(outline["source"], "manual_review_required")
        self.assertTrue(outline["needsReview"])
        self.assertEqual(outline["chapters"], [])
        self.assertTrue(outline["questions"])

    def test_model_enrichment_is_not_required_for_locked_template_outline(self):
        outline = build_outline(FORMAT_PLAN, None, {})

        template_chapters = [chapter for chapter in outline["chapters"] if chapter["type"] == "locked_template"]

        self.assertEqual(len(template_chapters), 1)
        self.assertEqual(template_chapters[0]["sections"], [])
        self.assertIn("不进行自由扩写", template_chapters[0]["content"])

    def test_toc_only_template_requires_review(self):
        outline = build_outline(TOC_ONLY_FORMAT_PLAN, None, {})

        self.assertTrue(outline["needsReview"])
        self.assertEqual(outline["chapters"][0]["templateStatus"], "toc_only")
        self.assertTrue(any("投标函" in question for question in outline["questions"]))

    def test_duplicate_numbered_titles_are_deduplicated(self):
        format_plan = {
            "detected": True,
            "chapters": [
                {
                    "title": "投标函",
                    "type": "locked_template",
                    "sourceText": "投标函 1",
                    "templateStatus": "toc_only",
                },
                {
                    "title": "1.投标函",
                    "type": "locked_template",
                    "sourceText": "1.投标函\n致：采购人\n我方承诺响应招标文件要求。",
                    "templateStatus": "valid",
                },
                {
                    "title": "二、法定代表人身份证明",
                    "type": "locked_template",
                    "sourceText": "二、法定代表人身份证明\n身份证明正文",
                },
                {
                    "title": "法定代表人身份证明",
                    "type": "locked_template",
                    "sourceText": "法定代表人身份证明 2",
                },
            ],
            "questions": [],
        }

        outline = build_outline(format_plan, None, {})

        self.assertEqual([chapter["title"] for chapter in outline["chapters"]], ["1.投标函", "二、法定代表人身份证明"])


if __name__ == "__main__":
    unittest.main()
