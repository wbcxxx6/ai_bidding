import json
from datetime import datetime

from flask import Blueprint, jsonify, request

from core.db import get_db
from services.agent_orchestrator import (
    agent_runs,
    apply_selection_patch,
    build_writer_context,
    check_chapter_consistency,
    create_chapter_version,
    create_compliance_report,
    create_evidence_pack,
    generate_rewrite_patch,
    PatchConflictError,
)
from services.qwen_client import generate_bid_section


bp = Blueprint("generation", __name__)


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def json_dumps(value):
    return json.dumps(value or {}, ensure_ascii=False)


def create_task(project_id, task_type, input_value=None, created_by=None):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO generation_tasks
            (tenant_id, project_id, task_type, status, input_json, started_at, created_by, created_at, updated_at)
            VALUES (1, ?, ?, 'running', ?, ?, ?, ?, ?)
            """,
            (project_id, task_type, json_dumps(input_value), now(), created_by, now(), now()),
        )
        task_id = cursor.lastrowid
        conn.commit()
        return task_id
    finally:
        conn.close()


def finish_task(task_id, status, output_value=None, error_message=None):
    conn = get_db()
    try:
        conn.execute(
            """
            UPDATE generation_tasks
            SET status=?, output_json=?, error_message=?, finished_at=?, updated_at=?
            WHERE id=?
            """,
            (status, json_dumps(output_value), error_message, now(), now(), task_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_chapter(chapter_id):
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM bid_chapters WHERE id=?", (chapter_id,)).fetchone()
    finally:
        conn.close()


def regenerate_chapter(chapter_id, instruction=None, created_by=None):
    chapter = get_chapter(chapter_id)
    if not chapter:
        raise ValueError("Chapter not found.")
    outline = chapter.get("outline_json")
    if isinstance(outline, str):
        try:
            outline = json.loads(outline)
        except json.JSONDecodeError:
            outline = {}
    description = "\n".join(
        item
        for item in [
            (outline or {}).get("content"),
            (outline or {}).get("describe"),
            instruction,
        ]
        if item
    )
    task_id = create_task(
        chapter["project_id"],
        "generate_chapter",
        {"chapterId": chapter_id, "instruction": instruction},
        created_by=created_by,
    )
    try:
        evidence = create_evidence_pack(
            project_id=chapter["project_id"],
            query_text=description or chapter["chapter_title"],
            bid_chapter_id=chapter_id,
            generation_task_id=task_id,
        )
        writer_context = build_writer_context(
            project_id=chapter["project_id"],
            chapter_title=chapter["chapter_title"],
            chapter_description=description,
            evidence_pack=evidence,
        )
        run_id = agent_runs.start(
            generation_task_id=task_id,
            project_id=chapter["project_id"],
            agent_name="SectionWriterAgent",
            input_value={"chapter_id": chapter_id, "evidence_pack_id": evidence.get("evidence_pack_id")},
        )
        content = generate_bid_section(
            chapter["chapter_title"],
            description,
            writer_context,
            generation_task_id=task_id,
            project_id=chapter["project_id"],
        )
        version = create_chapter_version(
            chapter_id=chapter_id,
            content=content,
            evidence_pack_id=evidence.get("evidence_pack_id"),
            generation_task_id=task_id,
            agent_run_id=run_id,
            change_source="regenerate",
        )
        agent_runs.finish(run_id, output_value={"chapter_version": version})
        issues = check_chapter_consistency(
            project_id=chapter["project_id"],
            bid_document_id=chapter.get("bid_document_id"),
            bid_chapter_id=chapter_id,
            content=content,
            generation_task_id=task_id,
        )
        output = {"chapterId": chapter_id, "version": version, "issues": issues["issues"], "evidencePackId": evidence.get("evidence_pack_id")}
        finish_task(task_id, "succeeded", output)
        return output
    except Exception as exc:
        finish_task(task_id, "failed", error_message=str(exc)[:1000])
        raise


@bp.route("/chapters/<int:chapter_id>/generate", methods=["POST"])
@bp.route("/chapters/<int:chapter_id>/regenerate", methods=["POST"])
def generate_chapter(chapter_id):
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(regenerate_chapter(chapter_id, instruction=data.get("instruction"), created_by=data.get("userId"))), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": f"Chapter generation failed: {str(exc)}"}), 500


@bp.route("/chapters/<int:chapter_id>/versions", methods=["GET"])
def list_chapter_versions(chapter_id):
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT id, version_no AS versionNo, evidence_pack_id AS evidencePackId,
                   generation_task_id AS generationTaskId, agent_run_id AS agentRunId,
                   word_count AS wordCount, review_status AS reviewStatus,
                   change_source AS changeSource, created_at AS createdAt
            FROM bid_chapter_versions
            WHERE chapter_id=?
            ORDER BY version_no DESC
            """,
            (chapter_id,),
        ).fetchall()
        return jsonify({"items": rows})
    finally:
        conn.close()


@bp.route("/chapters/<int:chapter_id>/versions/<int:version_id>/restore", methods=["POST"])
def restore_chapter_version(chapter_id, version_id):
    conn = get_db()
    try:
        version = conn.execute(
            "SELECT id FROM bid_chapter_versions WHERE id=? AND chapter_id=?",
            (version_id, chapter_id),
        ).fetchone()
        if not version:
            return jsonify({"error": "Chapter version not found."}), 404
        conn.execute(
            "UPDATE bid_chapters SET current_version_id=?, status='generated', updated_at=? WHERE id=?",
            (version_id, now(), chapter_id),
        )
        conn.commit()
        return jsonify({"chapterId": chapter_id, "currentVersionId": version_id})
    finally:
        conn.close()


@bp.route("/chapters/<int:chapter_id>/rewrite-tasks", methods=["POST"])
def create_rewrite_task(chapter_id):
    data = request.get_json(silent=True) or {}
    chapter = get_chapter(chapter_id)
    if not chapter:
        return jsonify({"error": "Chapter not found."}), 404

    rewrite_scope = data.get("rewriteScope") or "chapter"
    selected_text = data.get("selectedText")
    instruction = data.get("instruction")

    patch = None
    context_hash = None
    status = "suggested"

    if rewrite_scope == "selection" and selected_text and instruction:
        try:
            patch = generate_rewrite_patch(
                project_id=chapter["project_id"],
                chapter_id=chapter_id,
                selected_text=selected_text,
                instruction=instruction,
            )
            context_hash = patch.get("context_hash")
        except PatchConflictError as exc:
            return jsonify({"error": str(exc)}), 409
        except Exception as exc:
            return jsonify({"error": f"Patch generation failed: {str(exc)}"}), 500
    else:
        patch = {"operation": "regenerate", "instruction": instruction}

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO rewrite_tasks
            (tenant_id, project_id, bid_chapter_id, source_version_id, rewrite_scope,
             instruction, selected_text, context_hash, patch_json, status, created_by, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chapter["project_id"],
                chapter_id,
                chapter.get("current_version_id"),
                rewrite_scope,
                instruction,
                selected_text,
                context_hash,
                json_dumps(patch),
                status,
                data.get("userId"),
                now(),
                now(),
            ),
        )
        task_id = cursor.lastrowid
        conn.commit()
        return jsonify({
            "rewriteTaskId": task_id,
            "status": status,
            "patch": patch,
        }), 201
    finally:
        conn.close()


@bp.route("/rewrite-tasks/<int:task_id>", methods=["GET"])
def get_rewrite_task(task_id):
    conn = get_db()
    try:
        task = conn.execute("SELECT * FROM rewrite_tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            return jsonify({"error": "Rewrite task not found."}), 404
        return jsonify({"task": task})
    finally:
        conn.close()


@bp.route("/rewrite-tasks/<int:task_id>/apply", methods=["POST"])
def apply_rewrite_task(task_id):
    data = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        task = conn.execute("SELECT * FROM rewrite_tasks WHERE id=?", (task_id,)).fetchone()
    finally:
        conn.close()
    if not task:
        return jsonify({"error": "Rewrite task not found."}), 404

    patch = task.get("patch_json")
    if isinstance(patch, str):
        try:
            patch = json.loads(patch)
        except (json.JSONDecodeError, TypeError):
            patch = {}

    if patch and patch.get("operation") == "replace_selection":
        conn = get_db()
        try:
            version = conn.execute(
                "SELECT content FROM bid_chapter_versions WHERE id=?",
                (task.get("source_version_id"),),
            ).fetchone()
        finally:
            conn.close()
        if not version:
            return jsonify({"error": "Source chapter version not found."}), 404

        try:
            new_content = apply_selection_patch(version.get("content") or "", patch)
        except PatchConflictError as exc:
            return jsonify({"error": str(exc), "conflict": True}), 409

        version_result = create_chapter_version(
            chapter_id=task["bid_chapter_id"],
            content=new_content,
            change_source="rewrite_patch",
        )
        conn = get_db()
        try:
            conn.execute(
                "UPDATE rewrite_tasks SET target_version_id=?, status='applied', updated_at=? WHERE id=?",
                (version_result["version_id"], now(), task_id),
            )
            conn.commit()
        finally:
            conn.close()
        return jsonify({
            "rewriteTaskId": task_id,
            "status": "applied",
            "version": version_result,
            "patch": patch,
        })
    else:
        try:
            result = regenerate_chapter(task["bid_chapter_id"], instruction=task.get("instruction"), created_by=data.get("userId"))
            conn = get_db()
            try:
                conn.execute(
                    "UPDATE rewrite_tasks SET target_version_id=?, status='applied', updated_at=? WHERE id=?",
                    (result["version"]["version_id"], now(), task_id),
                )
                conn.commit()
            finally:
                conn.close()
            return jsonify({"rewriteTaskId": task_id, "status": "applied", **result})
        except Exception as exc:
            return jsonify({"error": f"Apply rewrite failed: {str(exc)}"}), 500


@bp.route("/rewrite-tasks/<int:task_id>/reject", methods=["POST"])
def reject_rewrite_task(task_id):
    conn = get_db()
    try:
        conn.execute("UPDATE rewrite_tasks SET status='rejected', updated_at=? WHERE id=?", (now(), task_id))
        conn.commit()
        return jsonify({"rewriteTaskId": task_id, "status": "rejected"})
    finally:
        conn.close()


@bp.route("/projects/<int:project_id>/review-report", methods=["GET"])
def project_review_report(project_id):
    bid_document_id = request.args.get("bidDocumentId", type=int)
    report = create_compliance_report(project_id=project_id, bid_document_id=bid_document_id)
    return jsonify(report)
