import json
import logging
import re
from datetime import datetime

from core.db import get_db
from services.deep_research_service import create_and_run_research_task, parse_json
from services.retrieval_router import retrieval_router


LOGGER = logging.getLogger(__name__)


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def json_dumps(value):
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def word_count(text):
    if not text:
        return 0
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    latin_words = re.findall(r"[A-Za-z0-9_]+", text)
    return len(chinese_chars) + len(latin_words)


class AgentRunLogger:
    def start(self, *, generation_task_id=None, project_id=None, agent_name, input_value=None):
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO agent_runs
                (tenant_id, generation_task_id, project_id, agent_name, status, input_json,
                 started_at, created_at, updated_at)
                VALUES (1, ?, ?, ?, 'running', ?, ?, ?, ?)
                """,
                (generation_task_id, project_id, agent_name, json_dumps(input_value), now(), now(), now()),
            )
            run_id = cursor.lastrowid
            conn.commit()
            return run_id
        finally:
            conn.close()

    def finish(self, run_id, *, output_value=None, status="succeeded", error_message=None):
        conn = get_db()
        try:
            conn.execute(
                """
                UPDATE agent_runs
                SET status=?, output_json=?, error_message=?, finished_at=?, updated_at=?
                WHERE id=?
                """,
                (status, json_dumps(output_value), error_message, now(), now(), run_id),
            )
            conn.commit()
        finally:
            conn.close()


agent_runs = AgentRunLogger()


def load_project_context(project_id):
    conn = get_db()
    try:
        project = conn.execute("SELECT * FROM bid_projects WHERE id=?", (project_id,)).fetchone()
        facts = conn.execute(
            """
            SELECT fact_key, fact_value, confidence, status AS confirm_status
            FROM project_facts
            WHERE project_id=?
            ORDER BY id
            """,
            (project_id,),
        ).fetchall()
        chapters = conn.execute(
            """
            SELECT chapter_title, chapter_type, sort_order, outline_json
            FROM bid_chapters
            WHERE project_id=?
            ORDER BY sort_order
            """,
            (project_id,),
        ).fetchall()
        return {"project": project, "facts": facts, "chapters": chapters}
    finally:
        conn.close()


def context_text(project_id):
    context = load_project_context(project_id)
    project = context.get("project") or {}
    confirmed_facts = [
        f"- {item['fact_key']}: {item['fact_value']}"
        for item in context["facts"]
        if item.get("confirm_status") in ("confirmed", "auto")
    ]
    outline = [f"- {item['chapter_title']}" for item in context["chapters"]]
    return "\n".join(
        [
            f"Project: {project.get('project_name') or ''}",
            "Confirmed project facts:",
            "\n".join(confirmed_facts) or "- none",
            "Full outline:",
            "\n".join(outline) or "- none",
        ]
    )


def _research_sources_for_generation(project_id, query_text, generation_task_id=None):
    try:
        bundle = create_and_run_research_task(
            project_id,
            {
                "query": query_text,
                "chapterQuery": query_text,
                "maxSources": 6,
                "trigger": "generation_auto_research",
                "generation_task_id": generation_task_id,
            },
        )
    except Exception as exc:
        return {"sources": [], "degraded_reason": f"auto_research_failed: {str(exc)[:240]}"}
    selected = []
    for source in bundle.get("sources") or []:
        meta = parse_json(source.get("reference_value"), {})
        if meta.get("selected_for_generation"):
            selected.append(
                {
                    "doc_type": source.get("source_type") or "research",
                    "file_id": source.get("file_id"),
                    "chunk_id": None,
                    "chunk_uid": f"research_source_{source['id']}",
                    "source_title": source.get("title"),
                    "content": source.get("summary") or source.get("content_snapshot") or "",
                    "similarity": meta.get("reflection_score") or source.get("credibility_score") or 0.5,
                    "reuse_policy": "reference",
                    "source_url": source.get("source_url"),
                    "retrieved_at": source.get("retrieved_at"),
                    "reflection_reason": meta.get("reflection_reason"),
                    "search_query": meta.get("search_query"),
                    "research_source_id": source.get("id"),
                }
            )
    return {"sources": selected, "research_task": (bundle.get("task") or {}).get("id")}


def run_tender_parser_agent(*, project_id, file_id, tender_content, generation_task_id=None):
    run_id = agent_runs.start(
        generation_task_id=generation_task_id,
        project_id=project_id,
        agent_name="TenderParserAgent",
        input_value={"file_id": file_id, "content_length": len(tender_content or "")},
    )
    try:
        from services.model_router import model_router

        text = tender_content or ""
        head_part = text[:6000]
        format_part = ""
        format_keywords = ["封面", "投标文件格式", "投标文件组成", "格式要求", "文件编制", "投标书格式"]
        for kw in format_keywords:
            pos = text.find(kw)
            if pos > 0:
                format_part = text[max(0, pos - 200):pos + 4000]
                break
        if not format_part and len(text) > 6000:
            format_part = text[-5000:]

        combined_content = head_part + "\n\n---以下为投标文件格式相关内容---\n\n" + format_part if format_part else head_part
        prompt = (
            "你是资深招标文件分析专家。请从以下招标文件内容中提取结构化信息。\n"
            "重点提取招标文件中对投标文件的格式要求、章节组成要求、文件编排要求。\n\n"
            "输出JSON格式：\n"
            "{\n"
            '  "project_name": "项目名称",\n'
            '  "purchaser_name": "采购人/招标人",\n'
            '  "agency_name": "招标代理机构",\n'
            '  "procurement_method": "采购方式",\n'
            '  "budget_amount": "预算金额",\n'
            '  "bid_deadline": "投标截止时间",\n'
            '  "service_period": "服务期限",\n'
            '  "service_location": "服务地点",\n'
            '  "qualification_requirements": ["资格要求列表"],\n'
            '  "scoring_method": "评分方法概述",\n'
            '  "invalid_bid_conditions": ["废标条款列表"],\n'
            '  "key_requirements": ["核心需求列表"],\n'
            '  "bid_document_format": {\n'
            '    "has_format_requirements": true,\n'
            '    "required_chapters": [\n'
            '      {"title": "招标文件要求的章节标题", "description": "该章节的具体要求说明", "is_mandatory": true}\n'
            '    ],\n'
            '    "format_notes": ["格式注意事项，如装订要求、页码要求、签章要求等"],\n'
            '    "document_composition": "投标文件组成说明（如技术标、商务标、资格标的划分）",\n'
            '    "cover_page": {\n'
            '      "has_cover_requirement": true,\n'
            '      "cover_lines": [\n'
            '        {"text": "封面第一行文字（如项目名称）", "style": "title|subtitle|normal", "placeholder": "project_name|bidder_name|tender_no|bid_date|none"},\n'
            '        {"text": "封面第二行文字", "style": "title|subtitle|normal", "placeholder": "..."}\n'
            '      ],\n'
            '      "cover_notes": "封面其他要求说明（如需要密封、加盖公章等）"\n'
            '    }\n'
            '  }\n'
            "}\n\n"
            "注意：\n"
            "1. required_chapters 必须提取招标文件中明确规定的投标文件章节组成\n"
            "2. 如果招标文件规定了投标文件必须包含哪些部分/章节/材料，全部列出\n"
            "3. is_mandatory=true 表示必须包含，false 表示建议包含\n"
            "4. 封面提取规则：招标文件中通常会有'投标文件格式'或'附件格式'章节，其中会规定投标文件封面的格式。"
            "封面通常包含：项目名称、招标编号、'投标文件'字样、投标人名称、投标日期等。"
            "请逐行提取封面要求的每一行文字。如果某行是需要投标人填写的内容，用对应的 placeholder 标记：\n"
            "  - project_name: 项目名称\n"
            "  - bidder_name: 投标人名称/公司名称\n"
            "  - tender_no: 招标编号/项目编号\n"
            "  - bid_date: 投标日期\n"
            "  - purchaser_name: 采购人/招标人名称\n"
            "  - none: 固定文字不需要替换\n"
            "5. 如果招标文件中有封面示例或格式模板，has_cover_requirement 必须设为 true\n"
            "6. style 规则：项目名称和'投标文件'等大字用 title，副标题用 subtitle，其他信息用 normal\n\n"
            f"招标文件内容：\n{combined_content[:12000]}"
        )
        response = model_router.chat(
            [{"role": "user", "content": prompt}],
            task_type="pre_analysis",
            response_format={"type": "json_object"},
            generation_task_id=generation_task_id,
            project_id=project_id,
            timeout=120,
        )
        content = response["output"]["choices"][0]["message"]["content"]
        result = json.loads(content)
        agent_runs.finish(run_id, output_value=result)
        return result
    except Exception as exc:
        agent_runs.finish(run_id, status="failed", error_message=str(exc)[:1000])
        raise


def extract_template_contents(*, tender_content, required_chapters, project_id=None, generation_task_id=None):
    """从招标文件中抽取格式性章节的完整模板文本"""
    if not tender_content or not required_chapters:
        return {}

    template_keywords = ["函", "表", "书", "证明", "声明", "承诺", "格式", "附件"]
    template_chapters = [
        ch for ch in required_chapters
        if any(kw in ch.get("title", "") for kw in template_keywords)
    ]
    if not template_chapters:
        return {}

    heading_pattern = re.compile(
        r'^(?:'
        r'[一二三四五六七八九十]+[、．.]'
        r'|第[一二三四五六七八九十\d]+[章节条款部分]'
        r'|\d+[\.\、]\d*\s*'
        r'|[（(]\s*[一二三四五六七八九十\d]+\s*[)）]'
        r'|附件\s*[\d一二三四五六七八九十]'
        r')',
        re.MULTILINE,
    )

    results = {}
    for ch in template_chapters:
        title = ch.get("title", "")
        if not title:
            continue

        search_titles = [title]
        core = re.sub(r'[及与和/／].*$', '', title).strip()
        if core != title:
            search_titles.append(core)

        pos = -1
        for st in search_titles:
            pos = tender_content.find(st)
            if pos >= 0:
                break
        if pos < 0:
            continue

        start = pos
        after_title = pos + len(title)
        remaining = tender_content[after_title:after_title + 5000]

        headings = list(heading_pattern.finditer(remaining))
        end_offset = len(remaining)
        for m in headings:
            if m.start() > 50:
                end_offset = m.start()
                break

        raw_text = tender_content[start:after_title + end_offset].strip()

        if len(raw_text) < 30:
            continue
        if len(raw_text) > 5000:
            raw_text = raw_text[:5000]

        placeholders = []
        for ph in re.findall(r'[\[【]([^】\]]+)[】\]]', raw_text):
            if ph not in placeholders:
                placeholders.append(ph)
        for ph in re.findall(r'（([^）]{2,10})）', raw_text):
            if any(kw in ph for kw in ["填写", "名称", "盖章", "签字", "日期"]):
                if ph not in placeholders:
                    placeholders.append(ph)

        results[title] = {
            "template_text": raw_text,
            "placeholders": placeholders,
        }

    if not results and template_chapters:
        try:
            from services.model_router import model_router

            titles_to_extract = [ch["title"] for ch in template_chapters[:5]]
            format_keywords = ["投标文件格式", "格式要求", "文件编制", "投标书格式", "附件格式"]
            format_section = ""
            for kw in format_keywords:
                pos = tender_content.find(kw)
                if pos >= 0:
                    format_section = tender_content[max(0, pos - 100):pos + 10000]
                    break
            if not format_section:
                format_section = tender_content[-10000:]

            prompt = (
                "你是招标文件分析专家。请从以下招标文件内容中，原样提取以下格式性章节的完整模板文本。\n"
                "要求：\n"
                "1. 保留模板的原始格式、换行、标点\n"
                "2. 保留所有占位符（如[XXX]、____等）\n"
                "3. 不要修改、补充或省略任何内容\n"
                "4. 如果找不到某个章节的模板，该章节返回空字符串\n\n"
                f"需要提取的章节：{json.dumps(titles_to_extract, ensure_ascii=False)}\n\n"
                "输出JSON格式：\n"
                '{"templates": [{"title": "章节标题", "template_text": "完整模板文本", "placeholders": ["占位符1"]}]}\n\n'
                f"招标文件内容：\n{format_section[:10000]}"
            )
            response = model_router.chat(
                [{"role": "user", "content": prompt}],
                task_type="pre_analysis",
                response_format={"type": "json_object"},
                generation_task_id=generation_task_id,
                project_id=project_id,
                timeout=120,
            )
            content = response["output"]["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            for item in parsed.get("templates", []):
                text = item.get("template_text", "")
                if text and len(text) > 30:
                    results[item["title"]] = {
                        "template_text": text,
                        "placeholders": item.get("placeholders", []),
                    }
        except Exception as exc:
            LOGGER.warning("LLM template extraction failed: %s", str(exc)[:200])

    return results


def run_fact_keeper_agent(*, project_id, analysis_data, generation_task_id=None):
    run_id = agent_runs.start(
        generation_task_id=generation_task_id,
        project_id=project_id,
        agent_name="FactKeeperAgent",
        input_value={"project_id": project_id},
    )
    try:
        if isinstance(analysis_data, str):
            analysis_data = json.loads(analysis_data)

        fact_mappings = {
            "project_name": ("项目名称", "text"),
            "purchaser_name": ("采购人", "organization"),
            "agency_name": ("招标代理机构", "organization"),
            "procurement_method": ("采购方式", "text"),
            "budget_amount": ("预算金额", "amount"),
            "bid_deadline": ("投标截止时间", "date"),
            "service_period": ("服务期限", "text"),
            "service_location": ("服务地点", "text"),
            "scoring_method": ("评分方法", "text"),
        }

        conn = get_db()
        try:
            cursor = conn.cursor()
            facts_created = 0
            for fact_key, (fact_label, value_type) in fact_mappings.items():
                value = analysis_data.get(fact_key)
                if not value or (isinstance(value, str) and not value.strip()):
                    continue
                fact_value = str(value).strip()
                cursor.execute(
                    """
                    INSERT INTO project_facts
                    (tenant_id, project_id, fact_key, fact_label, fact_value, value_type,
                     source_type, confidence, status, created_at, updated_at)
                    VALUES (1, ?, ?, ?, ?, ?, 'tender', 0.85, 'extracted', ?, ?)
                    ON DUPLICATE KEY UPDATE
                    fact_value = IF(status != 'confirmed', VALUES(fact_value), fact_value),
                    updated_at = VALUES(updated_at)
                    """,
                    (project_id, fact_key, fact_label, fact_value, value_type, now(), now()),
                )
                facts_created += 1
            conn.commit()
        finally:
            conn.close()

        output = {"facts_created": facts_created, "source": "tender_analysis"}
        agent_runs.finish(run_id, output_value=output)
        return output
    except Exception as exc:
        agent_runs.finish(run_id, status="failed", error_message=str(exc)[:1000])
        raise


def run_outline_planner_agent(*, project_id, analysis_data, generation_task_id=None):
    run_id = agent_runs.start(
        generation_task_id=generation_task_id,
        project_id=project_id,
        agent_name="OutlinePlannerAgent",
        input_value={"project_id": project_id},
    )
    try:
        from services.model_router import model_router
        if isinstance(analysis_data, str):
            analysis_data = json.loads(analysis_data)

        facts_text = context_text(project_id)
        prompt = (
            "你是投标文件目录规划专家。根据以下招标分析结果和项目事实，设计投标文件目录结构。\n\n"
            f"项目事实：\n{facts_text}\n\n"
            f"招标要求：{json.dumps(analysis_data, ensure_ascii=False)[:4000]}\n\n"
            "输出JSON格式：\n"
            '{"chapters": [{"title": "章节标题", "type": "normal|table|form", '
            '"content": "章节说明", "target_words": 1500, '
            '"sections": [{"title": "节标题", "subsections": [{"title": "", "describe": ""}]}]}]}'
        )
        response = model_router.chat(
            [{"role": "user", "content": prompt}],
            task_type="chapter_design",
            response_format={"type": "json_object"},
            generation_task_id=generation_task_id,
            project_id=project_id,
            timeout=120,
        )
        content = response["output"]["choices"][0]["message"]["content"]
        result = json.loads(content)
        agent_runs.finish(run_id, output_value={"chapter_count": len(result.get("chapters", []))})
        return result
    except Exception as exc:
        agent_runs.finish(run_id, status="failed", error_message=str(exc)[:1000])
        raise


def create_evidence_pack(*, project_id, query_text, bid_chapter_id=None, generation_task_id=None, include_research=True):
    run_id = agent_runs.start(
        generation_task_id=generation_task_id,
        project_id=project_id,
        agent_name="RetrievalAgent",
        input_value={"query": query_text, "bid_chapter_id": bid_chapter_id},
    )
    pack = retrieval_router.build_context(query_text, project_id=project_id, limit=8)
    research_pack = {"sources": []}
    if include_research:
        research_pack = _research_sources_for_generation(project_id, query_text, generation_task_id)
        pack["results"].extend(research_pack["sources"])
        if research_pack.get("degraded_reason"):
            pack["degraded"] = True
            pack["degraded_reason"] = "; ".join(
                item for item in [pack.get("degraded_reason"), research_pack.get("degraded_reason")] if item
            )
        external_context = "\n\n".join(
            f"[WEB] {item.get('source_title')} ({item.get('source_url')}):\n{item.get('content')}"
            for item in research_pack["sources"]
        )
        if external_context:
            pack["context_text"] = "\n\n".join(item for item in [pack.get("context_text"), external_context] if item)
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO rag_evidence_packs
            (tenant_id, project_id, bid_chapter_id, query_text, context_summary,
             degraded, degraded_reason, created_by_agent_run_id, created_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                bid_chapter_id,
                query_text,
                pack.get("context_text", "")[:2000],
                1 if pack.get("degraded") else 0,
                pack.get("degraded_reason"),
                run_id,
                now(),
            ),
        )
        evidence_pack_id = cursor.lastrowid
        for item in pack.get("results", []):
            cursor.execute(
                """
                INSERT INTO rag_evidence_items
                (tenant_id, evidence_pack_id, source_type, source_file_id, chunk_id, chunk_uid,
                 source_title, evidence_text, similarity, usage_policy, metadata_json, created_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_pack_id,
                    item.get("doc_type") or "unknown",
                    item.get("file_id"),
                    item.get("chunk_id"),
                    item.get("chunk_uid"),
                    item.get("source_title"),
                    item.get("content") or "",
                    item.get("similarity"),
                    item.get("reuse_policy") or "reference",
                    json_dumps(item),
                    now(),
                ),
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        agent_runs.finish(run_id, status="failed", error_message=str(exc)[:1000])
        raise
    finally:
        conn.close()
    agent_runs.finish(
        run_id,
        output_value={
            "evidence_pack_id": evidence_pack_id,
            "degraded": pack.get("degraded"),
            "auto_research_task_id": research_pack.get("research_task"),
            "web_source_count": len(research_pack.get("sources") or []),
        },
    )
    pack["evidence_pack_id"] = evidence_pack_id
    pack["retrieval_agent_run_id"] = run_id
    return pack


def create_chapter_version(*, chapter_id, content, evidence_pack_id=None, generation_task_id=None, agent_run_id=None, change_source="system_generated"):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(MAX(version_no), 0) AS max_version FROM bid_chapter_versions WHERE chapter_id=?", (chapter_id,))
        latest = cursor.fetchone()
        version_no = int(latest["max_version"]) + 1
        cursor.execute(
            """
            INSERT INTO bid_chapter_versions
            (tenant_id, chapter_id, version_no, content, evidence_pack_id, generation_task_id,
             agent_run_id, word_count, review_status, change_source, created_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                chapter_id,
                version_no,
                content,
                evidence_pack_id,
                generation_task_id,
                agent_run_id,
                word_count(content),
                change_source,
                now(),
            ),
        )
        version_id = cursor.lastrowid
        cursor.execute(
            "UPDATE bid_chapters SET current_version_id=?, status='generated', updated_at=? WHERE id=?",
            (version_id, now(), chapter_id),
        )
        conn.commit()
        return {"version_id": version_id, "version_no": version_no, "word_count": word_count(content)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def check_chapter_consistency(*, project_id, bid_document_id=None, bid_chapter_id=None, content="", generation_task_id=None):
    run_id = agent_runs.start(
        generation_task_id=generation_task_id,
        project_id=project_id,
        agent_name="ConsistencyCheckerAgent",
        input_value={"bid_chapter_id": bid_chapter_id},
    )
    issues = []
    context = load_project_context(project_id)
    facts = context["facts"]

    for fact in facts:
        if fact.get("confirm_status") not in ("confirmed", "auto"):
            continue
        value = str(fact.get("fact_value") or "").strip()
        if not value or len(value) < 2:
            continue
        fact_key = fact["fact_key"]
        if fact_key in {"project_name", "company_name", "bidder_name", "purchaser_name", "agency_name"}:
            if len(value) >= 4 and value not in content:
                issues.append({
                    "issue_type": "entity_mismatch",
                    "severity": "warning",
                    "issue_text": f"已确认事实 '{fact_key}' ({value}) 未在生成章节中出现。",
                    "evidence": {"fact_key": fact_key, "fact_value": value},
                })
        elif fact_key in {"service_period", "bid_deadline", "service_location"}:
            if len(value) >= 4 and value not in content:
                issues.append({
                    "issue_type": "date_conflict",
                    "severity": "info",
                    "issue_text": f"时间/地点事实 '{fact_key}' ({value}) 未在章节中体现。",
                    "evidence": {"fact_key": fact_key, "fact_value": value},
                })
        elif fact_key in {"budget_amount"}:
            digits = re.findall(r"[\d,.]+", value)
            for digit in digits:
                if len(digit) >= 3 and digit not in content:
                    issues.append({
                        "issue_type": "number_conflict",
                        "severity": "info",
                        "issue_text": f"数值事实 '{fact_key}' 中的 '{digit}' 未在章节中出现。",
                        "evidence": {"fact_key": fact_key, "fact_value": value, "missing_number": digit},
                    })

    conn = get_db()
    try:
        terms = conn.execute(
            "SELECT term, aliases_json, forbidden_aliases_json FROM project_terms WHERE project_id=?",
            (project_id,),
        ).fetchall()
    finally:
        conn.close()

    for term_row in terms:
        forbidden = parse_json(term_row.get("forbidden_aliases_json"), [])
        for forbidden_alias in (forbidden or []):
            if isinstance(forbidden_alias, str) and forbidden_alias in content:
                issues.append({
                    "issue_type": "terminology_violation",
                    "severity": "warning",
                    "issue_text": f"章节中使用了禁用术语 '{forbidden_alias}'，应使用标准术语 '{term_row['term']}'。",
                    "evidence": {"standard_term": term_row["term"], "forbidden_alias": forbidden_alias},
                })

    if word_count(content) < 120:
        issues.append({
            "issue_type": "word_count_low",
            "severity": "warning",
            "issue_text": "生成章节内容过短，可能不满足企业投标文件的内容密度要求。",
            "evidence": {"word_count": word_count(content)},
        })

    try:
        from services.model_router import model_router
        facts_summary = "\n".join(
            f"- {item['fact_key']}: {item['fact_value']}"
            for item in facts
            if item.get("confirm_status") in ("confirmed", "auto") and item.get("fact_value")
        )
        if facts_summary and len(content) > 200:
            prompt = (
                "你是招投标文件一致性审核专家。请检查以下生成章节内容与项目事实是否一致。\n\n"
                f"项目事实：\n{facts_summary[:2000]}\n\n"
                f"章节内容（截取）：\n{content[:3000]}\n\n"
                "请检查：\n"
                "1. 是否存在与项目事实矛盾的表述\n"
                "2. 是否存在可能编造的企业资质、案例、人员信息\n"
                "3. 是否存在前后逻辑不一致\n\n"
                "输出JSON: {\"issues\": [{\"type\": \"...\", \"severity\": \"warning|error\", \"description\": \"...\"}]}\n"
                "如果没有问题，输出: {\"issues\": []}"
            )
            response = model_router.chat(
                [{"role": "user", "content": prompt}],
                task_type="review",
                response_format={"type": "json_object"},
                generation_task_id=generation_task_id,
                project_id=project_id,
                timeout=30,
            )
            llm_output = response["output"]["choices"][0]["message"]["content"]
            try:
                llm_issues = json.loads(llm_output)
                for item in (llm_issues.get("issues") or [])[:5]:
                    issues.append({
                        "issue_type": item.get("type") or "llm_detected",
                        "severity": item.get("severity") or "warning",
                        "issue_text": item.get("description") or str(item),
                        "evidence": {"source": "llm_consistency_check"},
                    })
            except (json.JSONDecodeError, TypeError):
                pass
    except Exception as exc:
        LOGGER.warning("LLM consistency check degraded: %s", str(exc)[:200])

    conn = get_db()
    try:
        cursor = conn.cursor()
        for issue in issues:
            cursor.execute(
                """
                INSERT INTO consistency_issues
                (tenant_id, project_id, bid_document_id, bid_chapter_id, issue_type, severity,
                 issue_text, evidence_json, status, created_by_agent_run_id, created_at, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (
                    project_id,
                    bid_document_id,
                    bid_chapter_id,
                    issue["issue_type"],
                    issue["severity"],
                    issue["issue_text"],
                    json_dumps(issue.get("evidence")),
                    run_id,
                    now(),
                    now(),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    agent_runs.finish(run_id, output_value={"issue_count": len(issues), "issues": issues})
    return {"agent_run_id": run_id, "issues": issues}


def create_compliance_report(*, project_id, bid_document_id=None):
    run_id = agent_runs.start(
        project_id=project_id,
        agent_name="ComplianceReviewerAgent",
        input_value={"project_id": project_id, "bid_document_id": bid_document_id},
    )
    conn = get_db()
    try:
        issues = conn.execute(
            """
            SELECT issue_type, severity, issue_text
            FROM consistency_issues
            WHERE project_id=? AND (bid_document_id=? OR ? IS NULL) AND status='open'
            ORDER BY id DESC
            """,
            (project_id, bid_document_id, bid_document_id),
        ).fetchall()
        response_items = conn.execute(
            """
            SELECT response_status, COUNT(*) AS total
            FROM response_matrix_items
            WHERE project_id=? AND (bid_document_id=? OR ? IS NULL)
            GROUP BY response_status
            """,
            (project_id, bid_document_id, bid_document_id),
        ).fetchall()
        chapters = conn.execute(
            """
            SELECT c.chapter_title, v.content, v.word_count
            FROM bid_chapters c
            LEFT JOIN bid_chapter_versions v ON v.id = c.current_version_id
            WHERE c.project_id=? AND (? IS NULL OR c.bid_document_id=?)
            ORDER BY c.sort_order
            """,
            (project_id, bid_document_id, bid_document_id),
        ).fetchall()
    finally:
        conn.close()

    risk_level = "high" if any(item["severity"] == "error" for item in issues) else ("medium" if issues else "low")
    response_summary = {item["response_status"]: item["total"] for item in response_items}
    total_requirements = sum(item["total"] for item in response_items)
    covered_count = response_summary.get("covered", 0)
    coverage_rate = (covered_count / total_requirements * 100) if total_requirements > 0 else 0

    llm_analysis = None
    try:
        from services.model_router import model_router
        issues_text = "\n".join(f"- [{item['severity']}] {item['issue_text']}" for item in issues[:15])
        chapters_text = "\n".join(
            f"- {ch['chapter_title']} ({ch.get('word_count') or 0}字)"
            for ch in chapters
        )
        prompt = (
            "你是招投标合规审核专家。请根据以下信息生成合规审核报告。\n\n"
            f"一致性问题列表：\n{issues_text or '无'}\n\n"
            f"响应矩阵覆盖率：{coverage_rate:.1f}% ({covered_count}/{total_requirements})\n\n"
            f"章节列表：\n{chapters_text}\n\n"
            "请输出JSON格式的审核报告：\n"
            "{\n"
            '  "overall_assessment": "总体评估（一句话）",\n'
            '  "risk_level": "high|medium|low",\n'
            '  "missing_responses": ["漏响应项列表"],\n'
            '  "compliance_risks": ["合规风险列表"],\n'
            '  "improvement_suggestions": ["改进建议列表"]\n'
            "}"
        )
        response = model_router.chat(
            [{"role": "user", "content": prompt}],
            task_type="review",
            response_format={"type": "json_object"},
            project_id=project_id,
            timeout=30,
        )
        llm_output = response["output"]["choices"][0]["message"]["content"]
        llm_analysis = json.loads(llm_output)
        if llm_analysis.get("risk_level") == "high":
            risk_level = "high"
    except Exception as exc:
        LOGGER.warning("LLM compliance review degraded: %s", str(exc)[:200])

    report = {
        "issues": issues,
        "response_matrix": response_items,
        "risk_level": risk_level,
        "coverage_rate": round(coverage_rate, 1),
        "total_requirements": total_requirements,
        "covered_count": covered_count,
        "llm_analysis": llm_analysis,
    }

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO compliance_reports
            (tenant_id, project_id, bid_document_id, report_type, summary, report_json,
             risk_level, created_by_agent_run_id, created_at, updated_at)
            VALUES (1, ?, ?, 'full_review', ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                bid_document_id,
                (llm_analysis or {}).get("overall_assessment") or f"{len(issues)} open consistency/compliance issues. Coverage: {coverage_rate:.1f}%",
                json_dumps(report),
                risk_level,
                run_id,
                now(),
                now(),
            ),
        )
        report_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    agent_runs.finish(run_id, output_value={
        "report_id": report_id,
        "risk_level": risk_level,
        "issue_count": len(issues),
        "coverage_rate": coverage_rate,
    })
    return {"report_id": report_id, **report}


class PatchConflictError(Exception):
    pass


def generate_rewrite_patch(*, project_id, chapter_id, selected_text, instruction, generation_task_id=None):
    run_id = agent_runs.start(
        generation_task_id=generation_task_id,
        project_id=project_id,
        agent_name="SectionWriterAgent",
        input_value={"chapter_id": chapter_id, "rewrite_scope": "selection", "instruction": instruction},
    )
    try:
        conn = get_db()
        try:
            chapter = conn.execute("SELECT * FROM bid_chapters WHERE id=?", (chapter_id,)).fetchone()
            version = conn.execute(
                "SELECT content FROM bid_chapter_versions WHERE id=?",
                (chapter.get("current_version_id"),),
            ).fetchone() if chapter and chapter.get("current_version_id") else None
        finally:
            conn.close()

        if not chapter or not version:
            raise ValueError("Chapter or current version not found.")

        full_content = version.get("content") or ""
        if selected_text not in full_content:
            raise PatchConflictError("选中文本在当前章节版本中不存在。")

        pos = full_content.index(selected_text)
        context_before = full_content[max(0, pos - 500):pos]
        context_after = full_content[pos + len(selected_text):pos + len(selected_text) + 500]

        import hashlib
        context_hash = hashlib.sha256(
            (context_before[-200:] + selected_text + context_after[:200]).encode("utf-8")
        ).hexdigest()[:16]

        facts_text = context_text(project_id)

        from services.model_router import model_router
        prompt = (
            "你是投标文件改写专家。用户选中了以下文本并要求修改。\n\n"
            f"项目事实：\n{facts_text[:1500]}\n\n"
            f"选中文本：\n---\n{selected_text}\n---\n\n"
            f"上下文（选中文本前）：\n---\n{context_before[-300:]}\n---\n\n"
            f"上下文（选中文本后）：\n---\n{context_after[:300]}\n---\n\n"
            f"用户指令：{instruction}\n\n"
            "要求：\n"
            "1. 只输出替换后的新文本，不要输出其他内容\n"
            "2. 保持与上下文的语气和格式一致\n"
            "3. 不要改变选中范围之外的内容\n"
            "4. 保持专业投标文件的语言风格\n"
            "5. 不要编造企业资质、案例、人员等事实信息"
        )
        response = model_router.chat(
            [{"role": "user", "content": prompt}],
            task_type="generate_chapter",
            generation_task_id=generation_task_id,
            project_id=project_id,
            timeout=60,
        )
        new_text = response["output"]["choices"][0]["message"]["content"].strip()

        change_summary_prompt = (
            f"用一句话概括以下修改：\n原文：{selected_text[:200]}\n新文：{new_text[:200]}\n"
            "输出格式：一句中文概括"
        )
        try:
            summary_response = model_router.chat(
                [{"role": "user", "content": change_summary_prompt}],
                task_type="review",
                timeout=15,
            )
            change_summary = summary_response["output"]["choices"][0]["message"]["content"].strip()[:200]
        except Exception:
            change_summary = f"改写选中文本（{len(selected_text)}字 → {len(new_text)}字）"

        patch = {
            "operation": "replace_selection",
            "original_text": selected_text,
            "new_text": new_text,
            "context_hash": context_hash,
            "change_summary": change_summary,
        }

        agent_runs.finish(run_id, output_value={
            "patch_operation": "replace_selection",
            "original_length": len(selected_text),
            "new_length": len(new_text),
        })
        return patch
    except Exception as exc:
        agent_runs.finish(run_id, status="failed", error_message=str(exc)[:1000])
        raise


def apply_selection_patch(chapter_content, patch):
    original = patch.get("original_text")
    new_text = patch.get("new_text")

    if not original or not new_text:
        raise PatchConflictError("Patch 数据不完整。")

    if original not in chapter_content:
        raise PatchConflictError("选中文本在当前版本中已不存在，可能已被其他修改覆盖。")

    count = chapter_content.count(original)
    if count > 1:
        raise PatchConflictError("选中文本在章节中出现多次，无法确定替换位置。请提供更长的选区。")

    return chapter_content.replace(original, new_text, 1)


def create_response_matrix_from_analysis(*, project_id, bid_document_id=None, chapters=None):
    conn = get_db()
    try:
        project = conn.execute("SELECT analysis_data FROM bid_projects WHERE id=?", (project_id,)).fetchone()
        analysis = {}
        if project and project.get("analysis_data"):
            try:
                analysis = json.loads(project["analysis_data"])
            except (TypeError, json.JSONDecodeError):
                analysis = {}
        raw_requirements = "\n".join(
            str(analysis.get(key) or "")
            for key in ["bidding_requirements", "bidding_meta", "bidding_summary"]
        )
        candidates = [
            item.strip(" -;\t")
            for item in re.split(r"[\n。；;]", raw_requirements)
            if len(item.strip()) >= 8
        ][:30]
        if not candidates and chapters:
            candidates = [f"Cover chapter requirement: {chapter.get('title')}" for chapter in chapters if chapter.get("title")]
        existing = conn.execute(
            "SELECT COUNT(*) AS total FROM response_matrix_items WHERE project_id=? AND (bid_document_id=? OR ? IS NULL)",
            (project_id, bid_document_id, bid_document_id),
        ).fetchone()
        if existing and int(existing["total"]) > 0:
            return {"created": 0}
        cursor = conn.cursor()
        for requirement in candidates:
            cursor.execute(
                """
                INSERT INTO response_matrix_items
                (tenant_id, project_id, bid_document_id, requirement_type, requirement_text,
                 response_status, created_at, updated_at)
                VALUES (1, ?, ?, 'generated_requirement', ?, 'pending', ?, ?)
                """,
                (project_id, bid_document_id, requirement[:2000], now(), now()),
            )
        conn.commit()
        return {"created": len(candidates)}
    finally:
        conn.close()


def mark_response_matrix_coverage(*, project_id, bid_document_id=None):
    conn = get_db()
    try:
        items = conn.execute(
            """
            SELECT id, requirement_text
            FROM response_matrix_items
            WHERE project_id=? AND (bid_document_id=? OR ? IS NULL)
            """,
            (project_id, bid_document_id, bid_document_id),
        ).fetchall()
        chapters = conn.execute(
            """
            SELECT v.content
            FROM bid_chapters c
            JOIN bid_chapter_versions v ON v.id = c.current_version_id
            WHERE c.project_id=? AND (? IS NULL OR c.bid_document_id=?)
            """,
            (project_id, bid_document_id, bid_document_id),
        ).fetchall()
        full_text = "\n".join(row.get("content") or "" for row in chapters)
        cursor = conn.cursor()
        covered = 0
        for item in items:
            terms = [token for token in re.split(r"\s+", item["requirement_text"]) if len(token) >= 2]
            is_covered = bool(terms and any(term in full_text for term in terms[:8]))
            if is_covered:
                covered += 1
            cursor.execute(
                """
                UPDATE response_matrix_items
                SET response_status=?, evidence_text=?, updated_at=?
                WHERE id=?
                """,
                (
                    "covered" if is_covered else "pending",
                    "Matched generated chapter text." if is_covered else None,
                    now(),
                    item["id"],
                ),
            )
        conn.commit()
        return {"total": len(items), "covered": covered}
    finally:
        conn.close()


def build_writer_context(*, project_id, chapter_title, chapter_description, evidence_pack):
    source_lines = []
    for item in evidence_pack.get("results", []):
        if item.get("source_url"):
            source_lines.append(
                f"- {item.get('source_title')} | {item.get('source_url')} | reflection: {item.get('reflection_reason') or 'selected'}"
            )
    return "\n\n".join(
        [
            "Authoritative project context:",
            context_text(project_id),
            "Chapter target:",
            f"{chapter_title}\n{chapter_description}",
            "Evidence Pack:",
            evidence_pack.get("context_text") or "No evidence found. Continue only with confirmed project facts and tender requirements.",
            "Web search sources selected by reflection:",
            "\n".join(source_lines) or "- none",
        ]
    )
