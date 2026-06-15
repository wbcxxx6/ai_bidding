import re

from services.template_validation import is_toc_like_text, is_valid_template_text


FORMAT_HEADING_RE = re.compile(
    r"(?P<heading>(?:第[一二三四五六七八九十\d]+章\s*)?(?:响应文件格式|投标文件格式|响应性文件|附件格式|投标文件组成|响应文件组成))"
)

CHAPTER_HEADING_RE = re.compile(
    r"(?m)^(?P<title>(?:(?P<label_cn>[一二三四五六七八九十]+)[、．.]\s*|(?P<label_digit>\d+)[、．.]\s+)[^\n\r]{2,60})\s*$"
)
TOC_CHAPTER_RE = re.compile(r"(?m)^(?P<title>[\u4e00-\u9fa5A-Za-z0-9（）()、/\- ]{2,50})\s+\d{1,4}\s*$")

TEMPLATE_KEYWORDS = [
    "投标函",
    "报价表",
    "报价",
    "法定代表人",
    "授权",
    "委托书",
    "承诺",
    "声明",
    "偏离表",
    "证明",
    "附件",
    "格式",
]

OUTLINE_KEYWORDS = ["技术响应", "商务响应", "资格", "实施方案", "服务方案", "技术方案"]
TOC_LINE_RE = re.compile(r"^\s*(?:[一二三四五六七八九十]+|\d+)[、．.]\s*[^\n\r]{2,60}\s+\d+\s*$")
TEMPLATE_BODY_KEYWORDS = ["致：", "致:", "我方", "投标总价", "人民币", "____", "（大写）", "签字", "盖章"]
MAX_TEMPLATE_SOURCE_TEXT = 20000
MAX_OUTLINE_SOURCE_TEXT = 6000
MAX_SECTION_SOURCE_TEXT = 30000


def _empty_result():
    return {
        "detected": False,
        "source": "none",
        "confidence": 0,
        "formatSections": [],
        "chapters": [],
        "formatNotes": [],
        "questions": ["未在招标文件中识别到明确的投标文件格式，请确认是否需要手动创建目录。"],
    }


def _classify(title):
    if any(keyword in title for keyword in OUTLINE_KEYWORDS):
        return "locked_outline"
    if any(keyword in title for keyword in TEMPLATE_KEYWORDS):
        return "locked_template"
    return "locked_outline"


def _chapter_matches(section_text):
    matches = list(CHAPTER_HEADING_RE.finditer(section_text))
    if matches:
        return matches
    if is_toc_like_text(section_text):
        return list(TOC_CHAPTER_RE.finditer(section_text))
    return []


def _section_score(section):
    text = section["sourceText"]
    matches = _chapter_matches(text)
    score = len(matches) * 5
    score += sum(8 for keyword in TEMPLATE_BODY_KEYWORDS if keyword in text)
    score -= sum(4 for line in text.splitlines() if TOC_LINE_RE.match(line))
    if len(text) > 500:
        score += 10
    return score


def _find_section(text):
    matches = list(FORMAT_HEADING_RE.finditer(text or ""))
    if not matches:
        return None
    sections = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        next_major = re.search(r"(?m)^第[一二三四五六七八九十\d]+章\s+", text[match.end():end])
        if next_major:
            end = match.end() + next_major.start()
        section = {
            "heading": match.group("heading").strip(),
            "startOffset": start,
            "endOffset": end,
            "sourceText": text[start:end].strip()[:MAX_SECTION_SOURCE_TEXT],
        }
        section["score"] = _section_score(section)
        sections.append(section)
    return max(sections, key=lambda item: item["score"])


def parse_tender_format(tender_text, analysis_data=None):
    text = tender_text or ""
    section = _find_section(text)
    if not section:
        return _empty_result()

    section_text = section["sourceText"]
    matches = _chapter_matches(section_text)
    chapters = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(section_text)
        source_text = section_text[match.start():next_start].strip()
        title = match.group("title").strip()
        chapter_type = _classify(title)
        template_status = None
        if chapter_type == "locked_template":
            if is_valid_template_text(title, source_text):
                template_status = "valid"
            elif is_toc_like_text(source_text):
                template_status = "toc_only"
            else:
                template_status = "missing"
        chapters.append(
            {
                "title": title,
                "rawTitle": title,
                "orderLabel": match.groupdict().get("label_cn") or match.groupdict().get("label_digit"),
                "type": chapter_type,
                "lockTitle": True,
                "lockOrder": True,
                "sourceText": source_text[: MAX_TEMPLATE_SOURCE_TEXT if chapter_type == "locked_template" else MAX_OUTLINE_SOURCE_TEXT],
                "sourcePreview": source_text[:800],
                "sourceHeading": section["heading"],
                "confidence": 0.92,
                **({"templateStatus": template_status} if template_status else {}),
            }
        )

    if not chapters:
        result = _empty_result()
        result["formatSections"] = [section]
        result["questions"] = ["识别到格式章节，但未能拆分出明确目录，请人工确认章节。"]
        return result

    return {
        "detected": True,
        "source": "tender_text",
        "confidence": 0.86,
        "formatSections": [section],
        "chapters": chapters,
        "formatNotes": [],
        "questions": [],
    }
