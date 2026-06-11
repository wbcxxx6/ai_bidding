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
sys.modules.setdefault("requests", types.SimpleNamespace(post=lambda *args, **kwargs: None))
sys.modules.setdefault(
    "services.retrieval_router",
    types.SimpleNamespace(
        retrieval_router=types.SimpleNamespace(search=lambda *args, **kwargs: {"items": []})
    ),
)

from services.v2.followup_service import build_followup_questions
from services.v2.image_markdown_service import append_image_plan_placeholders
from services.v2.image_plan_service import plan_chapter_images


class P1ImageAndFollowupTest(unittest.TestCase):
    def test_image_planner_detects_architecture_image_need(self):
        chapter = {
            "id": 7,
            "projectId": 3,
            "title": "系统架构设计",
            "description": "说明总体架构、数据流、部署拓扑和集成关系。",
        }

        plans = plan_chapter_images(chapter, context_items=[])

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["imageType"], "architecture_diagram")
        self.assertEqual(plans[0]["sourcePriority"][0], "enterprise_image")
        self.assertIn("系统架构设计", plans[0]["caption"])

    def test_image_planner_selects_matching_enterprise_image_asset(self):
        chapter = {
            "id": 7,
            "projectId": 3,
            "title": "系统架构设计",
            "description": "说明总体架构、数据流、部署拓扑和集成关系。",
        }

        plans = plan_chapter_images(
            chapter,
            context_items=[
                {
                    "sourceType": "image_asset",
                    "doc_type": "image_asset",
                    "image_type": "architecture_diagram",
                    "source_type": "enterprise_upload",
                    "source_title": "企业系统架构图",
                    "file_id": 31,
                    "content": "系统架构图，适用于技术标。",
                }
            ],
        )

        self.assertEqual(plans[0]["status"], "selected")
        self.assertEqual(plans[0]["matchedAssets"][0]["sourcePriority"], "enterprise_image")

    def test_followup_questions_include_missing_citation_and_image_actions(self):
        questions = build_followup_questions(
            chapter={"id": 7, "title": "系统架构设计"},
            context_items=[],
            image_plans=[
                {
                    "imageType": "architecture_diagram",
                    "status": "pending_asset",
                    "caption": "系统架构设计图",
                }
            ],
        )

        actions = {question["action"] for question in questions}
        self.assertIn("upload_knowledge", actions)
        self.assertIn("upload_image_asset", actions)
        self.assertTrue(any("系统架构设计" in question["question"] for question in questions))

    def test_generation_markdown_includes_image_plan_placeholders(self):
        markdown = append_image_plan_placeholders(
            "## 系统架构设计\n\n本节描述系统架构。",
            [
                {
                    "id": 9,
                    "caption": "系统架构设计图",
                    "status": "pending_asset",
                }
            ],
        )

        self.assertIn("![系统架构设计图](image-plan://9)", markdown)
        self.assertEqual(markdown.count("image-plan://9"), 1)


if __name__ == "__main__":
    unittest.main()
