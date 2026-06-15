import importlib
import sys
import types
import unittest


class FakeParagraph:
    def __init__(self):
        self.text = ""
        self.alignment = None
        self.paragraph_format = types.SimpleNamespace(first_line_indent=None, line_spacing=None, space_after=None)
        self.runs = []

    def add_run(self, text=""):
        run = types.SimpleNamespace(
            text=text,
            font=types.SimpleNamespace(name=None, size=None, color=types.SimpleNamespace(rgb=None)),
            bold=False,
        )
        self.runs.append(run)
        self.text += text
        return run


class FakeCell:
    def __init__(self):
        self.text = ""
        self.paragraphs = [FakeParagraph()]


class FakeRow:
    def __init__(self, cols):
        self.cells = [FakeCell() for _ in range(cols)]


class FakeTable:
    def __init__(self, rows, cols):
        self.rows = [FakeRow(cols) for _ in range(rows)]
        self.style = None

    def add_row(self):
        row = FakeRow(len(self.rows[0].cells) if self.rows else 1)
        self.rows.append(row)
        return row


class FakeDoc:
    def __init__(self):
        self.paragraphs = []
        self.tables = []
        self.pictures = []

    def add_paragraph(self, text=None, style=None):
        paragraph = FakeParagraph()
        if text:
            paragraph.add_run(text)
        self.paragraphs.append(paragraph)
        return paragraph

    def add_table(self, rows=1, cols=1):
        table = FakeTable(rows, cols)
        self.tables.append(table)
        return table

    def add_picture(self, path, width=None):
        self.pictures.append({"path": path, "width": width})
        paragraph = self.add_paragraph()
        return paragraph


class WordImagePlaceholderTest(unittest.TestCase):
    def setUp(self):
        fake_docx = types.ModuleType("docx")
        fake_docx.__path__ = []
        fake_docx.Document = lambda *args, **kwargs: FakeDoc()
        fake_docx_shared = types.ModuleType("docx.shared")
        fake_docx_shared.Inches = lambda value: value
        fake_docx_shared.Cm = lambda value: value
        fake_docx_shared.Pt = lambda value: value
        fake_docx_shared.RGBColor = lambda *args: args
        fake_docx_enum = types.ModuleType("docx.enum")
        fake_docx_enum_text = types.ModuleType("docx.enum.text")
        fake_docx_enum_text.WD_ALIGN_PARAGRAPH = types.SimpleNamespace(CENTER=1)
        fake_docx_enum_text.WD_LINE_SPACING = types.SimpleNamespace()
        fake_docx_enum_style = types.ModuleType("docx.enum.style")
        fake_docx_enum_style.WD_STYLE_TYPE = types.SimpleNamespace(PARAGRAPH=1)
        fake_docx_oxml = types.ModuleType("docx.oxml")
        fake_docx_oxml.OxmlElement = lambda name: types.SimpleNamespace(set=lambda *args: None)
        fake_docx_oxml_ns = types.ModuleType("docx.oxml.ns")
        fake_docx_oxml_ns.qn = lambda value: value
        fake_docx_oxml_shared = types.ModuleType("docx.oxml.shared")

        sys.modules["docx"] = fake_docx
        sys.modules["markdown"] = types.SimpleNamespace(markdown=lambda value, **kwargs: value)
        sys.modules["docx.shared"] = fake_docx_shared
        sys.modules["docx.enum"] = fake_docx_enum
        sys.modules["docx.enum.text"] = fake_docx_enum_text
        sys.modules["docx.enum.style"] = fake_docx_enum_style
        sys.modules["docx.oxml"] = fake_docx_oxml
        sys.modules["docx.oxml.ns"] = fake_docx_oxml_ns
        sys.modules["docx.oxml.shared"] = fake_docx_oxml_shared
        fake_docx.shared = fake_docx_shared
        fake_docx.enum = types.SimpleNamespace(
            text=fake_docx_enum_text,
            style=fake_docx_enum_style,
        )
        fake_docx.oxml = fake_docx_oxml
        sys.modules.pop("export.md_to_word", None)
        self.md_to_word = importlib.import_module("export.md_to_word")

    def test_add_image_placeholder_caption(self):
        doc = FakeDoc()

        handled = self.md_to_word.add_image_placeholder(doc, "![系统架构设计图](image-plan://7)")

        self.assertTrue(handled)
        self.assertIn("图", doc.paragraphs[0].text)
        self.assertIn("系统架构设计图", doc.paragraphs[0].text)
        self.assertIn("图片待补充", doc.paragraphs[0].text)

    def test_process_structured_flowchart_does_not_write_code_text(self):
        doc = FakeDoc()

        handled = self.md_to_word.process_structured_flowchart(
            doc,
            """
            {"title":"项目实施流程图","nodes":["需求确认","方案设计"],"edges":[{"from":"N1","to":"N2"}]}
            """,
        )

        all_text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
        table_text = "\n".join(cell.paragraphs[0].text or cell.text for table in doc.tables for row in table.rows for cell in row.cells)
        self.assertTrue(handled)
        self.assertNotIn('"nodes"', all_text + table_text)
        self.assertNotIn("flowchart TD", all_text + table_text)
        self.assertTrue(doc.pictures or doc.tables)

    def test_process_table_accepts_unwrapped_rows_and_html_breaks(self):
        doc = FakeDoc()

        self.md_to_word.process_table(
            "\n".join(
                [
                    "招标文件要求 | 本方案响应内容 | 证明材料",
                    "--- | --- | ---",
                    "产品/货物名称<br>规格型号 | 散热风扇<br>120mm / 24V | 产品彩页<br>检测报告",
                ]
            ),
            doc,
        )

        self.assertEqual(len(doc.tables), 1)
        table = doc.tables[0]
        self.assertEqual(len(table.rows), 2)
        body_text = "\n".join(cell.paragraphs[0].text or cell.text for cell in table.rows[1].cells)
        self.assertIn("散热风扇", body_text)
        self.assertIn("120mm / 24V", body_text)
        self.assertNotIn("<br>", body_text)


if __name__ == "__main__":
    unittest.main()
