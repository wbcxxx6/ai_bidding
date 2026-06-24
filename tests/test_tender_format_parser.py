import unittest

from services.tender_format_parser import parse_tender_format


SAMPLE_TENDER = """
第一章 招标公告
本项目采购企业数字化平台建设服务。

第六章 响应文件格式
响应文件应按以下格式编制并加盖公章。

一、投标函
致：采购人
我方愿意参加本项目投标。

二、法定代表人身份证明
法定代表人姓名：____

三、授权委托书
委托代理人姓名：____

四、报价表
报价总价：____

五、技术响应文件
投标人应逐条响应技术要求并提供实施方案。
"""

TENDER_WITH_TOC_AND_REAL_TEMPLATE = """
目录
第六章 响应文件格式 43
1. 投标函 43
2. 法定代表人身份证明 44
3. 授权委托书 45

第六章 响应文件格式
1. 投标函

投标函

致：中交天航（宜宾）交通工程建设有限公司

1.我方已经仔细阅读（招标编号）招标文件，同意招标人在招标文件中对投标方的约束。

2.如果我方的投标被接受，我方将严格执行招标文件中的各项条款。

2. 法定代表人身份证明
法定代表人姓名：____
"""


class TenderFormatParserTest(unittest.TestCase):
    def test_extracts_chapters_from_response_file_format_section_in_order(self):
        result = parse_tender_format(SAMPLE_TENDER, {})

        self.assertTrue(result["detected"])
        self.assertEqual(result["source"], "tender_text")
        self.assertGreaterEqual(result["confidence"], 0.6)
        self.assertEqual(result["formatSections"][0]["heading"], "第六章 响应文件格式")

        titles = [chapter["title"] for chapter in result["chapters"]]
        self.assertEqual(
            titles,
            ["一、投标函", "二、法定代表人身份证明", "三、授权委托书", "四、报价表", "五、技术响应文件"],
        )

        for chapter in result["chapters"]:
            self.assertTrue(chapter["lockTitle"])
            self.assertTrue(chapter["lockOrder"])
            self.assertIn("sourceText", chapter)
            self.assertEqual(chapter["sourceHeading"], "第六章 响应文件格式")

    def test_classifies_template_and_outline_chapters(self):
        result = parse_tender_format(SAMPLE_TENDER, {})
        by_title = {chapter["title"]: chapter for chapter in result["chapters"]}

        self.assertEqual(by_title["一、投标函"]["type"], "locked_template")
        self.assertEqual(by_title["二、法定代表人身份证明"]["type"], "locked_template")
        self.assertEqual(by_title["三、授权委托书"]["type"], "locked_template")
        self.assertEqual(by_title["四、报价表"]["type"], "locked_template")
        self.assertEqual(by_title["五、技术响应文件"]["type"], "locked_outline")

    def test_returns_manual_review_shape_when_no_format_section_is_found(self):
        result = parse_tender_format("本项目采用综合评分法，技术分为40分。", {})

        self.assertFalse(result["detected"])
        self.assertEqual(result["source"], "none")
        self.assertEqual(result["chapters"], [])
        self.assertTrue(result["questions"])

    def test_prefers_real_template_section_over_table_of_contents(self):
        result = parse_tender_format(TENDER_WITH_TOC_AND_REAL_TEMPLATE, {})

        self.assertTrue(result["detected"])
        self.assertEqual(result["chapters"][0]["title"], "1. 投标函")
        self.assertEqual(result["chapters"][0]["templateStatus"], "valid")
        self.assertIn("致：中交天航", result["chapters"][0]["sourceText"])
        self.assertIn("我方已经仔细阅读", result["chapters"][0]["sourceText"])
        self.assertNotIn("法定代表人身份证明 44", result["chapters"][0]["sourceText"])

    def test_marks_toc_only_template_chapters_as_invalid_templates(self):
        tender = """
第六章 响应文件格式
投标函 43
法定代表人身份证明 44
授权委托书 45
"""
        result = parse_tender_format(tender, {})

        self.assertTrue(result["detected"])
        self.assertEqual(result["chapters"][0]["templateStatus"], "toc_only")

    def test_does_not_split_template_body_numbered_sentences_as_chapters(self):
        tender = """
第六章 响应文件格式
1. 投标函

投标函

致：采购人

1.我方已经仔细阅读招标文件，并承诺完全响应本项目采购需求。

2.如果我方中标，我方将按合同约定履行全部责任。

2. 法定代表人身份证明
法定代表人姓名：____
"""

        result = parse_tender_format(tender, {})

        self.assertEqual([chapter["title"] for chapter in result["chapters"]], ["1. 投标函", "2. 法定代表人身份证明"])
        self.assertIn("1.我方已经仔细阅读", result["chapters"][0]["sourceText"])

    def test_ignores_contract_clause_noise_when_extracting_format_chapters(self):
        tender = """
第六章 响应文件格式
响应文件应包含以下章节。

1. 投标函
致：采购人
我方承诺响应招标文件。

2. 甲方如错误通知到货地点、接货人的，应承担乙方因此所受到的实际损失。

6. 乙方若提前交货，必须征得甲方书面同意，否则甲方可不予接收货物，因此造成的一切损失均由乙方负责。

3. /

2. 法定代表人身份证明
法定代表人姓名：____
"""

        result = parse_tender_format(tender, {})

        titles = [chapter["title"] for chapter in result["chapters"]]
        self.assertEqual(titles, ["1. 投标函", "2. 法定代表人身份证明"])
        self.assertNotIn("甲方如错误通知到货地点", "\n".join(titles))
        self.assertNotIn("乙方若提前交货", "\n".join(titles))
        self.assertNotIn("3. /", titles)

    def test_keeps_legitimate_contract_response_chapter_title(self):
        tender = """
第六章 响应文件格式
1. 商务合同条款响应
投标人应逐条响应商务合同条款。

2. 技术响应文件
投标人应逐条响应技术要求。
"""

        result = parse_tender_format(tender, {})

        self.assertEqual([chapter["title"] for chapter in result["chapters"]], ["1. 商务合同条款响应", "2. 技术响应文件"])

    def test_keeps_long_template_source_text_for_exact_copy(self):
        long_body = "\n".join(f"{idx}.我方承诺按招标文件要求执行第{idx}项内容。" for idx in range(1, 260))
        tender = f"""
第六章 响应文件格式
1. 投标函

投标函

致：采购人

{long_body}

2. 法定代表人身份证明
法定代表人姓名：____
"""

        result = parse_tender_format(tender, {})

        self.assertIn("第250项内容", result["chapters"][0]["sourceText"])


if __name__ == "__main__":
    unittest.main()
