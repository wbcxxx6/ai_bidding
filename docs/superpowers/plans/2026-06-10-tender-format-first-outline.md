# Tender Format First Outline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace generic outline generation with a tender-format-first outline engine that locks chapters defined by the tender document and avoids automatic generic fallback chapters.

**Architecture:** Add a pure parser service for tender format sections and a pure outline builder service for schema construction. Keep `/api/bidding/chapter-design` as the compatibility entrypoint, but route it through the new parser/builder before optional model enrichment. Frontend keeps the current Generation page and adds lock/source display behavior.

**Tech Stack:** Python 3 unittest, Flask compatibility route, Vue 3 + Element Plus frontend in `front/`.

---

## File Structure

- Create `services/tender_format_parser.py`: Detect format sections and extract ordered chapter specs with lock metadata and source snippets.
- Create `services/outline_builder.py`: Build final outline JSON from parser output, user-confirmed format requirements, and analysis data.
- Modify `api/bidding.py`: Use new parser/builder in `/chapter-design`; keep model enrichment best-effort and preserve old route path.
- Modify `front/src/user/views/Generation.vue`: Display lock state, chapter type, source heading, source snippet, and manual-review prompts.
- Create `tests/test_tender_format_parser.py`: Unit tests for format section extraction and chapter classification.
- Create `tests/test_outline_builder.py`: Unit tests for format-first outline behavior, no generic fallback, and user override priority.
- Modify `tests/test_outline_fallback.py`: Remove expectations that generic fallback is the default for `/chapter-design`; keep only if `outline_fallback.py` remains for explicit suggestions.

## Task 1: Tender Format Parser

**Files:**
- Create: `services/tender_format_parser.py`
- Test: `tests/test_tender_format_parser.py`

- [ ] **Step 1: Write the failing parser tests**

Create `tests/test_tender_format_parser.py`:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run parser tests to verify they fail**

Run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/ai_bidding_pycache python3 -m unittest tests/test_tender_format_parser.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'services.tender_format_parser'`.

- [ ] **Step 3: Implement minimal parser**

Create `services/tender_format_parser.py`:

```python
import re


FORMAT_HEADING_RE = re.compile(
    r"(?P<heading>(?:第[一二三四五六七八九十\d]+章\s*)?(?:响应文件格式|投标文件格式|响应性文件|附件格式|投标文件组成|响应文件组成))"
)

CHAPTER_HEADING_RE = re.compile(
    r"(?m)^(?P<title>(?P<label>[一二三四五六七八九十]+)[、．.]\s*[^\n\r]{2,60})\s*$"
)

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


def _find_section(text):
    matches = list(FORMAT_HEADING_RE.finditer(text or ""))
    if not matches:
        return None
    match = matches[0]
    start = match.start()
    next_major = re.search(r"(?m)^第[一二三四五六七八九十\d]+章\s+", text[match.end():])
    end = len(text)
    if next_major:
        end = match.end() + next_major.start()
    return {
        "heading": match.group("heading").strip(),
        "startOffset": start,
        "endOffset": end,
        "sourceText": text[start:end].strip()[:8000],
    }


def parse_tender_format(tender_text, analysis_data=None):
    text = tender_text or ""
    section = _find_section(text)
    if not section:
        return _empty_result()

    section_text = section["sourceText"]
    matches = list(CHAPTER_HEADING_RE.finditer(section_text))
    chapters = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(section_text)
        source_text = section_text[match.start():next_start].strip()
        title = match.group("title").strip()
        chapters.append(
            {
                "title": title,
                "rawTitle": title,
                "orderLabel": match.group("label"),
                "type": _classify(title),
                "lockTitle": True,
                "lockOrder": True,
                "sourceText": source_text[:3000],
                "sourceHeading": section["heading"],
                "confidence": 0.92,
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
```

- [ ] **Step 4: Run parser tests to verify they pass**

Run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/ai_bidding_pycache python3 -m unittest tests/test_tender_format_parser.py
```

Expected: PASS.

- [ ] **Step 5: Commit parser work**

Run:

```bash
git add services/tender_format_parser.py tests/test_tender_format_parser.py
git commit -m "feat: parse tender format sections"
```

## Task 2: Outline Builder

**Files:**
- Create: `services/outline_builder.py`
- Test: `tests/test_outline_builder.py`

- [ ] **Step 1: Write the failing builder tests**

Create `tests/test_outline_builder.py`:

```python
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

    def test_user_confirmed_format_requirements_take_priority(self):
        format_requirements = {
            "required_chapters": [
                {"title": "响应性文件目录", "description": "用户确认后的目录", "is_mandatory": True},
                {"title": "技术服务方案", "description": "用户确认后的技术章节", "is_mandatory": True},
            ]
        }

        outline = build_outline(FORMAT_PLAN, format_requirements, {})

        self.assertEqual(outline["source"], "user_confirmed_format")
        self.assertEqual([chapter["title"] for chapter in outline["chapters"]], ["响应性文件目录", "技术服务方案"])
        self.assertTrue(all(chapter["lockTitle"] for chapter in outline["chapters"]))

    def test_manual_review_required_when_no_format_is_detected(self):
        outline = build_outline({"detected": False, "chapters": [], "questions": ["未识别到格式"]}, None, {})

        self.assertEqual(outline["source"], "manual_review_required")
        self.assertTrue(outline["needsReview"])
        self.assertEqual(outline["chapters"], [])
        self.assertTrue(outline["questions"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run builder tests to verify they fail**

Run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/ai_bidding_pycache python3 -m unittest tests/test_outline_builder.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'services.outline_builder'`.

- [ ] **Step 3: Implement minimal builder**

Create `services/outline_builder.py`:

```python
TEMPLATE_KEYWORDS = ["投标函", "授权", "委托书", "报价", "偏离表", "承诺", "声明", "证明", "附件", "格式"]
OUTLINE_KEYWORDS = ["技术", "商务", "资格", "服务", "实施", "响应"]


def _chapter_type(title, explicit=None):
    if explicit:
        return explicit
    if any(keyword in title for keyword in TEMPLATE_KEYWORDS):
        return "locked_template"
    if any(keyword in title for keyword in OUTLINE_KEYWORDS):
        return "locked_outline"
    return "locked_outline"


def _target_words(chapter_type, title):
    if chapter_type == "locked_template":
        return 500
    if "技术" in title or "方案" in title:
        return 3000
    return 1500


def _sections_for_locked_outline(title):
    return [
        {
            "title": "响应要求梳理",
            "subsections": [
                {
                    "title": "招标要求对应关系",
                    "describe": "逐条对应招标文件对本章节的要求，说明响应内容、证明材料、交付成果和需要引用的来源。",
                },
                {
                    "title": "重点评分项响应",
                    "describe": "围绕评分办法中的关键得分点组织内容，明确措施、方法、优势和风险控制，不编造企业事实。",
                },
            ],
        }
    ]


def _build_chapter(chapter):
    title = chapter.get("title") or "未命名章节"
    chapter_type = _chapter_type(title, chapter.get("type"))
    base = {
        "title": title,
        "type": chapter_type,
        "lockTitle": chapter.get("lockTitle", True),
        "lockOrder": chapter.get("lockOrder", True),
        "sourceHeading": chapter.get("sourceHeading"),
        "sourceText": chapter.get("sourceText"),
        "target_words": _target_words(chapter_type, title),
    }
    if chapter_type == "locked_template":
        return {
            **base,
            "content": "本章应按招标文件模板填写，不进行自由扩写；缺失企业事实时标记为待补充。",
            "sections": [],
        }
    return {
        **base,
        "content": "本章标题和顺序按招标文件锁定，内部内容可围绕招标要求、评分项和企业资料展开。",
        "sections": _sections_for_locked_outline(title),
    }


def _from_user_requirements(format_requirements):
    chapters = []
    for item in format_requirements.get("required_chapters") or []:
        title = item.get("title")
        if not title:
            continue
        chapters.append(
            _build_chapter(
                {
                    "title": title,
                    "type": _chapter_type(title),
                    "lockTitle": True,
                    "lockOrder": True,
                    "sourceHeading": "用户确认格式要求",
                    "sourceText": item.get("description") or "",
                }
            )
        )
    return chapters


def build_outline(format_plan, format_requirements=None, analysis_data=None):
    format_requirements = format_requirements or {}
    if format_requirements.get("required_chapters"):
        return {
            "source": "user_confirmed_format",
            "needsReview": False,
            "chapters": _from_user_requirements(format_requirements),
            "questions": [],
        }

    format_plan = format_plan or {}
    if format_plan.get("detected") and format_plan.get("chapters"):
        return {
            "source": "tender_format_first",
            "needsReview": bool(format_plan.get("questions")),
            "chapters": [_build_chapter(chapter) for chapter in format_plan.get("chapters") or []],
            "formatSections": format_plan.get("formatSections") or [],
            "questions": format_plan.get("questions") or [],
        }

    return {
        "source": "manual_review_required",
        "needsReview": True,
        "chapters": [],
        "suggestedChapters": [],
        "questions": (format_plan.get("questions") if isinstance(format_plan, dict) else None)
        or ["未识别到固定投标文件格式，是否基于评分项生成建议目录？"],
    }
```

- [ ] **Step 4: Run builder tests to verify they pass**

Run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/ai_bidding_pycache python3 -m unittest tests/test_outline_builder.py
```

Expected: PASS.

- [ ] **Step 5: Commit builder work**

Run:

```bash
git add services/outline_builder.py tests/test_outline_builder.py
git commit -m "feat: build tender-format-first outlines"
```

## Task 3: Wire `/chapter-design` Through Parser and Builder

**Files:**
- Modify: `api/bidding.py`
- Test: extend `tests/test_outline_builder.py` or add route-level test if Flask test dependencies are available

- [ ] **Step 1: Add a pure helper test for the route composition**

Append to `tests/test_outline_builder.py`:

```python
    def test_model_enrichment_is_not_required_for_locked_template_outline(self):
        outline = build_outline(FORMAT_PLAN, None, {})

        template_chapters = [chapter for chapter in outline["chapters"] if chapter["type"] == "locked_template"]

        self.assertEqual(len(template_chapters), 1)
        self.assertEqual(template_chapters[0]["sections"], [])
        self.assertIn("不进行自由扩写", template_chapters[0]["content"])
```

- [ ] **Step 2: Run tests to verify the new assertion passes before route wiring**

Run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/ai_bidding_pycache python3 -m unittest tests/test_outline_builder.py
```

Expected: PASS. This locks behavior before touching the route.

- [ ] **Step 3: Modify imports in `api/bidding.py`**

Replace:

```python
from services.outline_fallback import build_fallback_outline
```

with:

```python
from services.outline_builder import build_outline
from services.tender_format_parser import parse_tender_format
```

- [ ] **Step 4: Modify `/chapter-design` implementation**

Inside `chapter_design()`, after:

```python
analysis = json.loads(bidding["analysis_data"])
existing_outline = bidding.get("directory_structure") or ""
```

add:

```python
tender_content = ""
try:
    tender_content = read_tender_file(bidding_id) or ""
except Exception as exc:
    logging.warning("read tender text for format parsing failed: %s", str(exc)[:200])

format_plan = parse_tender_format(tender_content, analysis)
format_first_outline = build_outline(format_plan, format_reqs, analysis)

if format_first_outline.get("source") in {"tender_format_first", "user_confirmed_format", "manual_review_required"}:
    _update_project(
        bidding["project_id"],
        directory_structure=_json(format_first_outline),
        project_status="analyzing",
    )
    return jsonify(format_first_outline)
```

Then remove the old exception fallback block that calls `build_fallback_outline`, or replace it with:

```python
    except Exception as exc:
        logging.warning("chapter_design model failed after format parsing: %s", str(exc)[:500])
        fallback_outline = build_outline(format_plan, format_reqs, analysis)
        _update_project(bidding["project_id"], directory_structure=_json(fallback_outline), project_status="analyzing")
        return jsonify(fallback_outline)
```

Do not call `services/outline_fallback.py` from `/chapter-design`.

- [ ] **Step 5: Run backend tests**

Run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/ai_bidding_pycache python3 -m unittest discover tests
PYTHONPYCACHEPREFIX=/private/tmp/ai_bidding_pycache python3 -m py_compile api/bidding.py services/tender_format_parser.py services/outline_builder.py
```

Expected: unittest PASS and py_compile exit 0.

- [ ] **Step 6: Commit route wiring**

Run:

```bash
git add api/bidding.py tests/test_outline_builder.py
git commit -m "feat: use tender format outline route"
```

## Task 4: Frontend Directory Preview Lock Metadata

**Files:**
- Modify: `front/src/user/views/Generation.vue`

- [ ] **Step 1: Inspect current outline preview block**

Run:

```bash
sed -n '120,155p' front/src/user/views/Generation.vue
sed -n '220,245p' front/src/user/views/Generation.vue
```

Expected: find the `<el-tree>` outline preview and `outlineTree` computed property.

- [ ] **Step 2: Update outline tree labels**

In `outlineTree`, replace the current mapping with:

```javascript
const typeLabel = (type) => {
  if (type === 'locked_template') return '模板锁定'
  if (type === 'locked_outline') return '目录锁定'
  if (type === 'free_content') return '自由内容'
  return type || '未分类'
}

const outlineTree = computed(() => {
  if (!outline.value?.chapters) return []
  return outline.value.chapters.map(ch => ({
    label: `${ch.title}（${typeLabel(ch.type)}${ch.lockTitle ? '｜标题锁定' : ''}${ch.sourceHeading ? `｜${ch.sourceHeading}` : ''}）`,
    children: (ch.sections || []).map(sec => ({
      label: sec.title,
      children: (sec.subsections || []).map(sub => ({ label: sub.title }))
    }))
  }))
})
```

- [ ] **Step 3: Add manual review and source display in preview**

Above the `<el-tree>` in the outline preview, add:

```vue
<el-alert
  v-if="outline.needsReview"
  type="warning"
  show-icon
  :closable="false"
  title="未识别到固定投标文件格式，请确认目录后再生成。"
/>
<div v-if="outline.questions?.length" class="outline-questions">
  <el-tag v-for="(question, idx) in outline.questions" :key="idx" type="warning">
    {{ question }}
  </el-tag>
</div>
```

Below the `<el-tree>`, add:

```vue
<div v-if="outline.chapters?.some(ch => ch.sourceText)" class="source-snippets">
  <h4>格式来源</h4>
  <el-collapse>
    <el-collapse-item
      v-for="(ch, idx) in outline.chapters.filter(ch => ch.sourceText)"
      :key="idx"
      :title="`${ch.title} - ${ch.sourceHeading || '招标文件'}`"
    >
      <pre>{{ ch.sourceText }}</pre>
    </el-collapse-item>
  </el-collapse>
</div>
```

- [ ] **Step 4: Add compact styles**

In the `<style>` block, add:

```css
.outline-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0;
}

.source-snippets {
  margin-top: 16px;
}

.source-snippets pre {
  margin: 0;
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.6;
  color: #334155;
}
```

- [ ] **Step 5: Run frontend build if dependencies are present**

Run:

```bash
npm --prefix front run build
```

Expected: build succeeds. If dependencies are missing, run `npm --prefix front install` only after user approval because it may need network.

- [ ] **Step 6: Commit frontend preview**

Run:

```bash
git add front/src/user/views/Generation.vue
git commit -m "feat: show locked tender outline metadata"
```

## Task 5: Remove Default Generic Fallback From Chapter Design Path

**Files:**
- Modify: `tests/test_outline_fallback.py`
- Modify or delete: `services/outline_fallback.py`

- [ ] **Step 1: Decide whether `outline_fallback.py` is still used**

Run:

```bash
rg -n "outline_fallback|build_fallback_outline" .
```

Expected: no production import from `/chapter-design`. If only tests reference it, delete `services/outline_fallback.py` and `tests/test_outline_fallback.py`. If another explicit suggestion flow uses it, rename tests to clarify it is not automatic.

- [ ] **Step 2A: If unused, delete fallback files**

Use `apply_patch` delete hunks:

```text
*** Begin Patch
*** Delete File: services/outline_fallback.py
*** Delete File: tests/test_outline_fallback.py
*** End Patch
```

- [ ] **Step 2B: If kept for explicit suggestions, update tests**

Replace `tests/test_outline_fallback.py` assertions so the test name says:

```python
def test_builds_suggested_outline_only_for_manual_confirmation_flow(self):
```

and make sure no test implies this is default `/chapter-design` behavior.

- [ ] **Step 3: Run full backend tests**

Run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/ai_bidding_pycache python3 -m unittest discover tests
```

Expected: PASS.

- [ ] **Step 4: Commit fallback cleanup**

Run:

```bash
git add services/outline_fallback.py tests/test_outline_fallback.py
git commit -m "refactor: remove generic outline default"
```

## Task 6: Final Verification

**Files:**
- Verify all touched files.

- [ ] **Step 1: Run backend verification**

Run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/ai_bidding_pycache python3 -m unittest discover tests
PYTHONPYCACHEPREFIX=/private/tmp/ai_bidding_pycache python3 -m py_compile api/bidding.py services/tender_format_parser.py services/outline_builder.py services/qwen_client.py
```

Expected: all commands exit 0.

- [ ] **Step 2: Run frontend verification**

Run:

```bash
npm --prefix front run build
```

Expected: build exits 0. If it cannot run because dependencies are absent and network is blocked, document the exact error.

- [ ] **Step 3: Manual smoke payload**

Use the Flask app or a small local script to verify this sample text through parser/builder:

```python
from services.tender_format_parser import parse_tender_format
from services.outline_builder import build_outline

text = '''
第六章 响应文件格式
一、投标函
致：采购人
二、授权委托书
委托代理人：____
三、技术响应文件
逐条响应技术要求。
'''
outline = build_outline(parse_tender_format(text, {}), None, {})
assert outline["source"] == "tender_format_first"
assert [c["title"] for c in outline["chapters"]] == ["一、投标函", "二、授权委托书", "三、技术响应文件"]
assert outline["chapters"][0]["type"] == "locked_template"
assert outline["chapters"][2]["type"] == "locked_outline"
```

Expected: no assertion error.

- [ ] **Step 4: Review diff for unrelated changes**

Run:

```bash
git status --short
git diff --stat
```

Expected: only planned files are changed by this implementation. Existing user changes in `README.md`, `main.py`, `front/`, `web/`, and docs must not be reverted.

## Self-Review

- Spec coverage: Parser covers format detection, source snippets, chapter classification, and manual review. Builder covers lock metadata, no generic fallback, user override, and manual-review output. Route wiring covers compatibility path and model failure behavior. Frontend covers lock/source visibility.
- Placeholder scan: No TBD/TODO placeholders are intentionally left in this plan.
- Type consistency: Parser emits `detected`, `formatSections`, `chapters`, `type`, `lockTitle`, `lockOrder`, `sourceText`, `sourceHeading`; builder and frontend consume the same names.
