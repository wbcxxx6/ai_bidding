import re


TOC_LINE_RE = re.compile(r"^\s*(?:[一二三四五六七八九十]+|\d+)?[、．.]?\s*[\u4e00-\u9fa5A-Za-z0-9（）()、/\- ]{2,50}\s+\d{1,4}\s*$")
BODY_MARKERS = [
    "致：",
    "致:",
    "我方",
    "投标总价",
    "人民币",
    "大写",
    "小写",
    "签字",
    "盖章",
    "法定代表人",
    "委托代理人",
    "身份证号码",
    "____",
    "     ",
]


def _non_empty_lines(text):
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def is_toc_like_text(text):
    lines = _non_empty_lines(text)
    if not lines:
        return False
    toc_lines = [line for line in lines if TOC_LINE_RE.match(line)]
    return len(toc_lines) >= 1 and len(toc_lines) / len(lines) >= 0.6


def is_valid_template_text(title, text):
    clean = (text or "").strip()
    if len(clean) < 40:
        return False
    if is_toc_like_text(clean):
        return False
    marker_count = sum(1 for marker in BODY_MARKERS if marker in clean)
    if marker_count >= 1 and len(_non_empty_lines(clean)) >= 3:
        return True
    return False
