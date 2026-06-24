import re


LEADING_NUMBER_RE = re.compile(
    r"^\s*(?:"
    r"第[一二三四五六七八九十百千万\d]+[章节篇部分]\s*"
    r"|[（(]?\d+[）)]?[、．.\-]\s*"
    r"|[一二三四五六七八九十百千万]+[、．.]\s*"
    r")"
)
NOISE_RE = re.compile(r"[\s:：、，,．.。;；\-_/\\（）()【】\[\]<>《》]+")


def strip_leading_chapter_number(title):
    text = str(title or "").strip()
    while text:
        cleaned = LEADING_NUMBER_RE.sub("", text, count=1).strip()
        if cleaned == text:
            break
        text = cleaned
    return text


def normalise_chapter_title(title):
    stripped = strip_leading_chapter_number(title)
    return NOISE_RE.sub("", stripped).lower()


def dedupe_by_chapter_title(items, *, get_title, score_item=None):
    result = []
    positions = {}
    score_item = score_item or (lambda item: 0)

    for item in items or []:
        key = normalise_chapter_title(get_title(item))
        if not key:
            result.append(item)
            continue
        if key not in positions:
            positions[key] = len(result)
            result.append(item)
            continue

        index = positions[key]
        if score_item(item) > score_item(result[index]):
            result[index] = item
    return result
