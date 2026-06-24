import unittest

from services.template_validation import is_toc_like_text, is_valid_template_text


class TemplateValidationTest(unittest.TestCase):
    def test_rejects_table_of_contents_entry_as_template_text(self):
        text = "投标函 43\n\n法定代表人身份证明 44\n\n授权委托书 45"

        self.assertTrue(is_toc_like_text(text))
        self.assertFalse(is_valid_template_text("投标函", text))

    def test_accepts_bid_letter_body_as_template_text(self):
        text = """
1. 投标函

投标函

致：中交天航（宜宾）交通工程建设有限公司

1.我方已经仔细阅读（招标编号）招标文件，同意招标人在招标文件中对投标方的约束。

2.如果我方的投标被接受，我方将严格执行招标文件中的各项条款。
"""

        self.assertFalse(is_toc_like_text(text))
        self.assertTrue(is_valid_template_text("投标函", text))

    def test_rejects_title_only_template_text(self):
        self.assertFalse(is_valid_template_text("投标函", "投标函"))


if __name__ == "__main__":
    unittest.main()
