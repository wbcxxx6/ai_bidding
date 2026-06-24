import html
import json
import re


def parse_flowchart_payload(payload):
    if isinstance(payload, str):
        payload = json.loads(payload)
    title = str(payload.get("title") or "流程图").strip()
    raw_nodes = payload.get("nodes") or []
    nodes = []
    for index, node in enumerate(raw_nodes, start=1):
        if isinstance(node, str):
            nodes.append({"id": f"N{index}", "text": node})
        else:
            nodes.append(
                {
                    "id": str(node.get("id") or f"N{index}"),
                    "text": str(node.get("text") or node.get("label") or f"步骤{index}"),
                }
            )
    if not nodes:
        nodes = [{"id": "N1", "text": "待补充流程节点"}]

    edges = []
    for edge in payload.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("from") or edge.get("source") or "")
        target = str(edge.get("to") or edge.get("target") or "")
        if source and target:
            edges.append({"from": source, "to": target})
    if not edges and len(nodes) > 1:
        edges = [{"from": nodes[i]["id"], "to": nodes[i + 1]["id"]} for i in range(len(nodes) - 1)]
    return {"title": title, "nodes": nodes, "edges": edges}


def parse_mermaid_flowchart(mermaid_code):
    lines = [line.strip() for line in (mermaid_code or "").splitlines() if line.strip()]
    title = "流程图"
    node_text = {}
    edges = []
    node_pattern = re.compile(r'([A-Za-z0-9_]+)\s*(?:\[(.*?)\]|\((.*?)\)|\{(.*?)\})?')
    for line in lines:
        if line.startswith(("flowchart", "graph", "%%")):
            continue
        if "-->" not in line:
            continue
        left, right = line.split("-->", 1)
        left_match = node_pattern.search(left.strip())
        right_match = node_pattern.search(right.strip())
        if not left_match or not right_match:
            continue
        left_id = left_match.group(1)
        right_id = right_match.group(1)
        node_text[left_id] = next((value for value in left_match.groups()[1:] if value), left_id)
        node_text[right_id] = next((value for value in right_match.groups()[1:] if value), right_id)
        edges.append({"from": left_id, "to": right_id})
    nodes = [{"id": node_id, "text": text} for node_id, text in node_text.items()]
    return parse_flowchart_payload({"title": title, "nodes": nodes, "edges": edges})


def _wrap_text(text, width=10):
    text = str(text or "")
    if len(text) <= width:
        return [text]
    return [text[i : i + width] for i in range(0, len(text), width)]


def build_flowchart_svg(chart):
    nodes = chart["nodes"]
    node_w = 150
    node_h = 64
    gap = 48
    margin_x = 34
    margin_y = 54
    width = max(360, margin_x * 2 + len(nodes) * node_w + (len(nodes) - 1) * gap)
    height = 190
    y = margin_y + 30
    title = html.escape(chart.get("title") or "流程图")
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" font-family="SimSun, Microsoft YaHei, sans-serif" font-size="18" font-weight="700" fill="#111827">{title}</text>',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#475569"/></marker></defs>',
    ]
    positions = {}
    for index, node in enumerate(nodes):
        x = margin_x + index * (node_w + gap)
        positions[node["id"]] = (x, y)
    for edge in chart.get("edges") or []:
        if edge["from"] not in positions or edge["to"] not in positions:
            continue
        x1, y1 = positions[edge["from"]]
        x2, y2 = positions[edge["to"]]
        parts.append(
            f'<line x1="{x1 + node_w}" y1="{y1 + node_h / 2}" x2="{x2}" y2="{y2 + node_h / 2}" stroke="#475569" stroke-width="2" marker-end="url(#arrow)"/>'
        )
    for node in nodes:
        x, y = positions[node["id"]]
        parts.append(f'<rect x="{x}" y="{y}" width="{node_w}" height="{node_h}" rx="8" fill="#f8fafc" stroke="#2563eb" stroke-width="1.5"/>')
        lines = _wrap_text(node["text"])
        start_y = y + 34 - (len(lines) - 1) * 9
        for line_index, line in enumerate(lines[:3]):
            parts.append(
                f'<text x="{x + node_w / 2}" y="{start_y + line_index * 18}" text-anchor="middle" font-family="SimSun, Microsoft YaHei, sans-serif" font-size="14" fill="#111827">{html.escape(line)}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)
