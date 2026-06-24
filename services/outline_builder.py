from services.chapter_title import dedupe_by_chapter_title


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


MIN_SUBSECTION_WORDS = 1500


def _target_words(chapter_type, title):
    if chapter_type == "locked_template":
        return 0
    if "技术" in title or "方案" in title:
        return 15000
    return 13500


def _sections_for_locked_outline(title):
    return [
        {
            "title": "响应要求梳理",
            "subsections": [
                {
                    "title": "招标要求对应关系",
                    "describe": "逐条对应招标文件对本章节的要求，说明响应内容、证明材料、交付成果和需要引用的来源。",
                    "min_words": MIN_SUBSECTION_WORDS,
                },
                {
                    "title": "重点评分项响应",
                    "describe": "围绕评分办法中的关键得分点组织内容，明确措施、方法、优势和风险控制，不编造企业事实。",
                    "min_words": MIN_SUBSECTION_WORDS,
                },
                {
                    "title": "实质性条款响应",
                    "describe": "对工期、质量、服务、验收、付款、违约责任等实质性条款逐项说明响应方式和履约控制措施。",
                    "min_words": MIN_SUBSECTION_WORDS,
                },
            ],
        },
        {
            "title": "实施内容与方法",
            "subsections": [
                {
                    "title": "总体实施思路",
                    "describe": "结合招标范围说明本章节对应工作的总体组织方式、阶段划分、关键交付物和协同机制。",
                    "min_words": MIN_SUBSECTION_WORDS,
                },
                {
                    "title": "关键任务执行方案",
                    "describe": "展开说明关键任务的执行步骤、资源安排、质量标准、过程记录和验收依据。",
                    "min_words": MIN_SUBSECTION_WORDS,
                },
                {
                    "title": "风险识别与控制",
                    "describe": "识别履约过程中可能影响进度、质量、安全和合规的风险，提出可执行的预防和处置措施。",
                    "min_words": MIN_SUBSECTION_WORDS,
                },
            ],
        },
        {
            "title": "保障措施与交付承诺",
            "subsections": [
                {
                    "title": "组织与人员保障",
                    "describe": "说明组织职责、沟通汇报、人员投入原则和岗位协作方式，不编造具体人员姓名或证书。",
                    "min_words": MIN_SUBSECTION_WORDS,
                },
                {
                    "title": "质量与进度保障",
                    "describe": "说明质量检查、节点控制、问题闭环、成果复核和进度纠偏机制。",
                    "min_words": MIN_SUBSECTION_WORDS,
                },
                {
                    "title": "资料归档与后续服务",
                    "describe": "说明交付资料、归档方式、培训支持、售后响应和持续改进安排。",
                    "min_words": MIN_SUBSECTION_WORDS,
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
        "templateStatus": chapter.get("templateStatus"),
        "target_words": _target_words(chapter_type, title),
    }
    if chapter_type == "locked_template":
        return {
            **base,
            "content": "本章已由招标文件规定格式和正文，生成时必须原文复制，不进行自由扩写或自动改写。",
            "sections": [],
        }
    return {
        **base,
        "content": "本章标题和顺序按招标文件锁定，内部内容可围绕招标要求、评分项和企业资料展开。",
        "min_heading_level": 3,
        "min_subsection_words": MIN_SUBSECTION_WORDS,
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
    return dedupe_by_chapter_title(chapters, get_title=lambda chapter: chapter.get("title"), score_item=_chapter_score)


def _chapter_score(chapter):
    score = len(chapter.get("sourceText") or "")
    if chapter.get("templateStatus") == "valid":
        score += 100000
    if chapter.get("sourceText"):
        score += 1000
    if chapter.get("sections"):
        score += len(chapter.get("sections") or [])
    return score


def build_outline(format_plan, format_requirements=None, analysis_data=None):
    format_requirements = format_requirements or {}
    format_plan = format_plan or {}
    if format_plan.get("detected") and format_plan.get("chapters"):
        chapters = dedupe_by_chapter_title(
            [_build_chapter(chapter) for chapter in format_plan.get("chapters") or []],
            get_title=lambda chapter: chapter.get("title"),
            score_item=_chapter_score,
        )
        questions = list(format_plan.get("questions") or [])
        for chapter in chapters:
            if chapter.get("type") == "locked_template" and chapter.get("templateStatus") in {"toc_only", "missing"}:
                questions.append(
                    f"{chapter.get('title')} 只识别到目录项或缺少正文模板，请补充招标文件原始模板后再生成。"
                )
        return {
            "source": "tender_format_first",
            "needsReview": bool(questions),
            "chapters": chapters,
            "formatSections": format_plan.get("formatSections") or [],
            "questions": questions,
        }

    if format_requirements.get("required_chapters"):
        return {
            "source": "user_confirmed_format",
            "needsReview": False,
            "chapters": _from_user_requirements(format_requirements),
            "questions": [],
        }

    return {
        "source": "manual_review_required",
        "needsReview": True,
        "chapters": [],
        "suggestedChapters": [],
        "questions": (format_plan.get("questions") if isinstance(format_plan, dict) else None)
        or ["未识别到固定投标文件格式，是否基于评分项生成建议目录？"],
    }
