import unittest

from export.flowchart_renderer import build_flowchart_svg, parse_flowchart_payload


class FlowchartRendererTest(unittest.TestCase):
    def test_parse_flowchart_payload_normalizes_nodes_and_edges(self):
        chart = parse_flowchart_payload(
            """
            {
              "title": "项目实施流程图",
              "nodes": [
                {"id": "A", "text": "需求确认"},
                {"id": "B", "text": "方案设计"}
              ],
              "edges": [{"from": "A", "to": "B"}]
            }
            """
        )

        self.assertEqual(chart["title"], "项目实施流程图")
        self.assertEqual(chart["nodes"][0]["text"], "需求确认")
        self.assertEqual(chart["edges"][0]["to"], "B")

    def test_build_flowchart_svg_contains_nodes_without_mermaid_code(self):
        chart = parse_flowchart_payload(
            {
                "title": "项目实施流程图",
                "nodes": ["需求确认", "方案设计", "测试验收"],
                "edges": [
                    {"from": "N1", "to": "N2"},
                    {"from": "N2", "to": "N3"},
                ],
            }
        )

        svg = build_flowchart_svg(chart)

        self.assertIn("<svg", svg)
        self.assertIn("需求确认", svg)
        self.assertIn("方案设计", svg)
        self.assertNotIn("flowchart TD", svg)


if __name__ == "__main__":
    unittest.main()
