import json
import logging
import os
import re
from datetime import datetime
from html import unescape
from urllib.parse import urlparse

import requests
from openai import AuthenticationError

from core.db import get_db
from services.ingestion_service import ingest_document
from storage.storage_service import storage_service


LOGGER = logging.getLogger(__name__)


DEFAULT_SOURCES = [
    {
        "title": "China Government Procurement",
        "url": "https://www.ccgp.gov.cn/",
        "source_type": "recent_tender",
    },
    {
        "title": "National Public Resources Trading Platform",
        "url": "https://www.ggzy.gov.cn/",
        "source_type": "recent_tender",
    },
    {
        "title": "Regulation on the Implementation of the Tendering and Bidding Law",
        "url": "https://www.gov.cn/zhengce/zhengceku/2011-12/29/content_4066.htm",
        "source_type": "legal_policy",
    },
    {
        "title": "Fair Competition Review Rules for Tendering and Bidding",
        "url": "https://zfxxgk.ndrc.gov.cn/web/iteminfo.jsp?id=20360",
        "source_type": "legal_policy",
    },
]

DEFAULT_ALLOWED_DOMAINS = {
    "ccgp.gov.cn",
    "www.ccgp.gov.cn",
    "ggzy.gov.cn",
    "www.ggzy.gov.cn",
    "gov.cn",
    "www.gov.cn",
    "zfxxgk.ndrc.gov.cn",
    "ndrc.gov.cn",
}

ALLOWED_SOURCE_TYPES = {"legal_policy", "recent_tender", "industry_standard", "credit_check"}

SEARCH_TEMPLATES = [
    {
        "title": "China Government Procurement search",
        "url": "https://search.ccgp.gov.cn/bxsearch?searchtype=1&page_index=1&bidSort=0&buyerName=&projectId=&pinMu=0&bidType=0&dbselect=bidx&kw={query}",
        "source_type": "recent_tender",
    },
    {
        "title": "National Public Resources Trading Platform",
        "url": "https://www.ggzy.gov.cn/",
        "source_type": "recent_tender",
    },
    {
        "title": "State Council policy search",
        "url": "https://sousuo.www.gov.cn/sousuo/search.shtml?code=17da70961a7&dataTypeId=107&searchWord={query}",
        "source_type": "legal_policy",
    },
]


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def json_dumps(value):
    return json.dumps(value, ensure_ascii=False)


def parse_json(value, fallback):
    if not value:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def allowed_domains():
    extra = {
        item.strip().lower()
        for item in os.getenv("RESEARCH_ALLOWED_DOMAINS", "").split(",")
        if item.strip()
    }
    return DEFAULT_ALLOWED_DOMAINS | extra


def domain_allowed(url):
    domain = urlparse(url).netloc.lower()
    if not domain:
        return False
    domains = allowed_domains()
    return domain in domains or any(domain.endswith("." + item) for item in domains)


def project_profile(project_id):
    conn = get_db()
    try:
        project = conn.execute("SELECT * FROM bid_projects WHERE id=?", (project_id,)).fetchone()
        facts = conn.execute("SELECT fact_key, fact_value FROM project_facts WHERE project_id=?", (project_id,)).fetchall()
        return project, {row["fact_key"]: row["fact_value"] for row in facts}
    finally:
        conn.close()


def strip_html(html):
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", html or "")
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
    title = unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else ""
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(re.sub(r"\s+", " ", text)).strip()
    return title, text


def fetch_source(url):
    response = requests.get(
        url,
        timeout=20,
        headers={"User-Agent": "ai-bidding-deepresearch/1.0"},
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "text" not in content_type and "html" not in content_type and "json" not in content_type:
        return "", f"Unsupported content type: {content_type}"
    response.encoding = response.encoding or response.apparent_encoding
    title, text = strip_html(response.text)
    return title, text[:12000]


def summarize_source(text, project):
    if not text:
        return "Source could not be fetched or did not contain readable text."
    project_name = project.get("project_name") if project else ""
    try:
        from services.model_router import model_router
        prompt = (
            "\u4f60\u662f\u62db\u6295\u6807\u9886\u57df\u7684\u6cd5\u89c4\u548c\u653f\u7b56\u5206\u6790\u4e13\u5bb6\u3002\u8bf7\u5bf9\u4ee5\u4e0b\u7f51\u9875\u5185\u5bb9\u8fdb\u884c\u6458\u8981\u5206\u6790\uff0c"
            "\u63d0\u53d6\u4e0e\u62db\u6295\u6807\u76f8\u5173\u7684\u5173\u952e\u4fe1\u606f\u3001\u6cd5\u89c4\u8981\u70b9\u3001\u653f\u7b56\u8981\u6c42\u6216\u9879\u76ee\u53c2\u8003\u4ef7\u503c\u3002\n"
            f"\u5f53\u524d\u6295\u6807\u9879\u76ee\uff1a{project_name}\n\n"
            f"\u7f51\u9875\u5185\u5bb9\uff08\u622a\u53d6\uff09\uff1a\n{text[:3000]}\n\n"
            "\u8981\u6c42\uff1a\n"
            "1. \u8f93\u51fa\u4e0d\u8d85\u8fc7300\u5b57\u7684\u4e2d\u6587\u6458\u8981\n"
            "2. \u91cd\u70b9\u63d0\u53d6\u6cd5\u89c4\u6761\u6b3e\u3001\u8d44\u683c\u8981\u6c42\u3001\u8bc4\u5206\u6807\u51c6\u3001\u653f\u7b56\u5bfc\u5411\u7b49\u5173\u952e\u4fe1\u606f\n"
            "3. \u5982\u679c\u5185\u5bb9\u4e0e\u62db\u6295\u6807\u65e0\u5173\uff0c\u8bf4\u660e\u8be5\u6765\u6e90\u53c2\u8003\u4ef7\u503c\u6709\u9650"
        )
        response = model_router.chat(
            [{"role": "user", "content": prompt}],
            task_type="review",
            timeout=30,
        )
        summary = response["output"]["choices"][0]["message"]["content"]
        return summary[:900]
    except Exception as exc:
        LOGGER.warning("LLM summarize_source degraded to regex fallback: %s", str(exc)[:200])
        sentences = re.split(r"[\u3002\uff01\uff1f!?]\s*", text)
        picked = [item.strip() for item in sentences if item.strip()][:5]
        base = "; ".join(picked)
        if project_name:
            return f"Reference for {project_name}: {base[:900]}"
        return base[:900]


def build_strategy(project, facts, request_data):
    keywords = request_data.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [item.strip() for item in keywords.split() if item.strip()]
    generated = [
        project.get("project_name") if project else None,
        project.get("industry") if project else None,
        project.get("region") if project else None,
        facts.get("procurement_method"),
        facts.get("service_scope"),
    ]
    keywords.extend(item for item in generated if item)
    return {
        "keywords": list(dict.fromkeys(keywords))[:12],
        "months": int(request_data.get("months") or 12),
        "allowed_domains": sorted(allowed_domains()),
        "source_policy": "official whitelist only unless explicitly supplied and whitelisted",
    }


def build_auto_queries(project, facts, chapter_query=None):
    seeds = [
        project.get("project_name") if project else None,
        project.get("industry") if project else None,
        project.get("region") if project else None,
        facts.get("procurement_method"),
        facts.get("service_scope"),
        chapter_query,
    ]
    normalized = []
    for item in seeds:
        if not item:
            continue
        text = re.sub(r"\s+", " ", str(item)).strip()
        if text:
            normalized.append(text[:80])
    base = " ".join(dict.fromkeys(normalized))[:120]
    queries = [base] if base else []
    if chapter_query:
        queries.append(str(chapter_query)[:120])
    queries.extend(["招标投标 法规 政策", "近期 同类 招标公告 中标公告"])
    return list(dict.fromkeys(item for item in queries if item))[:4]


def build_auto_sources(project, facts, request_data):
    if request_data.get("sources"):
        return normalize_sources(request_data)
    queries = build_auto_queries(project, facts, request_data.get("chapterQuery") or request_data.get("query"))
    sources = []
    for query in queries:
        for template in SEARCH_TEMPLATES:
            sources.append(
                {
                    "title": f"{template['title']}: {query}",
                    "url": template["url"].format(query=requests.utils.quote(query)),
                    "source_type": template["source_type"],
                    "search_query": query,
                }
            )
    sources.extend(DEFAULT_SOURCES)
    seen = set()
    unique = []
    for source in sources:
        if source["url"] in seen:
            continue
        seen.add(source["url"])
        unique.append(source)
    return unique[: int(request_data.get("maxSources") or 8)]


def normalize_source_type(value):
    source_type = value or "recent_tender"
    return source_type if source_type in ALLOWED_SOURCE_TYPES else "recent_tender"


def normalize_sources(request_data):
    user_sources = request_data.get("sources") or []
    normalized = []
    for item in user_sources:
        if isinstance(item, str):
            normalized.append({"url": item, "title": item, "source_type": "recent_tender"})
        elif isinstance(item, dict) and item.get("url"):
            normalized.append(
                {
                    "url": item["url"],
                    "title": item.get("title") or item["url"],
                    "source_type": normalize_source_type(item.get("source_type") or item.get("sourceType")),
                    "publish_date": item.get("publish_date") or item.get("publishDate"),
                }
            )
    return normalized or DEFAULT_SOURCES


def reflect_sources(sources, project, query_text=None):
    reflected = []
    project_name = (project or {}).get("project_name") or ""
    for item in sources:
        score = float(item.get("credibility_score") or 0)
        summary = item.get("summary") or ""
        content = item.get("content") or ""
        reference_value = item.get("reference_value")
        reasons = []
        if item.get("reference_value") in {"fetch_failed", "not_allowed"}:
            score = min(score, 0.2)
            reasons.append(reference_value)
        if item.get("source_type") == "legal_policy":
            score += 0.08
            reasons.append("official_policy_source")
        if item.get("source_type") == "recent_tender":
            score += 0.03
            reasons.append("recent_tender_reference")
        if project_name and project_name in (summary + content):
            score += 0.05
            reasons.append("project_name_match")
        if query_text and any(token and token in (summary + content) for token in str(query_text).split()[:8]):
            score += 0.05
            reasons.append("query_match")
        item["reflection_score"] = max(0.0, min(score, 1.0))
        item["reflection_reason"] = ", ".join(reasons) or "general_reference"
        item["selected_for_generation"] = item["reflection_score"] >= 0.35 and reference_value not in {"fetch_failed", "not_allowed"}
        reflected.append(item)
    return sorted(reflected, key=lambda value: value.get("reflection_score") or 0, reverse=True)


def create_and_run_research_task(project_id, request_data, created_by=None):
    from core.celery_app import is_async_enabled
    from services.agent_orchestrator import agent_runs

    project, facts = project_profile(project_id)
    if not project:
        raise ValueError("Project not found.")
    strategy = build_strategy(project, facts, request_data)
    strategy["auto_search"] = not bool(request_data.get("sources"))

    generation_task_id = request_data.get("generation_task_id")
    run_id = agent_runs.start(
        generation_task_id=generation_task_id,
        project_id=project_id,
        agent_name="DeepResearchAgent",
        input_value={"query": request_data.get("query"), "strategy": strategy},
    )

    current = now()
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO research_tasks
            (tenant_id, project_id, task_type, status, query_json, strategy_json, started_at,
             created_by, created_at, updated_at)
            VALUES (1, ?, 'deep_research', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                "pending" if is_async_enabled() else "running",
                json_dumps(request_data),
                json_dumps(strategy),
                current,
                created_by,
                current,
                current,
            ),
        )
        task_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    if is_async_enabled():
        from tasks.research_tasks import run_research_async
        run_research_async.delay(task_id)
        agent_runs.finish(run_id, output_value={
            "research_task_id": task_id,
            "async": True,
            "status": "pending",
        })
        return get_research_task(task_id)

    try:
        result = run_research_task(task_id)
        agent_runs.finish(run_id, output_value={
            "research_task_id": task_id,
            "source_count": len(result.get("sources") or []),
            "report_id": (result.get("report") or {}).get("id"),
        })
        return result
    except Exception as exc:
        agent_runs.finish(run_id, status="failed", error_message=str(exc)[:1000])
        raise


def build_source_result(source, project):
    url = source["url"]
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not domain_allowed(url):
        return {
            **source,
            "domain": parsed.netloc,
            "summary": "Skipped because the source URL is invalid or the domain is not whitelisted.",
            "content": "",
            "credibility_score": 0.0,
            "reference_value": "not_allowed",
        }

    try:
        fetched_title, content = fetch_source(url)
        source_type = normalize_source_type(source.get("source_type"))
        title = fetched_title or source.get("title") or url
        summary = summarize_source(content, project)
        credibility = 0.92 if source_type == "legal_policy" else 0.82
        return {
            **source,
            "title": title,
            "source_type": source_type,
            "domain": parsed.netloc,
            "summary": summary,
            "content": content,
            "credibility_score": credibility,
            "reference_value": "compliance_reference" if source_type == "legal_policy" else "market_reference",
        }
    except Exception as exc:
        return {
            **source,
            "domain": parsed.netloc,
            "summary": f"Fetch failed: {str(exc)[:240]}",
            "content": "",
            "credibility_score": 0.2,
            "reference_value": "fetch_failed",
        }


def build_report(task, project, sources):
    findings = [item.get("summary", "")[:300] for item in sources if item.get("content")]
    risks = []
    if any(item.get("source_type") == "legal_policy" for item in sources):
        risks.append(
            "Check mandatory qualifications, scoring criteria, procurement method, and fair competition constraints against official policy sources."
        )

    try:
        from services.model_router import model_router
        source_summaries = "\n".join(
            f"- [{item.get('source_type')}] {item.get('title')}: {item.get('summary', '')[:200]}"
            for item in sources if item.get("summary")
        )
        prompt = (
            "你是招投标合规分析专家。根据以下联网研究结果，生成风险分析报告。\n\n"
            f"项目名称：{project.get('project_name') if project else '未知'}\n"
            f"研究来源摘要：\n{source_summaries[:3000]}\n\n"
            "请输出：\n"
            "1. risk_flags: 列出3-5条需要注意的合规风险或政策要点（JSON数组）\n"
            "2. recommendations: 列出2-3条建议（JSON数组）\n"
            "输出格式为JSON: {\"risk_flags\": [...], \"recommendations\": [...]}"
        )
        response = model_router.chat(
            [{"role": "user", "content": prompt}],
            task_type="review",
            response_format={"type": "json_object"},
            timeout=30,
        )
        llm_output = response["output"]["choices"][0]["message"]["content"]
        try:
            analysis = json.loads(llm_output)
            if analysis.get("risk_flags"):
                risks.extend(str(item) for item in analysis["risk_flags"][:5])
            if analysis.get("recommendations"):
                findings.extend(str(item) for item in analysis["recommendations"][:3])
        except (json.JSONDecodeError, TypeError):
            pass
    except Exception as exc:
        LOGGER.warning("LLM build_report analysis degraded: %s", str(exc)[:200])

    return {
        "project_id": task["project_id"],
        "retrieved_at": now(),
        "strategy": parse_json(task.get("strategy_json"), {}),
        "sources": [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "domain": item.get("domain"),
                "source_type": item.get("source_type"),
                "publish_date": item.get("publish_date"),
                "retrieved_at": now(),
                "summary": item.get("summary"),
                "credibility_score": item.get("credibility_score"),
                "reference_value": item.get("reference_value"),
            }
            for item in sources
        ],
        "findings": findings[:12],
        "risk_flags": list(dict.fromkeys(risks))[:12],
    }


def run_research_task(task_id):
    conn = get_db()
    try:
        task = conn.execute("SELECT * FROM research_tasks WHERE id=?", (task_id,)).fetchone()
    finally:
        conn.close()
    if not task:
        raise ValueError("Research task not found.")

    request_data = parse_json(task.get("query_json"), {})
    project, _facts = project_profile(task["project_id"])
    sources = [
        build_source_result(source, project)
        for source in build_auto_sources(project, _facts, request_data)
    ]
    sources = reflect_sources(sources, project, request_data.get("chapterQuery") or request_data.get("query"))
    report = build_report(task, project, sources)
    current = now()

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO research_reports
            (tenant_id, project_id, research_task_id, report_title, report_json, summary,
             findings_json, risk_flags_json, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task["project_id"],
                task_id,
                f"DeepResearch report for {project.get('project_name')}",
                json_dumps(report),
                "\n".join(report["findings"][:5]),
                json_dumps(report["findings"]),
                json_dumps(report["risk_flags"]),
                current,
                current,
            ),
        )
        report_id = cursor.lastrowid
        for item in sources:
            cursor.execute(
                """
                INSERT IGNORE INTO research_sources
                (tenant_id, project_id, research_task_id, research_report_id, source_type, title,
                 source_url, domain, publish_date, retrieved_at, summary, content_snapshot,
                 credibility_score, reference_value, created_at, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task["project_id"],
                    task_id,
                    report_id,
                    normalize_source_type(item.get("source_type")),
                    item.get("title") or item.get("url"),
                    item.get("url"),
                    item.get("domain"),
                    item.get("publish_date"),
                    current,
                    item.get("summary"),
                    item.get("content"),
                    item.get("credibility_score"),
                    json_dumps(
                        {
                            "reference_value": item.get("reference_value"),
                            "search_query": item.get("search_query"),
                            "reflection_score": item.get("reflection_score"),
                            "reflection_reason": item.get("reflection_reason"),
                            "selected_for_generation": item.get("selected_for_generation"),
                        }
                    ),
                    current,
                    current,
                ),
            )
        cursor.execute(
            "UPDATE research_tasks SET status='succeeded', finished_at=?, updated_at=? WHERE id=?",
            (current, current, task_id),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        failed_at = now()
        conn.execute(
            "UPDATE research_tasks SET status='failed', error_message=?, finished_at=?, updated_at=? WHERE id=?",
            (str(exc)[:1000], failed_at, failed_at, task_id),
        )
        conn.commit()
        raise
    finally:
        conn.close()

    return get_research_task(task_id)


def get_research_task(task_id):
    conn = get_db()
    try:
        task = conn.execute("SELECT * FROM research_tasks WHERE id=?", (task_id,)).fetchone()
        report = conn.execute("SELECT * FROM research_reports WHERE research_task_id=? ORDER BY id DESC LIMIT 1", (task_id,)).fetchone()
        sources = conn.execute("SELECT * FROM research_sources WHERE research_task_id=? ORDER BY id", (task_id,)).fetchall()
        return {"task": task, "report": report, "sources": sources}
    finally:
        conn.close()


def list_reports(project_id):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM research_reports WHERE project_id=? ORDER BY id DESC",
            (project_id,),
        ).fetchall()
    finally:
        conn.close()


def confirm_source(source_id, confirmed_by=None):
    conn = get_db()
    try:
        source = conn.execute("SELECT * FROM research_sources WHERE id=?", (source_id,)).fetchone()
    finally:
        conn.close()
    if not source:
        raise ValueError("Research source not found.")

    content = source.get("content_snapshot") or source.get("summary") or source.get("title")
    filename = f"research_source_{source_id}.md"
    text = (
        f"# {source['title']}\n\n"
        f"- URL: {source['source_url']}\n"
        f"- Retrieved at: {source['retrieved_at']}\n"
        f"- Source type: {source['source_type']}\n"
        f"- Credibility score: {source.get('credibility_score')}\n\n"
        f"## Summary\n\n{source.get('summary') or ''}\n\n"
        f"## Snapshot\n\n{content or ''}\n"
    )
    stored = storage_service.create_file(
        content_bytes=text.encode("utf-8"),
        original_filename=filename,
        file_category="research_snapshot",
        owner_user_id=confirmed_by,
        project_id=source["project_id"],
        content_text=text,
        content_encoding="utf-8",
        parse_status="parsed",
        change_source="research_confirm",
        allow_generated_ext=True,
    )

    vector_status = "indexed"
    try:
        ingest_document(
            file_id=stored.file_id,
            doc_type=normalize_source_type(source["source_type"]),
            project_id=source["project_id"],
        )
    except AuthenticationError:
        vector_status = "failed"
    except Exception:
        vector_status = "failed"

    current = now()
    conn = get_db()
    try:
        conn.execute(
            """
            UPDATE research_sources
            SET is_confirmed=1, confirmed_by=?, confirmed_at=?, file_id=?, vector_status=?, updated_at=?
            WHERE id=?
            """,
            (confirmed_by, current, stored.file_id, vector_status, current, source_id),
        )
        conn.commit()
    finally:
        conn.close()
    return {"source_id": source_id, "file_id": stored.file_id, "vector_status": vector_status}
