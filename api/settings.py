from flask import Blueprint, jsonify, request

from core.db import get_db
from core.llm_providers import (
    PROVIDERS,
    get_model_setting,
    mask_api_key,
    public_provider_list,
    save_model_setting,
)
from services.qwen_client import call_llm_api


bp = Blueprint("settings", __name__)


def _count(conn, sql):
    row = conn.execute(sql).fetchone() or {}
    return int(next(iter(row.values()), 0) or 0)


@bp.route("/model-providers", methods=["GET"])
def model_providers():
    return jsonify({"providers": public_provider_list()})


@bp.route("/model-config", methods=["GET"])
def model_config():
    setting = get_model_setting()
    provider = PROVIDERS.get(setting["active_provider"], PROVIDERS["xiaomi_mimo"])
    return jsonify(
        {
            "activeProvider": setting["active_provider"],
            "providerName": provider["name"],
            "model": setting["model"],
            "baseUrl": setting["base_url"],
            "apiKeyMasked": mask_api_key(setting.get("api_key", "")),
            "apiKeySet": bool(setting.get("api_key")),
        }
    )


@bp.route("/model-config", methods=["POST"])
def update_model_config():
    data = request.get_json(silent=True) or {}
    active_provider = data.get("activeProvider")
    model = data.get("model")
    api_key = data.get("apiKey")
    base_url = data.get("baseUrl")

    try:
        saved = save_model_setting(active_provider, model, api_key, base_url)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"message": "Model provider saved.", "config": saved})


@bp.route("/test-model", methods=["POST"])
def test_model():
    try:
        response = call_llm_api(
            [{"role": "user", "content": "请只回复 JSON：{\"ok\": true}"}],
            response_format={"type": "json_object"},
            timeout=30,
            task_type="review",
        )
        content = response["output"]["choices"][0]["message"]["content"]
        return jsonify({"message": "Model connection succeeded.", "content": content})
    except Exception as exc:
        return jsonify({"error": f"Model connection failed: {str(exc)}"}), 500


@bp.route("/dashboard-stats", methods=["GET"])
def dashboard_stats():
    conn = get_db()
    try:
        projects = _count(conn, "SELECT COUNT(*) AS projects FROM bid_projects WHERE deleted_at IS NULL")
        documents = _count(conn, "SELECT COUNT(*) AS documents FROM knowledge_documents WHERE deleted_at IS NULL")
        model_calls = _count(conn, "SELECT COUNT(*) AS model_calls FROM model_call_logs")
        return jsonify({"projects": projects, "documents": documents, "modelCalls": model_calls})
    finally:
        conn.close()


@bp.route("/model-logs", methods=["GET"])
def model_logs():
    limit = request.args.get("limit", default=100, type=int)
    limit = max(1, min(limit, 200))
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT
                id,
                project_id,
                generation_task_id,
                provider_code,
                model_name,
                latency_ms,
                status,
                error_message,
                created_at
            FROM model_call_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return jsonify({"items": rows})
    finally:
        conn.close()
