import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import jwt
import requests
from flask import Blueprint, jsonify, request

from core.db import get_db
from export.md_to_word import convert_md_to_word
from services.agent_orchestrator import (
    agent_runs,
    build_writer_context,
    check_chapter_consistency,
    create_chapter_version,
    create_compliance_report,
    create_evidence_pack,
    create_response_matrix_from_analysis,
    mark_response_matrix_coverage,
    run_fact_keeper_agent,
    run_tender_parser_agent,
)
from services.chapter_title import dedupe_by_chapter_title
from services.ingestion_service import extract_text_from_bytes, ingest_document
from services.outline_builder import build_outline
from services.tender_format_parser import parse_tender_format
from services.template_validation import is_valid_template_text
from services.qwen_client import call_dashscope_api, generate_bid_section
from storage.storage_service import BlobTooLarge, FileTypeNotAllowed, StorageError, storage_service


bp = Blueprint("bidding", __name__)

ONLYOFFICE_JWT_SECRET = os.getenv("ONLYOFFICE_JWT_SECRET", "fsdftertrt34768586sfhjsdhfjhhjfsuhaiubue")
BACKEND_URL_FOR_DOCKER = os.getenv("BACKEND_URL_FOR_DOCKER", "host.docker.internal:3012")


def _now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _json(value):
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value, default=None):
    if not value:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _row(sql, params=()):
    conn = get_db()
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def _latest_task_output(conn, project_id):
    latest_legacy_task = conn.execute(
        """
        SELECT output_json
        FROM generation_tasks
        WHERE project_id=? AND task_type='generate_document' AND status='succeeded'
        ORDER BY id DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    latest_agent_task = conn.execute(
        """
        SELECT output_json
        FROM agent_task
        WHERE project_id=? AND task_type IN ('project_export', 'project_generate') AND status='succeeded'
        ORDER BY id DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    legacy_output = _json_loads((latest_legacy_task or {}).get("output_json"), {}) or {}
    agent_output = _json_loads((latest_agent_task or {}).get("output_json"), {}) or {}
    return {**legacy_output, **agent_output}


def _generated_file_id_from_output(output):
    return output.get("wordFileId") or output.get("generatedFileId") or output.get("fileId")


def _latest_generated_docx_file_id(conn, project_id, preferred_file_id=None):
    if preferred_file_id:
        preferred = conn.execute(
            """
            SELECT id
            FROM document_files
            WHERE id=? AND project_id=? AND deleted_at IS NULL
              AND (file_category='generated_bid' OR file_ext='.docx')
            """,
            (preferred_file_id, project_id),
        ).fetchone()
        if preferred:
            return preferred["id"]
    row = conn.execute(
        """
        SELECT id
        FROM document_files
        WHERE project_id=? AND deleted_at IS NULL
          AND (file_category='generated_bid' OR file_ext='.docx')
        ORDER BY id DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    return (row or {}).get("id")


def _create_project(cursor, user_id, original_filename):
    now = _now()
    project_name = Path(original_filename).stem or original_filename
    project_code = f"BID-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    cursor.execute(
        """
        INSERT INTO bid_projects
        (tenant_id, company_id, project_code, project_name, project_status, owner_user_id, created_at, updated_at)
        VALUES (1, 1, ?, ?, 'draft', ?, ?, ?)
        """,
        (project_code, project_name, user_id, now, now),
    )
    project_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT IGNORE INTO project_members (project_id, tenant_id, user_id, project_role, joined_at)
        VALUES (?, 1, ?, 'owner', ?)
        """,
        (project_id, user_id, now),
    )
    return project_id


def _ensure_upload_user(cursor, user_id):
    cursor.execute("SELECT id FROM users WHERE id=?", (user_id,))
    existing = cursor.fetchone()
    if existing:
        return existing["id"]
    fingerprint_id = f"upload-user-{user_id}"
    cursor.execute("SELECT id FROM users WHERE fingerprint_id=?", (fingerprint_id,))
    existing = cursor.fetchone()
    if existing:
        return existing["id"]
    now = _now()
    cursor.execute(
        """
        INSERT INTO users (tenant_id, fingerprint_id, username, display_name, status, created_at, updated_at)
        VALUES (1, ?, ?, ?, 'active', ?, ?)
        """,
        (fingerprint_id, f"user-{user_id}", f"用户{user_id}", now, now),
    )
    ensured_user_id = cursor.lastrowid
    cursor.execute(
        "INSERT IGNORE INTO user_roles (user_id, role_id, tenant_id, created_at) VALUES (?, 1, 1, ?)",
        (ensured_user_id, now),
    )
    return ensured_user_id


def _update_project(project_id, **fields):
    if not project_id:
        return
    assignments = ["updated_at = ?"]
    params = [_now()]
    for key, value in fields.items():
        assignments.append(f"{key} = ?")
        params.append(value)
    params.append(project_id)
    conn = get_db()
    try:
        conn.execute(f"UPDATE bid_projects SET {', '.join(assignments)} WHERE id = ?", tuple(params))
        conn.commit()
    finally:
        conn.close()


def _create_task(cursor, project_id, task_type, input_value=None):
    now = _now()
    cursor.execute(
        """
        INSERT INTO generation_tasks
        (tenant_id, project_id, task_type, status, input_json, created_at, updated_at)
        VALUES (1, ?, ?, 'running', ?, ?, ?)
        """,
        (project_id, task_type, _json(input_value or {}), now, now),
    )
    return cursor.lastrowid


def _finish_task(task_id, status, output_value=None, error_message=None):
    conn = get_db()
    try:
        conn.execute(
            """
            UPDATE generation_tasks
            SET status = ?, output_json = ?, error_message = ?, finished_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, _json(output_value or {}), error_message, _now(), _now(), task_id),
        )
        conn.commit()
    finally:
        conn.close()


def _parse_llm_json(response):
    content = response["output"]["choices"][0]["message"]["content"]
    clean = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    match = re.search(r"```json\s*(.*?)\s*```", clean, re.DOTALL)
    text = match.group(1) if match else clean.replace("```json", "").replace("```", "").strip()
    text = re.sub(r"[\x00-\x1F\x7F]", "", text).strip().rstrip(",")
    return json.loads(text), content


def read_tender_file(bidding_id):
    bidding = _row("SELECT * FROM bidding WHERE id = ?", (bidding_id,))
    if not bidding:
        return None
    blob = storage_service.get_latest(bidding["file_id"])
    return blob.get("content_text") or extract_text_from_bytes(blob["original_filename"], blob["content"])


def _title_core(text):
    clean = re.sub(r"^#+\s*", "", text or "").strip()
    clean = re.sub(r"^(?:第\s*)?\d+\s*章\s*", "", clean)
    clean = re.sub(r"^(?:[一二三四五六七八九十]+|\d+)[、．.]\s*", "", clean)
    return re.sub(r"\s+", "", clean)


def _template_starts_with_title(content, section_name):
    for line in (content or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        return _title_core(stripped) == _title_core(section_name)
    return False


def merge_sections(section_contents):
    parts = []
    for index, item in enumerate(section_contents, 1):
        if len(item) == 3:
            section_name, content, chapter = item
        else:
            section_name, content = item
            chapter = {}
        clean_content = content.strip()
        if clean_content.startswith('```'):
            clean_content = re.sub(r'^```\w*\n?', '', clean_content)
            clean_content = re.sub(r'\n?```$', '', clean_content)
        if _is_template_locked_chapter(chapter):
            parts.append(f"<!-- locked_template -->\n{clean_content}\n<!-- /locked_template -->\n")
            continue
        if not clean_content.startswith('#'):
            parts.append(f"## 第{index}章 {section_name}\n\n{clean_content}\n")
        else:
            parts.append(f"{clean_content}\n")
    return "\n".join(parts)


def _chapter_description(chapter):
    parts = []
    if chapter.get("content"):
        parts.append(f"章节说明：{chapter['content']}")
    if chapter.get("describe"):
        parts.append(f"要求：{chapter['describe']}")
    if chapter.get("target_words"):
        parts.append(f"目标字数：{chapter['target_words']}字")
    for section in chapter.get("sections", []):
        if section.get("title"):
            parts.append(f"\n二级节：{section['title']}")
        for subsection in section.get("subsections", []):
            title = subsection.get("title", "")
            describe = subsection.get("describe", "")
            if title:
                min_words = subsection.get("min_words") or chapter.get("min_subsection_words")
                parts.append(f"  三级小节：{title}" + (f"（正文不少于{min_words}字）" if min_words else ""))
            if describe:
                parts.append(f"    内容要求：{describe}")
    if chapter.get("min_heading_level"):
        parts.append(f"\n标题层级要求：至少写到{chapter['min_heading_level']}级标题。")
    if chapter.get("min_subsection_words"):
        parts.append(f"三级小节篇幅要求：每个三级小节正文不少于{chapter['min_subsection_words']}字。")
    return "\n".join(parts)


def _get_template_for_chapter(analysis_data, chapter_title):
    """从 analysis_data 中模糊匹配并返回模板文本"""
    templates = (analysis_data or {}).get("template_contents", {})
    if not templates:
        return None
    if chapter_title in templates:
        return templates[chapter_title].get("template_text", "")
    for key, val in templates.items():
        if key in chapter_title or chapter_title in key:
            return val.get("template_text", "")
    for key, val in templates.items():
        key_chars = set(key.replace(" ", ""))
        title_chars = set(chapter_title.replace(" ", ""))
        if len(key_chars & title_chars) / max(len(key_chars | title_chars), 1) > 0.5:
            return val.get("template_text", "")
    return None


def _is_template_locked_chapter(chapter):
    chapter_type = (chapter.get("type") or "normal").lower()
    return chapter_type in {"table", "form", "locked_template"}


def _template_needs_review(chapter):
    return chapter.get("templateStatus") in {"toc_only", "missing"}


def _select_template_content(analysis, title, chapter):
    source_text = chapter.get("sourceText") or ""
    if source_text and is_valid_template_text(title, source_text):
        return source_text
    template_content = _get_template_for_chapter(analysis, title)
    if template_content and is_valid_template_text(title, template_content):
        return template_content
    return ""


def _template_generation_blockers(chapters, analysis):
    blockers = []
    for chapter in chapters or []:
        if not _is_template_locked_chapter(chapter):
            continue
        title = chapter.get("title") or "未命名模板章节"
        if _template_needs_review(chapter):
            reason = "只识别到目录项，未识别到招标文件正文模板" if chapter.get("templateStatus") == "toc_only" else "缺少招标文件正文模板"
            blockers.append({"title": title, "reason": reason})
            continue
        if not _select_template_content(analysis, title, chapter):
            blockers.append({"title": title, "reason": "未识别到有效正文模板"})
    return blockers


def _chapter_score(chapter):
    score = len(chapter.get("sourceText") or "")
    if chapter.get("templateStatus") == "valid":
        score += 100000
    if chapter.get("sourceText"):
        score += 1000
    if chapter.get("sections"):
        score += len(chapter.get("sections") or [])
    return score


def _replace_outside_locked_templates(content, replace_fn):
    parts = re.split(r"(<!-- locked_template -->.*?<!-- /locked_template -->)", content or "", flags=re.DOTALL)
    return "".join(part if part.startswith("<!-- locked_template -->") else replace_fn(part) for part in parts)


def _fill_template_placeholders(project_id, template_text):
    """用项目事实和企业信息填充模板中的占位符"""
    conn = get_db()
    try:
        facts_rows = conn.execute(
            "SELECT fact_key, fact_value FROM project_facts WHERE project_id=?",
            (project_id,),
        ).fetchall()
    finally:
        conn.close()

    fact_map = {r["fact_key"]: r["fact_value"] for r in facts_rows} if facts_rows else {}

    from datetime import datetime
    today = datetime.now().strftime("%Y年%m月%d日")

    placeholder_map = {
        "采购人名称": fact_map.get("purchaser_name", ""),
        "采购人": fact_map.get("purchaser_name", ""),
        "招标人名称": fact_map.get("purchaser_name", ""),
        "招标人": fact_map.get("purchaser_name", ""),
        "项目名称": fact_map.get("project_name", ""),
        "招标编号": fact_map.get("tender_no", ""),
        "项目编号": fact_map.get("tender_no", ""),
        "投标人名称": fact_map.get("bidder_name", ""),
        "投标人": fact_map.get("bidder_name", ""),
        "法定代表人": fact_map.get("legal_representative", ""),
        "服务期限": fact_map.get("service_period", ""),
        "投标日期": today,
        "日期": today,
    }

    result = template_text
    for placeholder, value in placeholder_map.items():
        if value:
            result = result.replace(f"[{placeholder}]", value)
            result = result.replace(f"【{placeholder}】", value)

    return result


_DATA_DEPENDENT_KEYWORDS = [
    "人员配置", "团队", "项目经理", "人员",
    "业绩", "案例", "类似项目", "项目经验",
    "资质证书", "荣誉", "证书",
]


def _is_data_dependent_chapter(title):
    """判断章节是否依赖知识库中的真实数据（不应编造）"""
    return any(kw in title for kw in _DATA_DEPENDENT_KEYWORDS)


def _check_scoring_coverage(project_id, full_text):
    """检查生成内容对评分点的覆盖率"""
    conn = get_db()
    try:
        project = conn.execute("SELECT analysis_data FROM bid_projects WHERE id=?", (project_id,)).fetchone()
    finally:
        conn.close()
    if not project or not project.get("analysis_data"):
        return None

    try:
        analysis = json.loads(project["analysis_data"])
    except (TypeError, json.JSONDecodeError):
        return None

    meta_text = analysis.get("bidding_meta") or analysis.get("bidding_requirements") or ""
    if not meta_text:
        return None

    scoring_items = [
        item.strip(" -·•\t")
        for item in re.split(r'[\n。；;]', meta_text)
        if len(item.strip()) >= 6
    ][:30]

    if not scoring_items:
        return None

    covered = []
    missing = []
    for item in scoring_items:
        keywords = [w for w in re.split(r'[\s,，、]+', item) if len(w) >= 2][:5]
        hit = any(kw in full_text for kw in keywords)
        if hit:
            covered.append(item)
        else:
            missing.append(item)

    total = len(scoring_items)
    coverage_rate = len(covered) / total * 100 if total > 0 else 0

    return {
        "total": total,
        "covered": len(covered),
        "missing_count": len(missing),
        "coverage_rate": round(coverage_rate, 1),
        "missing_items": missing[:10],
    }


def _fill_enterprise_info(project_id, content):
    """从 project_facts 和知识库中提取企业信息，替换生成内容中的通用占位符"""
    conn = get_db()
    try:
        facts = conn.execute(
            "SELECT fact_key, fact_value FROM project_facts WHERE project_id=?",
            (project_id,),
        ).fetchall()
        company = conn.execute(
            """
            SELECT c.company_name, c.legal_representative, c.registered_address, c.business_scope
            FROM companies c
            JOIN bid_projects p ON p.company_id = c.id
            WHERE p.id=?
            """,
            (project_id,),
        ).fetchone()
    finally:
        conn.close()

    fact_map = {row["fact_key"]: row["fact_value"] for row in facts}

    replacements = {
        "本公司": fact_map.get("bidder_name") or (company["company_name"] if company else "本公司"),
        "投标人": fact_map.get("bidder_name") or (company["company_name"] if company else "投标人"),
        "XX公司": fact_map.get("bidder_name") or (company["company_name"] if company else ""),
        "XX项目": fact_map.get("project_name") or "",
        "采购人": fact_map.get("purchaser_name") or "采购人",
        "招标人": fact_map.get("purchaser_name") or "招标人",
    }

    def apply_replacements(text):
        result = text
        for placeholder, value in replacements.items():
            if value and placeholder != value:
                result = result.replace(f"[{placeholder}]", value)
                result = result.replace(f"【{placeholder}】", value)
                result = result.replace(f"${{{placeholder}}}", value)
                result = result.replace(f"{{{{{placeholder}}}}}", value)

        if fact_map.get("bidder_name"):
            result = result.replace("XX科技有限公司", fact_map["bidder_name"])
            result = result.replace("XX有限公司", fact_map["bidder_name"])
        if fact_map.get("project_name"):
            result = result.replace("XX项目", fact_map["project_name"])
            result = result.replace("本项目", fact_map["project_name"])
        return result

    return _replace_outside_locked_templates(content, apply_replacements)


@bp.route("/projects", methods=["GET"])
def list_projects():
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT
                p.id,
                p.project_code,
                p.project_name,
                p.purchaser_name,
                p.industry,
                p.region,
                p.project_status,
                p.created_at,
                b.id AS bidding_id,
                b.original_filename AS bidding_filename,
                b.status AS bidding_status,
                legacy_task.id AS latest_generation_task_id,
                legacy_task.task_type AS latest_generation_task_type,
                legacy_task.status AS latest_generation_task_status,
                legacy_task.updated_at AS latest_generation_task_updated_at,
                agent_task.id AS latest_agent_task_id,
                agent_task.task_type AS latest_agent_task_type,
                agent_task.status AS latest_agent_task_status,
                agent_task.updated_at AS latest_agent_task_updated_at,
                COALESCE(chapter_stats.total_chapters, 0) AS total_chapters,
                COALESCE(chapter_stats.generated_chapters, 0) AS generated_chapters,
                COALESCE(chapter_stats.pending_chapters, 0) AS pending_chapters
            FROM bid_projects p
            LEFT JOIN (
                SELECT b1.*
                FROM bidding b1
                INNER JOIN (
                    SELECT project_id, MAX(id) AS max_id
                    FROM bidding
                    GROUP BY project_id
                ) latest_bidding ON latest_bidding.max_id = b1.id
            ) b ON b.project_id = p.id
            LEFT JOIN (
                SELECT t1.*
                FROM generation_tasks t1
                INNER JOIN (
                    SELECT project_id, MAX(id) AS max_id
                    FROM generation_tasks
                    GROUP BY project_id
                ) latest_legacy_task ON latest_legacy_task.max_id = t1.id
            ) legacy_task ON legacy_task.project_id = p.id
            LEFT JOIN (
                SELECT t1.*
                FROM agent_task t1
                INNER JOIN (
                    SELECT project_id, MAX(id) AS max_id
                    FROM agent_task
                    GROUP BY project_id
                ) latest_agent_task ON latest_agent_task.max_id = t1.id
            ) agent_task ON agent_task.project_id = p.id
            LEFT JOIN (
                SELECT
                    c.project_id,
                    c.bid_document_id,
                    COUNT(*) AS total_chapters,
                    SUM(CASE WHEN c.current_version_id IS NOT NULL OR c.status IN ('generated', 'ready') THEN 1 ELSE 0 END) AS generated_chapters,
                    SUM(CASE WHEN c.current_version_id IS NULL AND c.status NOT IN ('generated', 'ready') THEN 1 ELSE 0 END) AS pending_chapters
                FROM bid_chapters c
                INNER JOIN (
                    SELECT project_id, MAX(id) AS latest_doc_id
                    FROM bid_documents
                    WHERE deleted_at IS NULL
                    GROUP BY project_id
                ) latest_doc ON latest_doc.project_id = c.project_id AND latest_doc.latest_doc_id = c.bid_document_id
                GROUP BY c.project_id, c.bid_document_id
            ) chapter_stats ON chapter_stats.project_id = p.id
            WHERE p.deleted_at IS NULL
            ORDER BY p.id DESC
            LIMIT 50
            """,
        ).fetchall()
        return jsonify({"items": rows})
    finally:
        conn.close()


@bp.route("/projects/<int:project_id>", methods=["GET"])
def get_project(project_id):
    conn = get_db()
    try:
        project = conn.execute(
            "SELECT * FROM bid_projects WHERE id=? AND deleted_at IS NULL",
            (project_id,),
        ).fetchone()
        if not project:
            return jsonify({"error": "Project not found."}), 404
        bidding = conn.execute(
            "SELECT id, original_filename, status, bid_document, generated_file_id, document_key FROM bidding WHERE project_id=? ORDER BY id DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        bid_document = conn.execute(
            """
            SELECT id, current_version_id, status
            FROM bid_documents
            WHERE project_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        result = dict(project)
        analysis_data = _json_loads(result.get("analysis_data"), {})
        directory_structure = _json_loads(result.get("directory_structure"), None)
        latest_output = _latest_task_output(conn, project_id)
        result["biddingId"] = bidding["id"] if bidding else None
        result["biddingFilename"] = bidding["original_filename"] if bidding else None
        result["biddingStatus"] = bidding["status"] if bidding else None
        result["generated_file_id"] = (bidding["generated_file_id"] if bidding else None) or _generated_file_id_from_output(latest_output)
        result["document_key"] = bidding["document_key"] if bidding else None
        result["analysisData"] = analysis_data
        result["directoryStructure"] = directory_structure
        result["bidDocumentId"] = (bid_document or {}).get("id") or latest_output.get("bidDocumentId")
        result["bidDocumentStatus"] = (bid_document or {}).get("status")
        result["generatedFileUrl"] = latest_output.get("fileUrl") or (
            f"/api/files/{result['generated_file_id']}/download" if result.get("generated_file_id") else None
        )
        return jsonify(result)
    finally:
        conn.close()


@bp.route("/<int:bidding_id>", methods=["GET"])
def get_bidding(bidding_id):
    conn = get_db()
    try:
        bidding = conn.execute("SELECT * FROM bidding WHERE id=?", (bidding_id,)).fetchone()
        if not bidding:
            return jsonify({"error": "Bidding not found."}), 404
        return jsonify(dict(bidding))
    finally:
        conn.close()


@bp.route("/upload", methods=["POST"])
def upload_bidding():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400
    file = request.files["file"]
    user_id = request.form.get("userId")
    if not file.filename:
        return jsonify({"error": "No file selected."}), 400
    if not user_id:
        return jsonify({"error": "User ID is required for upload."}), 400
    try:
        requested_user_id = int(user_id)
    except ValueError:
        return jsonify({"error": "User ID must be an integer."}), 400

    try:
        content_bytes = file.read()
        conn = get_db()
        cursor = conn.cursor()
        ensured_user_id = _ensure_upload_user(cursor, requested_user_id)
        project_id = _create_project(cursor, ensured_user_id, file.filename)
        conn.commit()
        conn.close()

        stored = storage_service.create_file(
            content_bytes=content_bytes,
            original_filename=file.filename,
            file_category="tender_original",
            owner_user_id=ensured_user_id,
            project_id=project_id,
            change_source="upload",
        )

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO bidding
            (user_id, project_id, file_id, original_filename, storage_path, document_key, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'Uploaded', ?)
            """,
            (ensured_user_id, project_id, stored.file_id, file.filename, stored.storage_key, str(uuid.uuid4()), _now()),
        )
        bidding_id = cursor.lastrowid
        conn.commit()
        conn.close()

        try:
            ingest_document(file_id=stored.file_id, doc_type="tender_original", project_id=project_id)
        except Exception:
            logging.warning("ingest_document failed for uploaded tender file_id=%s", stored.file_id)
            conn = get_db()
            conn.execute("UPDATE document_files SET vector_status='failed', updated_at=? WHERE id=?", (_now(), stored.file_id))
            conn.commit()
            conn.close()

        return jsonify(
            {
                "message": "File uploaded successfully.",
                "biddingId": bidding_id,
                "projectId": project_id,
                "fileId": stored.file_id,
                "originalFilename": file.filename,
            }
        ), 201
    except FileTypeNotAllowed as exc:
        return jsonify({"error": str(exc)}), 400
    except BlobTooLarge as exc:
        return jsonify({"error": str(exc)}), 413
    except Exception as exc:
        logging.exception("upload_bidding failed")
        return jsonify({"error": f"Server error during file upload: {str(exc)}"}), 500


@bp.route("/save-callback", methods=["POST"])
def save_callback():
    try:
        body = request.get_json(force=True)
        if body.get("status") in [2, 6]:
            download_url = body.get("url")
            document_key = body.get("key")
            if download_url:
                conn = get_db()
                cursor = conn.cursor()
                bidding = cursor.execute("SELECT * FROM bidding WHERE document_key = ?", (document_key,)).fetchone()
                if bidding:
                    resp = requests.get(download_url, timeout=60)
                    resp.raise_for_status()
                    file_id = bidding.get("generated_file_id") or bidding.get("file_id")
                    version = storage_service.add_version(
                        file_id=file_id,
                        content_bytes=resp.content,
                        change_source="onlyoffice_save",
                        created_by=bidding["user_id"],
                    )
                    cursor.execute(
                        "UPDATE bidding SET status=?, bid_document=? WHERE id=?",
                        ("Edited", version.get("storage_key") or storage_service.storage_key(file_id, version["version_no"]), bidding["id"]),
                    )
                    conn.commit()
                conn.close()
        return jsonify({"error": 0})
    except Exception:
        logging.exception("save-callback failed")
        return jsonify({"error": 0})


@bp.route("/pre-analysis_bid", methods=["POST"])
def pre_analysis_bid():
    bidding_id = (request.get_json(silent=True) or {}).get("biddingId")
    if not bidding_id:
        return jsonify({"error": "Missing biddingId"}), 400
    bidding = _row("SELECT * FROM bidding WHERE id = ?", (bidding_id,))
    if not bidding:
        return jsonify({"error": "Tender document not found."}), 404

    task_id = None
    try:
        content = read_tender_file(bidding_id)
        conn = get_db()
        task_id = _create_task(conn.cursor(), bidding["project_id"], "pre_analysis", {"biddingId": bidding_id})
        conn.commit()
        conn.close()

        result = run_tender_parser_agent(
            project_id=bidding["project_id"],
            file_id=bidding.get("file_id"),
            tender_content=content,
            generation_task_id=task_id,
        )

        try:
            from services.agent_orchestrator import extract_template_contents
            template_contents = extract_template_contents(
                tender_content=content,
                required_chapters=result.get("bid_document_format", {}).get("required_chapters", []),
                project_id=bidding["project_id"],
                generation_task_id=task_id,
            )
            if template_contents:
                result["template_contents"] = template_contents
        except Exception as exc:
            logging.warning("template extraction failed: %s", str(exc)[:200])

        run_fact_keeper_agent(
            project_id=bidding["project_id"],
            analysis_data=result,
            generation_task_id=task_id,
        )

        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO confirmation_gates
                (tenant_id, project_id, gate_type, gate_status, generation_task_id, created_at, updated_at)
                VALUES (1, ?, 'facts_confirmation', 'pending', ?, ?, ?)
                """,
                (bidding["project_id"], task_id, _now(), _now()),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

        _update_project(bidding["project_id"], analysis_data=_json(result), project_status="analyzing")
        _finish_task(task_id, "succeeded", result)
        return jsonify(result)
    except Exception as exc:
        if task_id:
            _finish_task(task_id, "failed", error_message=str(exc))
        logging.exception("pre_analysis_bid failed")
        return jsonify({"error": f"Pre-analysis failed: {str(exc)}"}), 500


@bp.route("/chapter-analysis_bid", methods=["POST"])
def chapter_analysis_bid():
    bidding_id = (request.get_json(silent=True) or {}).get("biddingId")
    if not bidding_id:
        return jsonify({"error": "Missing biddingId"}), 400
    bidding = _row("SELECT * FROM bidding WHERE id = ?", (bidding_id,))
    if not bidding:
        return jsonify({"error": "Tender document not found."}), 404
    try:
        content = read_tender_file(bidding_id)
        prompt = f"""
You are a bid document structure analyst. Return JSON only:
{{"chapter_format": "..."}}
Tender content:
---
{content}
---
"""
        result, raw = _parse_llm_json(
            call_dashscope_api(
                [{"role": "user", "content": prompt}],
                task_type="chapter_design",
                project_id=bidding["project_id"],
                timeout=25,
                retries=0,
            )
        )
        _update_project(bidding["project_id"], directory_structure=_json(raw), project_status="analyzing")
        return jsonify(result)
    except Exception as exc:
        logging.exception("chapter_analysis_bid failed")
        return jsonify({"error": f"Chapter analysis failed: {str(exc)}"}), 500


@bp.route("/chapter-design", methods=["POST"])
def chapter_design():
    data = request.get_json(silent=True) or {}
    bidding_id = data.get("biddingId")
    if not bidding_id:
        return jsonify({"error": "Missing biddingId"}), 400
    bidding = _row(
        """
        SELECT b.*, p.analysis_data, p.directory_structure
        FROM bidding b LEFT JOIN bid_projects p ON p.id = b.project_id
        WHERE b.id = ?
        """,
        (bidding_id,),
    )
    if not bidding or not bidding.get("analysis_data"):
        return jsonify({"error": "请先完成预分析"}), 400

    format_reqs = data.get("formatRequirements") or {}
    analysis = json.loads(bidding["analysis_data"])

    tender_content = ""
    try:
        tender_content = read_tender_file(bidding_id) or ""
    except Exception as exc:
        logging.warning("read tender text for format parsing failed: %s", str(exc)[:200])

    format_plan = parse_tender_format(tender_content, analysis)
    format_first_outline = build_outline(format_plan, format_reqs, analysis)
    if format_reqs:
        analysis["bid_document_format_confirmed"] = format_reqs
    analysis["outline_generation_mode"] = "tender_format_first" if format_reqs else "free_design"
    _update_project(
        bidding["project_id"],
        analysis_data=_json(analysis),
        directory_structure=_json(format_first_outline),
        project_status="analyzing",
    )
    return jsonify(format_first_outline)


@bp.route("/generate-bid-document", methods=["POST"])
def generate_bid_document():
    data = request.get_json(silent=True) or {}
    bidding_id = data.get("biddingId")
    chapter_design_data = data.get("chapterDesign")
    if not bidding_id:
        return jsonify({"error": "Missing biddingId"}), 400
    if not chapter_design_data:
        return jsonify({"error": "Missing chapterDesign"}), 400
    if isinstance(chapter_design_data, str):
        chapter_design_data = json.loads(chapter_design_data)
    chapters = chapter_design_data.get("chapters", chapter_design_data) if isinstance(chapter_design_data, dict) else chapter_design_data
    if not isinstance(chapters, list):
        return jsonify({"error": "Invalid chapterDesign"}), 400
    chapters = dedupe_by_chapter_title(
        chapters,
        get_title=lambda chapter: chapter.get("title") if isinstance(chapter, dict) else "",
        score_item=lambda chapter: _chapter_score(chapter) if isinstance(chapter, dict) else 0,
    )

    bidding = _row("SELECT * FROM bidding WHERE id = ?", (bidding_id,))
    if not bidding:
        return jsonify({"error": "Tender document not found."}), 404

    conn = get_db()
    try:
        pending_gates = conn.execute(
            "SELECT id, gate_type FROM confirmation_gates WHERE project_id=? AND gate_status='pending'",
            (bidding["project_id"],),
        ).fetchall()
    except Exception:
        pending_gates = []
    finally:
        conn.close()
    if pending_gates:
        return jsonify({
            "error": "Generation blocked: pending confirmation required.",
            "blocked": True,
            "pendingGates": pending_gates,
        }), 409

    analysis = {}
    if bidding.get("project_id"):
        project_row = _row("SELECT analysis_data FROM bid_projects WHERE id=?", (bidding["project_id"],))
        if project_row and project_row.get("analysis_data"):
            try:
                analysis = json.loads(project_row["analysis_data"])
            except (TypeError, json.JSONDecodeError):
                analysis = {}

    template_blockers = _template_generation_blockers(chapters, analysis)
    if template_blockers:
        return jsonify({
            "error": "模板章节缺少招标文件正文，已停止生成。请重新上传包含响应文件格式正文页的招标文件，或在目录确认阶段补充模板正文。",
            "blocked": True,
            "templateBlockers": template_blockers,
        }), 409

    from flask import Response

    def generate_stream():
        conn = get_db()
        cursor = conn.cursor()
        task_id = _create_task(cursor, bidding["project_id"], "generate_document", {"biddingId": bidding_id})
        conn.commit()
        conn.close()

        try:
            _update_project(bidding["project_id"], project_status="generating")
            tender_name = Path(bidding["original_filename"]).stem
            section_contents = []
            total = len(chapters)

            yield f"data: {_json({'type': 'start', 'total': total, 'taskId': task_id})}\n\n"

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO bid_documents (tenant_id, project_id, document_title, status, created_by, created_at, updated_at)
                VALUES (1, ?, ?, 'generating', ?, ?, ?)
                """,
                (bidding["project_id"], bidding["original_filename"], bidding["user_id"], _now(), _now()),
            )
            bid_document_id = cursor.lastrowid
            chapter_rows = []
            for index, chapter in enumerate(chapters):
                cursor.execute(
                    """
                    INSERT INTO bid_chapters
                    (tenant_id, bid_document_id, project_id, chapter_title, chapter_type, sort_order, outline_json, status, created_at, updated_at)
                    VALUES (1, ?, ?, ?, ?, ?, ?, 'planned', ?, ?)
                    """,
                    (
                        bid_document_id,
                        bidding["project_id"],
                        chapter.get("title", f"Chapter {index + 1}"),
                        chapter.get("type", "normal"),
                        index,
                        _json(chapter),
                        _now(),
                        _now(),
                    ),
                )
                chapter_rows.append({"id": cursor.lastrowid, "chapter": chapter})
            conn.commit()
            conn.close()

            # 生成前做一次联网搜索，结果供所有章节共用
            web_research_context = ""
            try:
                yield f"data: {_json({'type': 'progress', 'current': 0, 'total': total, 'chapter': '正在联网搜索相关资料...'})}\n\n"

                conn = get_db()
                try:
                    proj_row = conn.execute("SELECT analysis_data FROM bid_projects WHERE id=?", (bidding["project_id"],)).fetchone()
                finally:
                    conn.close()
                analysis = {}
                if proj_row and proj_row.get("analysis_data"):
                    try:
                        analysis = json.loads(proj_row["analysis_data"])
                    except (TypeError, json.JSONDecodeError):
                        pass

                from services.qwen_client import call_llm_api
                keywords_prompt = f"请从以下招标文件摘要中提取5个最重要的搜索关键词（用逗号分隔）：\n{analysis.get('bidding_summary', tender_name)[:1000]}"
                try:
                    kw_resp = call_llm_api([{"role": "user", "content": keywords_prompt}], task_type="review", timeout=15)
                    search_keywords = kw_resp["output"]["choices"][0]["message"]["content"].strip()
                except Exception:
                    search_keywords = tender_name

                from services.deep_research_service import create_and_run_research_task
                research_bundle = create_and_run_research_task(
                    bidding["project_id"],
                    {"query": search_keywords, "maxSources": 4, "trigger": "pre_generation_search"},
                )
                sources = research_bundle.get("sources") or []
                for src in sources:
                    summary = src.get("summary") or src.get("content_snapshot") or ""
                    if summary:
                        web_research_context += f"\n【{src.get('title', '')}】{summary[:300]}"
                if web_research_context:
                    web_research_context = f"\n\n【联网搜索参考资料】{web_research_context[:2000]}"
            except Exception as exc:
                logging.warning("pre-generation research failed: %s", str(exc)[:200])

            for idx, item in enumerate(chapter_rows):
                chapter_id = item["id"]
                chapter = item["chapter"]
                title = chapter.get("title", f"Chapter {chapter_id}")
                desc = _chapter_description(chapter)

                yield f"data: {_json({'type': 'progress', 'current': idx + 1, 'total': total, 'chapter': title})}\n\n"

                if _is_template_locked_chapter(chapter):
                    template_content = _select_template_content(analysis, title, chapter)
                    if not template_content:
                        raise ValueError(f"{title} 缺少招标文件原始正文模板，请补充后再生成。")
                    content = template_content
                    create_chapter_version(
                        chapter_id=chapter_id, content=content,
                        generation_task_id=task_id,
                    )
                    section_contents.append((title, content, chapter))
                    continue

                try:
                    rag_context = ""
                    try:
                        from services.retrieval_router import retrieval_router
                        pack = retrieval_router.search(desc or title, project_id=bidding["project_id"], limit=3)
                        if pack.get("items"):
                            rag_context = "\n\n".join(
                                f"【参考资料：{item.get('source_title', '')}】\n{item.get('content', '')[:800]}"
                                for item in pack["items"][:3]
                            )
                    except Exception:
                        pass

                    if _is_data_dependent_chapter(title) and not rag_context:
                        content = (
                            f"### {title}\n\n"
                            "（本章节内容需要根据公司实际情况填写。"
                            "请在知识库中上传相关资料（如人员简历、项目业绩、资质证书等）后重新生成，"
                            "或在生成后的文档中手动补充。）"
                        )
                    else:
                        full_context = rag_context + web_research_context
                        content = generate_bid_section(
                            title, desc, full_context,
                            generation_task_id=task_id,
                            project_id=bidding["project_id"],
                        )
                    create_chapter_version(
                        chapter_id=chapter_id, content=content,
                        generation_task_id=task_id,
                    )
                    section_contents.append((title, content, chapter))
                except Exception as exc:
                    logging.warning("chapter failed id=%s: %s", chapter_id, str(exc)[:200])
                    section_contents.append((title, f"（本章生成失败：{str(exc)[:100]}）", chapter))

            yield f"data: {_json({'type': 'progress', 'current': total, 'total': total, 'chapter': '正在合并文档...'})}\n\n"

            markdown_content = merge_sections(section_contents)

            try:
                markdown_content = _fill_enterprise_info(bidding["project_id"], markdown_content)
            except Exception:
                pass

            scoring_report = None
            try:
                scoring_report = _check_scoring_coverage(bidding["project_id"], markdown_content)
                if scoring_report:
                    yield f"data: {_json({'type': 'scoring', 'report': scoring_report})}\n\n"
            except Exception:
                pass

            markdown_filename = f"{tender_name}_bid_document.md"

            try:
                cover_data = None
                doc_facts = {}
                try:
                    conn = get_db()
                    proj_row = conn.execute("SELECT analysis_data FROM bid_projects WHERE id=?", (bidding["project_id"],)).fetchone()
                    fact_rows = conn.execute("SELECT fact_key, fact_value FROM project_facts WHERE project_id=?", (bidding["project_id"],)).fetchall()
                    conn.close()
                    doc_facts = {r["fact_key"]: r["fact_value"] for r in fact_rows}
                    if proj_row and proj_row.get("analysis_data"):
                        ad = json.loads(proj_row["analysis_data"])
                        bdf = ad.get("bid_document_format") or {}
                        cover_data = bdf.get("cover_page")
                except Exception:
                    pass

                with TemporaryDirectory() as tmpdir:
                    markdown_file = Path(tmpdir) / markdown_filename
                    markdown_file.write_text(markdown_content, encoding="utf-8")
                    generated_docx_path = Path(convert_md_to_word(markdown_file, cover_data=cover_data, facts=doc_facts))
                    docx_bytes = generated_docx_path.read_bytes()
            except Exception as exc:
                logging.warning("md_to_word failed: %s", str(exc)[:200])
                docx_bytes = None

            markdown_stored = storage_service.create_file(
                content_bytes=markdown_content.encode("utf-8"),
                original_filename=markdown_filename,
                file_category="generated_markdown",
                owner_user_id=bidding["user_id"],
                project_id=bidding["project_id"],
                content_text=markdown_content,
                content_encoding="utf-8",
                change_source="system_generated",
                allow_generated_ext=True,
            )

            file_url = None
            word_file_id = None
            if docx_bytes:
                docx_filename = f"{tender_name}_bid_document.docx"
                docx_stored = storage_service.create_file(
                    content_bytes=docx_bytes,
                    original_filename=docx_filename,
                    file_category="generated_bid",
                    owner_user_id=bidding["user_id"],
                    project_id=bidding["project_id"],
                    change_source="system_generated",
                    allow_generated_ext=True,
                )
                file_url = f"/api/files/{docx_stored.file_id}/download"
                word_file_id = docx_stored.file_id

            if not file_url:
                file_url = f"/api/files/{markdown_stored.file_id}/download"
                word_file_id = markdown_stored.file_id

            _update_project(bidding["project_id"], project_status="completed")
            try:
                conn = get_db()
                conn.execute(
                    """
                    UPDATE bidding
                    SET status='Generated', generated_file_id=?, bid_document=?, document_key=COALESCE(document_key, ?)
                    WHERE id=?
                    """,
                    (word_file_id, file_url, f"gen-{bidding['project_id']}", bidding_id),
                )
                conn.commit()
                conn.close()
            except Exception:
                logging.exception("failed to persist generated bidding file")
            _finish_task(task_id, "succeeded", {"fileUrl": file_url, "wordFileId": word_file_id, "bidDocumentId": bid_document_id})

            yield f"data: {_json({'type': 'done', 'fileUrl': file_url, 'wordFileId': word_file_id, 'bidDocumentId': bid_document_id, 'markdownFileId': markdown_stored.file_id})}\n\n"

        except Exception as exc:
            logging.exception("generate stream failed")
            try:
                _finish_task(task_id, "failed", error_message=str(exc))
            except Exception:
                pass
            yield f"data: {_json({'type': 'error', 'error': str(exc)[:500]})}\n\n"

    return Response(generate_stream(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


@bp.route("/generation-tasks/<int:task_id>", methods=["GET"])
def get_generation_task(task_id):
    conn = get_db()
    try:
        task = conn.execute("SELECT * FROM generation_tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            return jsonify({"error": "Task not found."}), 404
        result = dict(task)
        if task.get("output_json") and isinstance(task["output_json"], str):
            try:
                result["output"] = json.loads(task["output_json"])
            except (json.JSONDecodeError, TypeError):
                result["output"] = None
        else:
            result["output"] = task.get("output_json")
        return jsonify(result)
    finally:
        conn.close()


@bp.route("/projects/<int:project_id>/editor-config", methods=["GET"])
def get_editor_config(project_id):
    conn = get_db()
    try:
        bidding = conn.execute(
            "SELECT id, original_filename, document_key, generated_file_id FROM bidding WHERE project_id=? ORDER BY id DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        latest_output = _latest_task_output(conn, project_id)
        generated_file_id = _latest_generated_docx_file_id(
            conn,
            project_id,
            preferred_file_id=(bidding or {}).get("generated_file_id") or _generated_file_id_from_output(latest_output),
        )
    finally:
        conn.close()

    if not generated_file_id:
        return jsonify({"error": "No generated Word document found. Please export the project as Word first.", "config": None, "generatedFileId": None})

    try:
        generated_file = storage_service.get_latest(generated_file_id)
    except StorageError:
        return jsonify(
            {
                "error": "Generated document file is missing or cannot be downloaded.",
                "config": None,
                "generatedFileId": generated_file_id,
            }
        )

    bidding_id = (bidding or {}).get("id") or project_id
    doc_key = f"gen_{generated_file_id}_{bidding_id}"
    file_url = f"http://{BACKEND_URL_FOR_DOCKER}/api/files/{generated_file_id}/download"
    callback_url = f"http://{BACKEND_URL_FOR_DOCKER}/api/bidding/save-callback"
    title = (generated_file or {}).get("original_filename") or (bidding or {}).get("original_filename") or "投标文档.docx"

    payload = {
        "document": {
            "fileType": "docx",
            "key": doc_key,
            "title": title,
            "url": file_url,
        },
        "documentType": "word",
        "editorConfig": {
            "callbackUrl": callback_url,
            "mode": "edit",
            "lang": "zh-CN",
            "user": {"id": "1", "name": "用户"},
            "customization": {"forcesave": True, "autosave": True},
        },
    }

    token = jwt.encode(payload, ONLYOFFICE_JWT_SECRET, algorithm="HS256")
    config = {**payload, "token": token}

    return jsonify({"config": config, "generatedFileId": generated_file_id})


@bp.route("/projects/<int:project_id>/facts", methods=["GET"])
def get_project_facts(project_id):
    conn = get_db()
    try:
        facts = conn.execute(
            """
            SELECT id, fact_key AS factKey, fact_label AS factLabel, fact_value AS factValue,
                   value_type AS valueType, source_type AS sourceType, confidence,
                   status, confirmed_by AS confirmedBy, confirmed_at AS confirmedAt
            FROM project_facts
            WHERE project_id=?
            ORDER BY id
            """,
            (project_id,),
        ).fetchall()
        return jsonify({"items": facts})
    finally:
        conn.close()


@bp.route("/projects/<int:project_id>/facts", methods=["PUT"])
def confirm_project_facts(project_id):
    data = request.get_json(silent=True) or {}
    facts_to_confirm = data.get("facts", [])
    user_id = data.get("userId")
    if not facts_to_confirm:
        return jsonify({"error": "No facts provided."}), 400

    conn = get_db()
    try:
        cursor = conn.cursor()
        confirmed_count = 0
        for fact in facts_to_confirm:
            fact_key = fact.get("factKey")
            fact_value = fact.get("factValue")
            status = fact.get("status", "confirmed")
            if not fact_key:
                continue
            if fact_value is not None:
                cursor.execute(
                    """
                    UPDATE project_facts
                    SET fact_value=?, status=?, confirmed_by=?, confirmed_at=?, updated_at=?
                    WHERE project_id=? AND fact_key=?
                    """,
                    (str(fact_value), status, user_id, _now(), _now(), project_id, fact_key),
                )
            else:
                cursor.execute(
                    """
                    UPDATE project_facts
                    SET status=?, confirmed_by=?, confirmed_at=?, updated_at=?
                    WHERE project_id=? AND fact_key=?
                    """,
                    (status, user_id, _now(), _now(), project_id, fact_key),
                )
            confirmed_count += 1

        try:
            cursor.execute(
                """
                UPDATE confirmation_gates
                SET gate_status='confirmed', confirmed_by=?, confirmed_at=?, updated_at=?
                WHERE project_id=? AND gate_type='facts_confirmation' AND gate_status='pending'
                """,
                (user_id, _now(), _now(), project_id),
            )
        except Exception:
            pass
        conn.commit()
        return jsonify({"confirmed": confirmed_count})
    finally:
        conn.close()


@bp.route("/projects/<int:project_id>/confirmation-gates", methods=["GET"])
def get_confirmation_gates(project_id):
    conn = get_db()
    try:
        gates = conn.execute(
            """
            SELECT id, gate_type AS gateType, gate_status AS gateStatus,
                   confirmed_by AS confirmedBy, confirmed_at AS confirmedAt,
                   expires_at AS expiresAt, created_at AS createdAt
            FROM confirmation_gates
            WHERE project_id=?
            ORDER BY id DESC
            """,
            (project_id,),
        ).fetchall()
        return jsonify({"items": gates})
    finally:
        conn.close()


@bp.route("/projects/<int:project_id>/confirmation-gates/<int:gate_id>/confirm", methods=["POST"])
def confirm_gate(project_id, gate_id):
    data = request.get_json(silent=True) or {}
    user_id = data.get("userId")
    conn = get_db()
    try:
        conn.execute(
            """
            UPDATE confirmation_gates
            SET gate_status='confirmed', confirmed_by=?, confirmed_at=?, updated_at=?
            WHERE id=? AND project_id=? AND gate_status='pending'
            """,
            (user_id, _now(), _now(), gate_id, project_id),
        )
        conn.commit()
        return jsonify({"gateId": gate_id, "status": "confirmed"})
    finally:
        conn.close()


@bp.route("/projects/<int:project_id>/confirmation-gates/<int:gate_id>/skip", methods=["POST"])
def skip_gate(project_id, gate_id):
    data = request.get_json(silent=True) or {}
    user_id = data.get("userId")
    conn = get_db()
    try:
        conn.execute(
            """
            UPDATE confirmation_gates
            SET gate_status='skipped', confirmed_by=?, confirmed_at=?, updated_at=?
            WHERE id=? AND project_id=? AND gate_status='pending'
            """,
            (user_id, _now(), _now(), gate_id, project_id),
        )
        conn.commit()
        return jsonify({"gateId": gate_id, "status": "skipped"})
    finally:
        conn.close()
